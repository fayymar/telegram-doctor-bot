import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramConflictError
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import MenuButtonDefault

from config import BOT_TOKEN
from bot.handlers import basic, profile, consultation, specialists, history, medications, health_diary, clinic_finder, fallback
from bot.middlewares import FSMTimeoutMiddleware
from utils.logger import setup_logger
from services.consultation_agent import (
    check_red_flags,
    parse_and_generate_questions,
    get_anamnesis_questions,
    get_final_recommendation,
    get_patient_history,
    get_recent_health_metrics,
)
from database.connection import supabase_client, run_query


# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = setup_logger(__name__)


# Инициализация бота
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

dp = Dispatcher()

# Регистрация middleware
dp.message.middleware(FSMTimeoutMiddleware())
dp.callback_query.middleware(FSMTimeoutMiddleware())

# Регистрация роутеров (ПОРЯДОК ВАЖЕН!)
dp.include_router(basic.router)        # Базовые команды (/start, /help)
dp.include_router(profile.router)      # Профиль и регистрация
dp.include_router(history.router)      # История консультаций
dp.include_router(medications.router)  # Напоминания о лекарствах
dp.include_router(health_diary.router) # Дневник здоровья
dp.include_router(clinic_finder.router) # Поиск клиник рядом
dp.include_router(specialists.router)  # Поиск специалистов
dp.include_router(consultation.router) # Консультации
dp.include_router(fallback.router)    # Fallback для зависших FSM (ВСЕГДА ПОСЛЕДНИМ)


# Хранилище сессий в памяти (для MVP)
consultation_sessions: dict = {}

# Хранилище кодов авторизации для Web — shared с bot handlers
from bot.shared import web_auth_codes, link_codes

# ── Rate limiting (in-memory, resets on redeploy) ──────────────────────────
from collections import defaultdict
import time as _time

_rate_counters: dict = defaultdict(list)  # ip → [timestamps]
_RATE_LIMIT = 60       # max requests
_RATE_WINDOW = 60      # per N seconds

def _is_rate_limited(request: web.Request) -> bool:
    """Simple IP-based rate limiting. Returns True if request should be blocked."""
    ip = request.headers.get("X-Forwarded-For", request.remote or "unknown").split(",")[0].strip()
    now = _time.time()
    window_start = now - _RATE_WINDOW
    timestamps = _rate_counters[ip]
    # Remove old timestamps
    _rate_counters[ip] = [t for t in timestamps if t > window_start]
    if len(_rate_counters[ip]) >= _RATE_LIMIT:
        return True
    _rate_counters[ip].append(now)
    return False


def _rate_limit_response() -> web.Response:
    return json_response({"error": "Too many requests. Please slow down."}, status=429)




ALLOWED_ORIGINS = {
    "https://symed-web.vercel.app",
    "https://symed.uz",
    "https://www.symed.uz",
    "https://sympto-med-app.vercel.app",
    "https://telegram-doctor-bot.onrender.com",
}

def _get_cors_headers(request: web.Request) -> dict:
    origin = request.headers.get("Origin", "")
    allowed = origin if origin in ALLOWED_ORIGINS else "https://sympto-med-app.vercel.app"
    return {
        "Access-Control-Allow-Origin": allowed,
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Vary": "Origin",
    }

# Fallback headers for non-request contexts
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "https://sympto-med-app.vercel.app",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}


def json_response(data: dict, status: int = 200) -> web.Response:
    return web.Response(
        text=json.dumps(data, ensure_ascii=False),
        status=status,
        content_type="application/json",
        headers=CORS_HEADERS,
    )


async def options_handler(request: web.Request) -> web.Response:
    """Универсальный обработчик preflight OPTIONS запросов"""
    return web.Response(status=204, headers=CORS_HEADERS)


@web.middleware
async def cors_middleware(request: web.Request, handler):
    cors_headers = _get_cors_headers(request)
    if request.method == "OPTIONS":
        return web.Response(status=204, headers=cors_headers)
    response = await handler(request)
    for key, value in cors_headers.items():
        response.headers[key] = value
    return response


# HTTP сервер для Render (Health check)
async def health_check(request):
    """Endpoint для проверки здоровья сервиса"""
    return web.Response(text="OK", status=200)


# ── API endpoints ──────────────────────────────────────────────

async def api_consultation_start(request: web.Request) -> web.Response:
    """POST /api/consultation/start"""
    if _is_rate_limited(request):
        return _rate_limit_response()
    try:
        body = await request.json()
    except Exception as e:
        logger.warning(f"Consultation start: failed to parse JSON body: {e}")
        return json_response({"error": "Invalid JSON body"}, status=400)

    logger.info(f"Consultation start request body: {body}")

    user_id = body.get("user_id")
    symptoms = body.get("symptoms", "").strip()

    if not symptoms:
        logger.warning(f"Consultation start: missing symptoms, body={body}")
        return json_response({"error": "Missing required field: symptoms"}, status=400)

    # Получаем профиль пользователя из Supabase (только если есть user_id)
    user_profile = {}
    patient_history = []
    health_metrics = {"has_any_data": False}
    if user_id:
        try:
            resp = await run_query(lambda: supabase_client.table("user_profiles").select("*").eq("user_id", int(user_id)).limit(1).execute())
            user_profile = (resp.data[0] if resp.data else {})
        except Exception:
            user_profile = {}
        patient_history = get_patient_history(user_id, supabase_client)
        health_metrics = get_recent_health_metrics(user_id, supabase_client, hours=24)
    logger.info(f"Health metrics for user_id={user_id}: has_data={health_metrics.get('has_any_data')}")

    # Шаг 1: Красные флаги (с учётом метрик)
    red_flag_result = check_red_flags(symptoms, health_metrics=health_metrics)
    red_flag = red_flag_result.get("red_flag", False)
    needs_fresh_metrics = red_flag_result.get("needs_fresh_metrics", [])

    # Шаг 2: Генерация уточняющих вопросов
    questions = parse_and_generate_questions(symptoms, user_profile, patient_history)

    session_id = str(uuid.uuid4())
    consultation_sessions[session_id] = {
        "_created_at": datetime.utcnow(),
        "user_id": user_id,
        "symptoms": symptoms,
        "user_profile": user_profile,
        "questions": questions,
        "answers": [],
        "duration": None,
        "anamnesis_questions": [],
        "anamnesis_answers": [],
        "health_metrics": health_metrics,
    }

    return json_response({
        "session_id": session_id,
        "questions": questions,
        "red_flag": red_flag,
        "needs_fresh_metrics": needs_fresh_metrics,
    })


async def api_consultation_answer(request: web.Request) -> web.Response:
    """POST /api/consultation/answer"""
    try:
        body = await request.json()
    except Exception:
        return json_response({"error": "Invalid JSON"}, status=400)

    logger.info(f"Consultation answer: {body}")

    session_id = body.get("session_id")
    if not session_id:
        return json_response({"error": "session_id is required"}, status=400)

    session = consultation_sessions.get(session_id)
    if not session:
        return json_response({"error": "Session not found"}, status=404)

    try:
        answers = body.get("answers", [])
        questions = session["questions"]

        # Сохраняем каждый ответ, сопоставляя с вопросом по индексу
        paired = []
        for i, ans in enumerate(answers):
            q_text = questions[i]["question"] if i < len(questions) else ""
            paired.append({"question": q_text, "answer": str(ans)})
        session["answers"] = paired

        return json_response({"next_step": "duration"})
    except Exception as e:
        logger.error(f"Consultation answer error: {e}", exc_info=True)
        return json_response({"error": str(e)}, status=500)


async def api_consultation_duration(request: web.Request) -> web.Response:
    """POST /api/consultation/duration"""
    try:
        body = await request.json()
    except Exception:
        return json_response({"error": "Invalid JSON"}, status=400)

    logger.info(f"Consultation duration: {body}")

    session_id = body.get("session_id")
    duration = body.get("duration", "")

    if not session_id:
        return json_response({"error": "session_id is required"}, status=400)

    session = consultation_sessions.get(session_id)
    if not session:
        return json_response({"error": "Session not found"}, status=404)

    try:
        session["duration"] = duration

        # Генерация анамнестических вопросов
        anamnesis_questions = get_anamnesis_questions(session["symptoms"])
        session["anamnesis_questions"] = anamnesis_questions

        # Нормализуем ключ: question → text для Mini App
        normalized = [
            {"text": q.get("question", q.get("text", "")), "options": q.get("options", [])}
            for q in anamnesis_questions
        ]

        return json_response({"anamnesis_questions": normalized, "needs_fresh_metrics": []})
    except Exception as e:
        logger.error(f"Consultation duration error: {e}", exc_info=True)
        return json_response({"error": str(e)}, status=500)


async def api_consultation_result(request: web.Request) -> web.Response:
    """POST /api/consultation/result"""
    try:
        body = await request.json()
    except Exception:
        return json_response({"error": "Invalid JSON"}, status=400)

    logger.info(f"Consultation result: {body}")

    session_id = body.get("session_id")
    if not session_id:
        return json_response({"error": "session_id is required"}, status=400)

    session = consultation_sessions.get(session_id)
    if not session:
        return json_response({"error": "Session not found"}, status=404)

    try:
        # Анамнестические ответы могут быть переданы в теле запроса (плоский список строк или список dict)
        raw_anamnesis = body.get("anamnesis_answers", session.get("anamnesis_answers", []))
        # Нормализуем: если пришли строки — сопоставляем с вопросами из сессии
        if raw_anamnesis and isinstance(raw_anamnesis[0], str):
            qs = session.get("anamnesis_questions", [])
            anamnesis_answers = [
                {"question": (qs[i].get("text") or qs[i].get("question", "")) if i < len(qs) else "",
                 "answer": str(ans)}
                for i, ans in enumerate(raw_anamnesis)
            ]
        else:
            anamnesis_answers = raw_anamnesis
        session["anamnesis_answers"] = anamnesis_answers

        all_data = {
            "symptoms": session["symptoms"],
            "followup_answers": [a for a in session["answers"] if a],
            "duration": session["duration"] or "не указана",
            "anamnesis_answers": anamnesis_answers,
        }

        # user_profile может отсутствовать в упрощённых сессиях — подгружаем при необходимости
        user_profile = session.get("user_profile") or {}
        if not user_profile:
            try:
                resp = await run_query(lambda: supabase_client.table("user_profiles").select("*").eq("user_id", int(session["user_id"])).limit(1).execute())
                user_profile = (resp.data[0] if resp.data else {})
            except Exception:
                pass

        recommendation = get_final_recommendation(
            all_data,
            user_profile,
            health_metrics=session.get("health_metrics"),
        )

        # Сохраняем в Supabase (только для авторизованных пользователей)
        specialists_raw = recommendation.get("specialists", [])
        if session.get("user_id"):
            try:
                recommended_doctor = specialists_raw[0]["name"] if specialists_raw else "Терапевт"
                await run_query(lambda: supabase_client.table("consultations").insert({
                    "user_id": session["user_id"],
                    "symptoms": json.dumps({"text": session["symptoms"], "history": [a for a in session["answers"] if a]}, ensure_ascii=False),
                    "questions_answers": json.dumps(all_data, ensure_ascii=False),
                    "recommended_doctor": recommended_doctor,
                    "urgency_level": recommendation.get("urgency", "medium"),
                }).execute())
            except Exception as e:
                logger.error(f"Failed to save consultation to Supabase: {e}", exc_info=True)
        else:
            specialists_raw = recommendation.get("specialists", [])

        # Нормализуем specialists: match_percent → percentage для Mini App
        specialists_out = [
            {
                "name": s.get("name", ""),
                "percentage": s.get("match_percent", s.get("percentage", 0)),
                "reason": s.get("reason", ""),
            }
            for s in specialists_raw
        ]

        # Clean up session from memory after successful result
        consultation_sessions.pop(session_id, None)
        logger.info(f"Session {session_id} cleaned up after result")

        return json_response({
            "recommendation": recommendation.get("recommendation", recommendation.get("urgency_reason", "")),
            "specialists": specialists_out,
            "urgency": recommendation.get("urgency", "medium"),
            "needs_fresh_metrics": recommendation.get("needs_fresh_metrics", []),
            "needs_fresh_metrics_message": recommendation.get("needs_fresh_metrics_message", ""),
        })

    except Exception as e:
        logger.error(f"Consultation result error: {e}", exc_info=True)
        return json_response({"error": str(e)}, status=500)


_PROFILE_FIELDS = [
    "full_name", "phone", "birthdate", "gender", "height", "weight",
    "chronic_diseases", "drug_allergies", "smoking", "hereditary", "physical_activity",
]


async def api_profile_get(request: web.Request) -> web.Response:
    """GET /api/profile/{user_id} — читает из таблицы user_profiles по user_id"""
    user_id = request.match_info.get("user_id")
    if not user_id:
        return json_response({"error": "user_id is required"}, status=400)

    logger.info(f"Profile GET request: user_id={user_id}")

    try:
        resp = await run_query(
            lambda: supabase_client.table("user_profiles")
            .select(", ".join(_PROFILE_FIELDS))
            .eq("user_id", int(user_id))
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        logger.info(f"Profile GET result: user_id={user_id}, exists={bool(rows)}, data={rows}")
        if not rows:
            return json_response({"exists": False, "profile": None})

        row = rows[0]
        profile = {f: row.get(f) for f in _PROFILE_FIELDS}
        return json_response({"exists": True, "profile": profile})
    except Exception as e:
        logger.error(f"Profile GET error for user {user_id}: {e}", exc_info=True)
        return json_response({"error": str(e)}, status=500)


async def api_profile_post(request: web.Request) -> web.Response:
    """POST /api/profile/{user_id} — upsert в таблицу user_profiles по user_id"""
    user_id = request.match_info.get("user_id")
    if not user_id:
        return json_response({"error": "user_id is required"}, status=400)

    try:
        body = await request.json()
    except Exception:
        return json_response({"error": "Invalid JSON"}, status=400)

    logger.info(f"Profile POST request: user_id={user_id}, body={body}")
    logger.info(f"Saving profile fields: {list(body.keys())}")

    # Берём только допустимые поля профиля
    update_data = {k: v for k, v in body.items() if k in _PROFILE_FIELDS}
    if not update_data:
        return json_response({"error": "No valid profile fields provided"}, status=400)

    update_data["user_id"] = int(user_id)
    logger.info(f"Profile POST upsert data: {update_data}")

    try:
        await run_query(lambda: supabase_client.table("user_profiles").upsert(update_data, on_conflict="user_id").execute())
        logger.info(f"Profile POST success: user_id={user_id}")
        return json_response({"status": "ok"})
    except Exception as e:
        logger.error(f"Profile POST error for user {user_id}: {e}", exc_info=True)
        return json_response({"error": str(e)}, status=500)


def _fetch_heartrate_records(user_id: str) -> list:
    """Выполняет запрос к Supabase. Использует глобальный supabase_client."""
    resp = (
        supabase_client.table('health_metrics')
        .select('value, recorded_at, source')
        .eq('user_id', user_id)
        .eq('metric_type', 'heartrate')
        .order('recorded_at', desc=True)
        .limit(10)
        .execute()
    )
    return resp.data or []


async def api_health_heartrate_get(request: web.Request) -> web.Response:
    """GET /api/health/heartrate/{user_id}"""
    user_id = request.match_info.get('user_id')
    if not user_id:
        return json_response({'error': 'user_id is required'}, status=400)

    try:
        records = _fetch_heartrate_records(user_id)
    except Exception as e:
        if 'Name or service not known' in str(e):
            logger.warning(f"Heartrate GET DNS error for user_id={user_id}, retrying in 1s: {e}")
            await asyncio.sleep(1)
            try:
                records = _fetch_heartrate_records(user_id)
            except Exception as retry_e:
                logger.error(f"Heartrate GET retry failed for user_id={user_id}: {retry_e}", exc_info=True)
                return json_response({'error': str(retry_e)}, status=500)
        else:
            logger.error(f"Heartrate GET error for user_id={user_id}: {e}", exc_info=True)
            return json_response({'error': str(e)}, status=500)

    logger.info(f"Heartrate GET for user_id={user_id}: found {len(records)} records")
    return json_response({'records': records, 'has_data': len(records) > 0})


async def api_health_heartrate(request: web.Request) -> web.Response:
    """POST /api/health/heartrate"""
    try:
        data = await request.json()
        logger.info(f"Received heartrate POST: {data}")
        user_id = data.get('user_id')
        heartrate = data.get('heartrate')
        timestamp = data.get('timestamp', datetime.utcnow().isoformat())

        if not heartrate:
            return json_response({'error': 'heartrate required'}, status=400)

        # Формируем запись — user_id включаем только если он передан
        record = {
            'metric_type': 'heartrate',
            'value': float(heartrate),
            'unit': 'bpm',
            'recorded_at': timestamp,
            'source': 'apple_watch'
        }
        if user_id:
            record['user_id'] = user_id

        # Сохраняем в Supabase таблицу health_metrics
        await run_query(lambda: supabase_client.table('health_metrics').insert(record).execute())

        # Если есть user_id — отправляем уведомление в Telegram
        if user_id:
            hr = float(heartrate)
            if hr > 120 or hr < 50:
                msg = f"🚨 Пульс: {hr:.0f} уд/мин! Значительно выше нормы. Рекомендуем обратиться к врачу."
            elif hr > 100:
                msg = f"❤️ Пульс получен: {hr:.0f} уд/мин ⚠️ Немного выше нормы. Отдохните."
            else:
                msg = f"❤️ Пульс получен: {hr:.0f} уд/мин ✅ В норме"

            await bot.send_message(user_id, msg)

        return json_response({'status': 'ok', 'message': f'Пульс сохранён: {heartrate} уд/мин'})

    except Exception as e:
        logger.error(f"Health heartrate error: {e}")
        return json_response({'error': str(e)}, status=500)


def _interpret_heartrate(hr: float) -> str:
    if hr < 50 or hr > 120:
        return f"❤️ Пульс: {hr:.0f} уд/мин 🚨 Критично"
    if hr < 60:
        return f"❤️ Пульс: {hr:.0f} уд/мин ⚠️ Ниже нормы"
    if hr > 100:
        return f"❤️ Пульс: {hr:.0f} уд/мин ⚠️ Повышен"
    return f"❤️ Пульс: {hr:.0f} уд/мин ✅ В норме"


def _interpret_blood_pressure(systolic: float, diastolic: float) -> str:
    if systolic >= 140 or diastolic >= 90:
        label = "🚨 Высокое"
    elif systolic >= 130 or diastolic >= 85:
        label = "⚠️ Слегка повышенное"
    elif systolic < 90 or diastolic < 60:
        label = "⚠️ Пониженное"
    else:
        label = "✅ Норма"
    return f"🩺 Давление: {systolic:.0f}/{diastolic:.0f} мм рт.ст. {label}"


def _interpret_spo2(spo2: float) -> str:
    if spo2 < 90:
        return f"🫁 SpO2: {spo2:.0f}% 🚨 Критично низкая насыщенность"
    if spo2 < 95:
        return f"🫁 SpO2: {spo2:.0f}% ⚠️ Понижена"
    return f"🫁 SpO2: {spo2:.0f}% ✅ Норма"


def _interpret_steps(steps: int) -> str:
    if steps >= 10000:
        return f"👣 Шаги: {steps} за день 🏃 Высокая активность"
    if steps >= 5000:
        return f"👣 Шаги: {steps} за день 👍 Средняя активность"
    return f"👣 Шаги: {steps} за день 🛋️ Низкая активность"


def _has_deviation(received: dict) -> bool:
    """Проверяет наличие отклонений от нормы."""
    return bool(_get_abnormal_metrics(received))


def _get_abnormal_metrics(received: dict) -> list:
    """Возвращает список ключей метрик с отклонениями: 'heartrate', 'blood_pressure', 'spo2'."""
    abnormal = []
    hr = received.get('heartrate')
    if hr is not None and (hr < 60 or hr > 100):
        abnormal.append('heartrate')
    s = received.get('systolic')
    d = received.get('diastolic')
    if s is not None and d is not None and (s >= 140 or d >= 90 or s < 90 or d < 60):
        abnormal.append('blood_pressure')
    spo2 = received.get('spo2')
    if spo2 is not None and spo2 < 95:
        abnormal.append('spo2')
    return abnormal


def _build_alert_msg(received: dict) -> str:
    """Формирует сообщение об отклонениях для Telegram."""
    lines = ["⚠️ Обнаружены отклонения в показателях:\n"]
    recommendations = []

    if 'heartrate' in received:
        hr = received['heartrate']
        lines.append(_interpret_heartrate(hr))
        if hr < 50 or hr > 120:
            recommendations.append("Критически аномальный пульс — немедленно обратитесь за медицинской помощью.")
        elif hr < 60 or hr > 100:
            recommendations.append("Нестандартный пульс — отдохните и повторите измерение через 15 минут.")

    if 'systolic' in received and 'diastolic' in received:
        s, d = received['systolic'], received['diastolic']
        lines.append(_interpret_blood_pressure(s, d))
        if s >= 140 or d >= 90:
            recommendations.append(
                "При повышенном давлении рекомендуем отдохнуть, избегать физических нагрузок "
                "и измерить давление повторно через 15-30 минут. "
                "Если давление стабильно выше 140/90 — обратитесь к врачу."
            )
        elif s < 90 or d < 60:
            recommendations.append(
                "При пониженном давлении выпейте воды, лягте и поднимите ноги. "
                "Если состояние не улучшается — обратитесь к врачу."
            )

    if 'spo2' in received:
        spo2 = received['spo2']
        lines.append(_interpret_spo2(spo2))
        if spo2 < 90:
            recommendations.append("Критически низкое насыщение крови кислородом — немедленно обратитесь за медицинской помощью.")
        elif spo2 < 95:
            recommendations.append("Пониженное насыщение крови кислородом — обеспечьте приток свежего воздуха и отдохните.")

    if 'steps' in received:
        lines.append(_interpret_steps(int(received['steps'])))

    if recommendations:
        lines.append(f"\n💡 Рекомендация: {' '.join(recommendations)}")

    return "\n".join(lines)


async def send_delayed_alert(user_id, received: dict, delay: int = 120):
    """Отправляет уведомление об отклонениях через delay секунд."""
    await asyncio.sleep(delay)
    msg = _build_alert_msg(received)
    try:
        await bot.send_message(user_id, msg)
        logger.info(f"Delayed alert sent to user_id={user_id}")
    except Exception as e:
        logger.error(f"Delayed alert send error for user_id={user_id}: {e}")


async def send_remeasure_reminder(user_id, abnormal_metrics: list, delay: int = 14400):
    """Напоминание о повторном измерении через delay секунд (по умолчанию 4 часа)."""
    await asyncio.sleep(delay)

    metric_names = {
        'blood_pressure': 'давление',
        'heartrate': 'пульс',
        'spo2': 'SpO2',
    }
    metrics_text = [metric_names.get(m, m) for m in abnormal_metrics]
    metrics_list = ', '.join(metrics_text)

    message = (
        f"🔔 Напоминание о повторном измерении\n\n"
        f"Ранее были обнаружены отклонения: {metrics_list}.\n"
        f"Рекомендуем измерить повторно чтобы убедиться что показатели пришли в норму.\n\n"
        f"Откройте приложение Symed → Здоровье → «Отправить показатели сейчас»"
    )

    try:
        await bot.send_message(chat_id=user_id, text=message)
        logger.info(f"Remeasure reminder sent to user {user_id}")
    except Exception as e:
        logger.error(f"Failed to send reminder to {user_id}: {e}")


async def api_health_metrics_post(request: web.Request) -> web.Response:
    """POST /api/health/metrics — тихое сохранение + отложенный алерт при отклонениях"""
    try:
        data = await request.json()
        logger.info(f"Received health metrics POST: {data}")
    except Exception:
        return json_response({'error': 'Invalid JSON'}, status=400)

    user_id = data.get('user_id')
    timestamp = data.get('timestamp') or datetime.utcnow().isoformat()

    # Если передан часовой пояс (формат "+05:00") — конвертируем timestamp в UTC
    tz_str = data.get('timezone')
    if tz_str and timestamp:
        try:
            import re as _re
            from datetime import timezone as _tz
            m = _re.match(r'([+-])(\d{2}):(\d{2})', str(tz_str))
            if m:
                sign = 1 if m.group(1) == '+' else -1
                offset = timedelta(hours=int(m.group(2)), minutes=int(m.group(3))) * sign
                # Убираем возможный суффикс Z или существующий offset перед парсингом
                ts_clean = timestamp.rstrip('Z').split('+')[0]
                if ts_clean.count('-') > 2:          # "2026-05-04T10:00:00-05:00"
                    ts_clean = ts_clean.rsplit('-', 1)[0]
                dt_local = datetime.fromisoformat(ts_clean).replace(tzinfo=_tz(offset))
                timestamp = dt_local.astimezone(_tz.utc).strftime('%Y-%m-%dT%H:%M:%S')
                logger.info(f"Timezone {tz_str} applied, recorded_at={timestamp}")
        except Exception as tz_err:
            logger.warning(f"Timezone conversion failed (tz={tz_str}): {tz_err}")

    METRIC_MAP = [
        ('heartrate',  'heartrate',              'bpm'),
        ('systolic',   'blood_pressure_systolic', 'mmHg'),
        ('diastolic',  'blood_pressure_diastolic','mmHg'),
        ('spo2',       'spo2',                   '%'),
        ('steps',      'steps',                  'steps'),
    ]

    records_to_insert = []
    received = {}
    for field, metric_type, unit in METRIC_MAP:
        raw = data.get(field)
        if raw is None or raw == 0:
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        row = {
            'metric_type': metric_type,
            'value': value,
            'unit': unit,
            'recorded_at': timestamp,
            'source': 'apple_watch',
        }
        if user_id:
            row['user_id'] = user_id
        records_to_insert.append(row)
        received[field] = value

    if not records_to_insert:
        return json_response({'error': 'No valid metrics provided'}, status=400)

    # Тихое сохранение в Supabase
    try:
        await run_query(lambda: supabase_client.table('health_metrics').insert(records_to_insert).execute())
    except Exception as e:
        logger.error(f"Health metrics insert error: {e}", exc_info=True)
        return json_response({'error': str(e)}, status=500)

    logger.info(f"Silent save for user {user_id}: {received}")

    # Проверка отклонений — если есть, запускаем отложенный алерт через 2 минуты
    if user_id and _has_deviation(received):
        abnormal = _get_abnormal_metrics(received)
        asyncio.create_task(send_delayed_alert(user_id, received, delay=120))
        asyncio.create_task(send_remeasure_reminder(user_id, abnormal, delay=14400))
        logger.info(f"Deviation detected for user_id={user_id}, alert in 120s, reminder in 4h, metrics={abnormal}")

    return json_response({'status': 'ok', 'saved': len(records_to_insert)})


async def api_health_metrics_report(request: web.Request) -> web.Response:
    """POST /api/health/metrics/report/{user_id} — ручной отчёт о последних метриках"""
    user_id = request.match_info.get('user_id')
    if not user_id:
        return json_response({'error': 'user_id is required'}, status=400)

    try:
        cutoff = (datetime.utcnow() - timedelta(hours=1)).isoformat()
        resp = (
            supabase_client.table('health_metrics')
            .select('metric_type, value, recorded_at')
            .eq('user_id', user_id)
            .gte('recorded_at', cutoff)
            .order('recorded_at', desc=True)
            .execute()
        )
        rows = resp.data or []
    except Exception as e:
        logger.error(f"Report fetch error for user_id={user_id}: {e}", exc_info=True)
        return json_response({'error': str(e)}, status=500)

    # Берём последнюю запись каждого типа
    seen: dict = {}
    for row in rows:
        mt = row['metric_type']
        if mt not in seen:
            seen[mt] = row

    if not seen:
        return json_response({'status': 'ok', 'message': 'No data in the last hour'})

    # Собираем received-словарь для построения отчёта
    received: dict = {}
    if 'heartrate' in seen:
        received['heartrate'] = seen['heartrate']['value']
    if 'blood_pressure_systolic' in seen:
        received['systolic'] = seen['blood_pressure_systolic']['value']
    if 'blood_pressure_diastolic' in seen:
        received['diastolic'] = seen['blood_pressure_diastolic']['value']
    if 'spo2' in seen:
        received['spo2'] = seen['spo2']['value']
    if 'steps' in seen:
        received['steps'] = seen['steps']['value']

    # Формируем полный отчёт
    lines = ["📊 Ваши показатели здоровья:\n"]
    all_ok = True

    if 'heartrate' in received:
        line = _interpret_heartrate(received['heartrate'])
        lines.append(line)
        if '🚨' in line or '⚠️' in line:
            all_ok = False

    if 'systolic' in received and 'diastolic' in received:
        line = _interpret_blood_pressure(received['systolic'], received['diastolic'])
        lines.append(line)
        if '🚨' in line or '⚠️' in line:
            all_ok = False
    elif 'systolic' in received:
        lines.append(f"🩺 Систолическое: {received['systolic']:.0f} мм рт.ст.")

    if 'spo2' in received:
        line = _interpret_spo2(received['spo2'])
        lines.append(line)
        if '🚨' in line or '⚠️' in line:
            all_ok = False

    if 'steps' in received:
        lines.append(_interpret_steps(int(received['steps'])))

    lines.append("\nВсе показатели в норме 👌" if all_ok else "\n⚠️ Есть показатели, требующие внимания.")

    msg = "\n".join(lines)
    try:
        await bot.send_message(user_id, msg)
        logger.info(f"Report sent to user_id={user_id}")
    except Exception as e:
        logger.error(f"Report send error for user_id={user_id}: {e}", exc_info=True)
        return json_response({'error': f'Telegram send failed: {e}'}, status=500)

    return json_response({'status': 'ok', 'message': 'Report sent'})


async def api_health_metrics_get(request: web.Request) -> web.Response:
    """GET /api/health/metrics/{user_id}?type=metric_type&limit=10"""
    user_id = request.match_info.get('user_id')
    if not user_id:
        return json_response({'error': 'user_id is required'}, status=400)

    metric_type = request.rel_url.query.get('type')
    try:
        limit = int(request.rel_url.query.get('limit', 10))
    except ValueError:
        limit = 10

    try:
        query = (
            supabase_client.table('health_metrics')
            .select('metric_type, value, unit, recorded_at, source')
            .eq('user_id', user_id)
            .order('recorded_at', desc=True)
            .limit(limit)
        )
        if metric_type:
            query = query.eq('metric_type', metric_type)
        resp = query.execute()
        records = resp.data or []
        logger.info(f"Health metrics GET user_id={user_id} type={metric_type}: {len(records)} records")
        return json_response({'records': records, 'has_data': len(records) > 0})
    except Exception as e:
        logger.error(f"Health metrics GET error user_id={user_id}: {e}", exc_info=True)
        return json_response({'error': str(e)}, status=500)


async def _check_anamnesis_fields():
    """Проверяет наличие полей анамнеза в user_profiles; пытается добавить их если нет."""
    try:
        supabase_client.table("user_profiles").select(
            "chronic_diseases, drug_allergies, smoking, hereditary"
        ).limit(1).execute()
        logger.info("✅ Anamnesis fields present in user_profiles")
    except Exception as e:
        logger.warning(f"MISSING FIELDS in user_profiles: {e}")
        logger.warning("Attempting to add anamnesis fields via SQL migration...")
        try:
            supabase_client.rpc("exec_sql", {"query": (
                "ALTER TABLE user_profiles "
                "ADD COLUMN IF NOT EXISTS chronic_diseases TEXT[] DEFAULT '{}',"
                "ADD COLUMN IF NOT EXISTS drug_allergies TEXT DEFAULT '',"
                "ADD COLUMN IF NOT EXISTS smoking TEXT DEFAULT 'no',"
                "ADD COLUMN IF NOT EXISTS hereditary TEXT[] DEFAULT '{}';"
            )}).execute()
            logger.info("✅ Anamnesis fields added via SQL migration")
        except Exception as rpc_err:
            logger.error(
                f"Cannot add fields automatically (rpc failed: {rpc_err}). "
                "Please run this SQL manually in Supabase:\n"
                "ALTER TABLE user_profiles "
                "ADD COLUMN IF NOT EXISTS chronic_diseases TEXT[] DEFAULT '{}',"
                "ADD COLUMN IF NOT EXISTS drug_allergies TEXT DEFAULT '',"
                "ADD COLUMN IF NOT EXISTS smoking TEXT DEFAULT 'no',"
                "ADD COLUMN IF NOT EXISTS hereditary TEXT[] DEFAULT '{}';"
            )


async def api_consultations_get(request: web.Request) -> web.Response:
    """GET /api/consultations/{user_id} — история консультаций для Mini App."""
    user_id = request.match_info.get('user_id')
    try:
        resp = await run_query(
            lambda: supabase_client.table('consultations')
            .select('id, symptoms, recommended_doctor, urgency_level, created_at')
            .eq('user_id', int(user_id))
            .order('created_at', desc=True)
            .limit(20)
            .execute()
        )
        rows = resp.data or []
        records = []
        for r in rows:
            symptoms_raw = r.get('symptoms', '')
            try:
                symptoms_parsed = json.loads(symptoms_raw) if symptoms_raw else {}
                if 'text' in symptoms_parsed:
                    symptoms_text = symptoms_parsed['text']
                elif 'history' in symptoms_parsed and symptoms_parsed['history']:
                    first = next(
                        (h for h in symptoms_parsed['history'] if not h.get('question')),
                        symptoms_parsed['history'][0]
                    )
                    symptoms_text = first.get('answer', symptoms_raw)
                elif isinstance(symptoms_parsed, list) and symptoms_parsed:
                    first = next(
                        (h for h in symptoms_parsed if not h.get('question')),
                        symptoms_parsed[0]
                    )
                    symptoms_text = first.get('answer', symptoms_raw)
                else:
                    symptoms_text = symptoms_raw
            except Exception:
                symptoms_text = symptoms_raw
            records.append({
                'id': r.get('id'),
                'symptoms': symptoms_text,
                'recommended_doctor': r.get('recommended_doctor', ''),
                'urgency_level': r.get('urgency_level', 'medium'),
                'created_at': r.get('created_at', ''),
            })
        return json_response({'records': records, 'has_data': bool(records)})
    except Exception as e:
        logger.error(f'Consultations GET error for {user_id}: {e}', exc_info=True)
        return json_response({'records': [], 'has_data': False})



async def api_auth_social(request: web.Request) -> web.Response:
    """POST /api/auth/social — register or find user from OAuth / email provider"""
    cors = _get_cors_headers(request)
    try:
        body = await request.json()
    except Exception:
        return web.Response(status=400, text=json.dumps({"error": "invalid json"}),
                            content_type="application/json", headers=cors)

    provider    = str(body.get("provider", "email")).strip()
    email       = str(body.get("email", "")).strip().lower()
    name        = str(body.get("name", "")).strip()
    provider_id = str(body.get("provider_id", "")).strip()
    avatar      = body.get("avatar") or None

    if not email and not provider_id:
        return web.Response(status=400, text=json.dumps({"error": "email or provider_id required"}),
                            content_type="application/json", headers=cors)

    # Generate a stable integer user_id from provider_id or email
    import hashlib
    seed = provider_id if provider_id else email
    h = int(hashlib.sha256(seed.encode()).hexdigest()[:12], 16)
    # Use range 5_000_000_000 – 9_999_999_999 to avoid clash with Telegram IDs
    user_id = 5_000_000_000 + (h % 4_999_999_999)

    first_name = name.split()[0] if name else email.split("@")[0]
    last_name  = " ".join(name.split()[1:]) if name and len(name.split()) > 1 else None

    try:
        existing = await run_query(
            lambda: supabase_client.table("user_profiles")
                .select("user_id, full_name, phone")
                .eq("user_id", user_id).limit(1).execute()
        )

        if not existing.data:
            # Create new profile
            await run_query(
                lambda: supabase_client.table("user_profiles").insert({
                    "user_id":    user_id,
                    "full_name":  name or first_name,
                    "phone":      None,
                    "gender":     None,
                    "birthdate":  None,
                }).execute()
            )
            is_new = True
            logger.info(f"Social auth: created user_id={user_id} via {provider} ({email})")
        else:
            is_new = False
            logger.info(f"Social auth: found user_id={user_id} via {provider}")

        return web.Response(
            text=json.dumps({
                "id":         user_id,
                "first_name": first_name,
                "last_name":  last_name,
                "username":   None,
                "photo_url":  avatar,
                "provider":   provider,
                "email":      email,
                "is_new":     is_new,
                "auth_date":  int(datetime.utcnow().timestamp()),
            }, ensure_ascii=False),
            status=200, content_type="application/json", headers=cors,
        )

    except Exception as e:
        logger.error(f"Social auth error: {e}", exc_info=True)
        return web.Response(status=500, text=json.dumps({"error": str(e)}),
                            content_type="application/json", headers=cors)



async def api_auth_link_request(request: web.Request) -> web.Response:
    """POST /api/auth/link-request — generate a link code for a web user"""
    cors = _get_cors_headers(request)
    try:
        body = await request.json()
    except Exception:
        return web.Response(status=400, text=json.dumps({"error": "invalid json"}),
                            content_type="application/json", headers=cors)

    web_user_id = body.get("user_id")
    if not web_user_id:
        return web.Response(status=400, text=json.dumps({"error": "user_id required"}),
                            content_type="application/json", headers=cors)

    import random, string
    code = ''.join(random.choices(string.digits, k=6))
    link_codes[code] = {
        "web_user_id": int(web_user_id),
        "verified":    False,
        "telegram_id": None,
        "created_at":  datetime.utcnow(),
    }
    logger.info(f"Link code {code} created for web_user_id={web_user_id}")
    return web.Response(
        text=json.dumps({"code": code}),
        status=200, content_type="application/json", headers=cors,
    )


async def api_auth_link_status(request: web.Request) -> web.Response:
    """GET /api/auth/link-status/{code} — poll for link completion"""
    cors = _get_cors_headers(request)
    code = request.match_info.get("code", "")
    entry = link_codes.get(code)
    if not entry:
        return web.Response(
            text=json.dumps({"verified": False, "error": "not_found"}),
            status=200, content_type="application/json", headers=cors,
        )
    return web.Response(
        text=json.dumps({
            "verified":    entry.get("verified", False),
            "telegram_id": entry.get("telegram_id"),
        }),
        status=200, content_type="application/json", headers=cors,
    )


async def api_auth_request(request: web.Request) -> web.Response:
    """POST /api/auth/request — регистрирует 6-значный код для web-авторизации"""
    try:
        body = await request.json()
    except Exception:
        return web.Response(status=204, headers=_get_cors_headers(request))

    code = str(body.get("code", "")).strip()
    if not code or not code.isdigit() or len(code) != 6:
        return web.Response(
            text=json.dumps({"error": "Invalid code"}, ensure_ascii=False),
            status=400, content_type="application/json",
            headers=_get_cors_headers(request)
        )

    # Удаляем старые коды этого же источника (по IP) — не обязательно, просто чистота
    web_auth_codes[code] = {
        "telegram_id": None,
        "first_name": None,
        "last_name": None,
        "username": None,
        "photo_url": None,
        "verified": False,
        "created_at": datetime.utcnow(),
    }
    logger.info(f"Web auth code registered: {code}")
    return web.Response(
        text=json.dumps({"ok": True, "expires_in": 600}, ensure_ascii=False),
        status=200, content_type="application/json",
        headers=_get_cors_headers(request)
    )


async def api_auth_status(request: web.Request) -> web.Response:
    """GET /api/auth/status/{code} — проверяет статус верификации кода"""
    code = request.match_info.get("code", "")
    entry = web_auth_codes.get(code)

    if not entry:
        return web.Response(
            text=json.dumps({"verified": False, "error": "Code not found or expired"}, ensure_ascii=False),
            status=404, content_type="application/json",
            headers=_get_cors_headers(request)
        )

    # Проверяем expiry (10 минут)
    age = (datetime.utcnow() - entry["created_at"]).total_seconds()
    if age > 600:
        web_auth_codes.pop(code, None)
        return web.Response(
            text=json.dumps({"verified": False, "error": "Code expired"}, ensure_ascii=False),
            status=404, content_type="application/json",
            headers=_get_cors_headers(request)
        )

    if not entry["verified"]:
        return web.Response(
            text=json.dumps({"verified": False}, ensure_ascii=False),
            status=200, content_type="application/json",
            headers=_get_cors_headers(request)
        )

    # Верифицирован — возвращаем данные и удаляем код
    user_data = {
        "verified": True,
        "id": entry["telegram_id"],
        "first_name": entry["first_name"],
        "last_name": entry["last_name"],
        "username": entry["username"],
        "photo_url": entry["photo_url"],
        "auth_date": int(datetime.utcnow().timestamp()),
    }
    web_auth_codes.pop(code, None)
    logger.info(f"Web auth code {code} consumed for user {entry['telegram_id']}")
    return web.Response(
        text=json.dumps(user_data, ensure_ascii=False),
        status=200, content_type="application/json",
        headers=_get_cors_headers(request)
    )


async def cleanup_stale_sessions():
    """Удаляет сессии консультаций старше 2 часов из памяти."""
    while True:
        await asyncio.sleep(3600)  # каждый час
        now = datetime.utcnow()
        stale = []
        for sid, session in list(consultation_sessions.items()):
            created = session.get("_created_at")
            if created and (now - created).total_seconds() > 7200:
                stale.append(sid)
        for sid in stale:
            consultation_sessions.pop(sid, None)
        if stale:
            logger.info(f"Cleaned up {len(stale)} stale consultation sessions")


async def start_bot():
    """Запуск бота с автоматическим перезапуском при ошибках"""
    retry_delay = 5

    while True:
        try:
            logger.info("🤖 Starting Telegram bot...")

            # Проверяем поля анамнеза в БД
            await _check_anamnesis_fields()

            # Удаляем старые вебхуки (если есть)
            await bot.delete_webhook(drop_pending_updates=True)
            logger.info("✅ Webhook cleared")

            # Сбрасываем глобальную Menu Button — управление только через set_chat_menu_button per user
            await bot.set_chat_menu_button(menu_button=MenuButtonDefault())
            logger.info("✅ Global menu button reset to default")

            # Небольшая задержка при старте — даём старому инстансу время завершиться
            await asyncio.sleep(3)

            # Запускаем polling
            logger.info("✅ Bot polling started successfully!")
            await dp.start_polling(
                bot,
                allowed_updates=dp.resolve_used_update_types(),
                handle_signals=False,  # manage signals ourselves
            )

        except KeyboardInterrupt:
            logger.info("⚠️ Bot stopped by user")
            break

        except TelegramConflictError:
            # Two instances running simultaneously (e.g. Render blue-green deploy)
            # Wait for old instance to die, then retry
            logger.warning("⚠️ Conflict: another bot instance is running. Waiting 15s for it to stop...")
            await asyncio.sleep(15)
            continue

        except Exception as e:
            logger.error(f"❌ Bot crashed: {e}", exc_info=True)
            logger.info(f"🔄 Restarting bot in {retry_delay} seconds...")
            await asyncio.sleep(retry_delay)

            # Экспоненциальная задержка, но не более 60 секунд
            retry_delay = min(retry_delay * 2, 60)


async def start_web_server():
    """Запуск веб-сервера для Render"""
    try:
        logger.info("🌐 Starting web server...")

        app = web.Application(middlewares=[cors_middleware])
        app.router.add_get('/health', health_check)
        app.router.add_get('/', health_check)

        # OPTIONS preflight для всех /api/* маршрутов
        app.router.add_route('OPTIONS', '/api/{path_info:.*}', options_handler)

        # API эндпоинты
        app.router.add_post('/api/consultation/start', api_consultation_start)
        app.router.add_post('/api/consultation/answer', api_consultation_answer)
        app.router.add_post('/api/consultation/duration', api_consultation_duration)
        app.router.add_post('/api/consultation/result', api_consultation_result)
        app.router.add_get('/api/consultations/{user_id}', api_consultations_get)
        app.router.add_get('/api/medications/{user_id}', api_medications_get)
        app.router.add_post('/api/medications/{user_id}', api_medications_post)
        app.router.add_post('/api/diary/{user_id}', api_diary_post)
        app.router.add_get('/api/diary/{user_id}', api_diary_get)
        app.router.add_get('/api/profile/{user_id}', api_profile_get)
        app.router.add_post('/api/profile/{user_id}', api_profile_post)
        app.router.add_get('/api/health/heartrate/{user_id}', api_health_heartrate_get)
        app.router.add_post('/api/health/heartrate', api_health_heartrate)
        app.router.add_post('/api/health/metrics', api_health_metrics_post)
        app.router.add_post('/api/health/metrics/report/{user_id}', api_health_metrics_report)
        app.router.add_get('/api/health/metrics/{user_id}', api_health_metrics_get)
        app.router.add_post('/api/auth/social', api_auth_social)
        app.router.add_post('/api/auth/request', api_auth_request)
        app.router.add_get('/api/auth/status/{code}', api_auth_status)
        app.router.add_post('/api/auth/link-request', api_auth_link_request)
        app.router.add_get('/api/auth/link-status/{code}', api_auth_link_status)

        runner = web.AppRunner(app)
        await runner.setup()

        # Render использует порт из переменной окружения PORT
        import os
        port = int(os.getenv('PORT', 8080))

        site = web.TCPSite(runner, '0.0.0.0', port)
        await site.start()

        logger.info(f"✅ Web server started successfully on http://0.0.0.0:{port}")
        logger.info(f"   Health check endpoints: /health, /")

        # Держим сервер запущенным
        while True:
            await asyncio.sleep(3600)

    except Exception as e:
        logger.critical(f"❌ Failed to start web server: {e}", exc_info=True)
        raise



async def api_medications_post(request: web.Request) -> web.Response:
    """POST /api/medications/{user_id} — добавить лекарство"""
    user_id = request.match_info.get('user_id')
    if not user_id:
        return json_response({'error': 'user_id required'}, status=400)
    try:
        body = await request.json()
    except Exception:
        return json_response({'error': 'invalid JSON'}, status=400)
    try:
        row = {
            'user_id': int(user_id),
            'medication_name': body.get('name') or body.get('medication_name', ''),
            'dosage': body.get('dosage', ''),
            'frequency': body.get('frequency', ''),
            'times': body.get('times', []),
            'start_date': body.get('start_date') or None,
            'end_date': body.get('end_date') or None,
            'notes': body.get('notes', ''),
            'is_active': True,
        }
        resp = await run_query(
            lambda: supabase_client.table('medications').insert(row).execute()
        )
        inserted = (resp.data or [{}])[0]
        return json_response({'ok': True, 'id': inserted.get('id')})
    except Exception as e:
        logger.error(f'Medications POST error for {user_id}: {e}', exc_info=True)
        return json_response({'error': str(e)}, status=500)


async def api_diary_post(request: web.Request) -> web.Response:
    """POST /api/diary/{user_id} — добавить запись дневника"""
    user_id = request.match_info.get('user_id')
    if not user_id:
        return json_response({'error': 'user_id required'}, status=400)
    try:
        body = await request.json()
    except Exception:
        return json_response({'error': 'invalid JSON'}, status=400)
    try:
        from datetime import date, datetime
        today = date.today().isoformat()
        now_time = datetime.now().strftime('%H:%M:%S')
        row = {
            'user_id': int(user_id),
            'entry_date': body.get('entry_date', today),
            'entry_time': body.get('entry_time', now_time),
        }
        for field in ('temperature', 'blood_pressure_sys', 'blood_pressure_dia', 'pulse', 'weight'):
            if field in body and body[field] is not None:
                row[field] = body[field]
        for field in ('mood', 'symptoms', 'notes'):
            if field in body and body[field]:
                row[field] = body[field]
        resp = await run_query(
            lambda: supabase_client.table('health_diary').insert(row).execute()
        )
        inserted = (resp.data or [{}])[0]
        return json_response({'ok': True, 'id': inserted.get('id')})
    except Exception as e:
        logger.error(f'Diary POST error for {user_id}: {e}', exc_info=True)
        return json_response({'error': str(e)}, status=500)


async def api_medications_get(request: web.Request) -> web.Response:
    """GET /api/medications/{user_id} — список активных лекарств пользователя"""
    user_id = request.match_info.get('user_id')
    if not user_id:
        return json_response({'error': 'user_id required'}, status=400)
    try:
        resp = await run_query(
            lambda: supabase_client.table('medications')
            .select('id, medication_name, dosage, frequency, times, start_date, end_date, notes')
            .eq('user_id', int(user_id))
            .eq('is_active', True)
            .order('created_at', desc=True)
            .execute()
        )
        return json_response({'records': resp.data or [], 'has_data': bool(resp.data)})
    except Exception as e:
        logger.error(f'Medications GET error for {user_id}: {e}', exc_info=True)
        return json_response({'records': [], 'has_data': False})


async def api_diary_get(request: web.Request) -> web.Response:
    """GET /api/diary/{user_id} — записи дневника здоровья"""
    user_id = request.match_info.get('user_id')
    if not user_id:
        return json_response({'error': 'user_id required'}, status=400)
    try:
        resp = await run_query(
            lambda: supabase_client.table('health_diary')
            .select('id, entry_date, entry_time, created_at, temperature, blood_pressure_sys, blood_pressure_dia, pulse, weight, mood, symptoms, notes')
            .eq('user_id', int(user_id))
            .order('entry_date', desc=True)
            .order('entry_time', desc=True)
            .limit(30)
            .execute()
        )
        rows = resp.data or []
        entries = []
        for row in rows:
            # Normalize created_at for web display
            created_at = row.get('created_at') or f"{row.get('entry_date', '')}T{row.get('entry_time', '00:00:00')}"
            entries.append({**row, 'created_at': created_at})
        return json_response({'records': entries, 'has_data': bool(entries)})
    except Exception as e:
        logger.error(f'Diary GET error for {user_id}: {e}', exc_info=True)
        return json_response({'records': [], 'has_data': False})


async def main():
    """Главная функция"""
    logger.info("=" * 60)
    logger.info("🚀 Starting Telegram Doctor Bot")
    logger.info("=" * 60)

    try:
        # Запускаем веб-сервер и бота параллельно
        # Веб-сервер всегда доступен, бот автоматически перезапускается
        await asyncio.gather(
            start_web_server(),
            start_bot(),
            cleanup_stale_sessions(),
            return_exceptions=True  # Не останавливаем всё при падении одной задачи
        )
    except Exception as e:
        logger.critical(f"❌ Fatal error in main: {e}", exc_info=True)
        raise
    finally:
        logger.info("🛑 Shutting down...")
        try:
            await bot.session.close()
        except Exception as e:
            logger.error(f"Error closing bot session: {e}")


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⚠️ Bot stopped by user (Ctrl+C)")
    except Exception as e:
        logger.critical(f"❌ Fatal error: {e}", exc_info=True)
        raise
