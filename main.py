import asyncio
import functools
import ipaddress
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramConflictError
from aiogram.types import MenuButtonDefault
from aiohttp import web

from bot.handlers import (
    basic,
    clinic_finder,
    consultation,
    fallback,
    health_diary,
    history,
    medications,
    profile,
    specialists,
)
from bot.middlewares import ConsentMiddleware, FSMTimeoutMiddleware
from config import BOT_TOKEN
from database.connection import run_query, supabase_client
from services.consent import CONSENT_VERSION, delete_all_user_data, has_consent, record_consent
from services.consultation_agent import (
    check_red_flags,
    get_anamnesis_questions,
    get_final_recommendation,
    get_patient_history,
    get_recent_health_metrics,
    parse_and_generate_questions,
)
from security.auth import (
    SCOPE_METRICS,
    SCOPE_SESSION,
    bearer_token,
    derive_web_user_id,
    issue_token,
    verify_login_widget,
    verify_token,
    verify_webapp_init_data,
)
from utils.logger import setup_logger

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
# Согласие на обработку данных — до любых обработчиков, собирающих данные о здоровье
dp.message.outer_middleware(ConsentMiddleware())
dp.callback_query.outer_middleware(ConsentMiddleware())

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
_MAX_CONSULTATION_SESSIONS = 2000

# Ссылки на фоновые задачи: без них asyncio может собрать задачу сборщиком мусора
_background_tasks: set = set()


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

# Хранилище кодов авторизации для Web — shared с bot handlers
import time as _time

# ── Rate limiting (in-memory, resets on redeploy) ──────────────────────────
from collections import defaultdict

from bot.shared import redeem_site_code, site_codes

_rate_counters: dict = defaultdict(list)  # (bucket, ip) → [timestamps]


def _client_ip(request: web.Request) -> str:
    """
    IP клиента для rate limit. На Render перед приложением стоит Cloudflare,
    который всегда перезаписывает CF-Connecting-IP реальным адресом клиента.
    Другим заголовкам не доверяем: True-Client-IP Cloudflare выставляет только
    на Enterprise-тарифе (иначе пропускает значение клиента), а X-Forwarded-For
    клиент может дописать сам, и его последнее значение — адрес прокси.
    """
    value = request.headers.get("CF-Connecting-IP", "").strip()
    if value:
        try:
            return str(ipaddress.ip_address(value))
        except ValueError:
            pass
    return request.remote or "unknown"


def _is_rate_limited(request: web.Request, bucket: str = "default", limit: int = 60, window: int = 60) -> bool:
    """Простой rate limit по IP в памяти. True — запрос надо отклонить."""
    key = (bucket, _client_ip(request))
    now = _time.time()
    window_start = now - window
    _rate_counters[key] = [t for t in _rate_counters[key] if t > window_start]
    # Чистим устаревшие ключи, чтобы память не росла бесконечно
    if len(_rate_counters) > 10_000:
        stale = [k for k, v in _rate_counters.items() if not v or v[-1] < now - 3600]
        for k in stale:
            del _rate_counters[k]
    if len(_rate_counters[key]) >= limit:
        return True
    _rate_counters[key].append(now)
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
        "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
        "Vary": "Origin",
    }


def json_response(data: dict, status: int = 200) -> web.Response:
    # CORS headers are added by cors_middleware — do not set static headers here
    return web.Response(
        text=json.dumps(data, ensure_ascii=False),
        status=status,
        content_type="application/json",
    )


# ── Авторизация API ───────────────────────────────────────────────────────────

def _unauthorized() -> web.Response:
    return json_response({"error": "unauthorized"}, status=401)


def _forbidden() -> web.Response:
    return json_response({"error": "forbidden"}, status=403)


def _token_user_id(request: web.Request, scopes: tuple[str, ...] = (SCOPE_SESSION,)) -> int | None:
    token = bearer_token(request.headers)
    return verify_token(token, scopes) if token else None


def auth_required(handler):
    """
    Требует валидный токен сессии. Кладёт user_id в request["user_id"].
    Если в URL есть {user_id} — он обязан совпадать с владельцем токена,
    иначе 403 (нельзя читать/менять чужие данные, подставив чужой ID).
    """
    @functools.wraps(handler)
    async def wrapper(request: web.Request) -> web.Response:
        uid = _token_user_id(request)
        if uid is None:
            return _unauthorized()
        path_uid = request.match_info.get("user_id")
        if path_uid is not None:
            try:
                if int(path_uid) != uid:
                    return _forbidden()
            except ValueError:
                return json_response({"error": "invalid user_id"}, status=400)
        request["user_id"] = uid
        return await handler(request)
    return wrapper


async def _consent_withdrawn(session: dict) -> bool:
    """
    Согласие вошедшего пользователя проверено при старте консультации. Если он
    отозвал его (удалил данные) посреди консультации — не продолжаем обработку
    и не сохраняем результат.
    """
    user_id = session.get("user_id")
    return bool(user_id) and not await has_consent(user_id)


def _consent_required_response() -> web.Response:
    return json_response({"error": "consent_required", "consent_version": CONSENT_VERSION}, status=403)


def consent_required(handler):
    """
    Применяется под @auth_required: без согласия на обработку данных о здоровье
    (текущей версии) запись данных запрещена — ответ 403 consent_required.
    """
    @functools.wraps(handler)
    async def wrapper(request: web.Request) -> web.Response:
        try:
            if not await has_consent(request["user_id"]):
                return _consent_required_response()
        except Exception as e:
            logger.error(f"Consent check failed: {type(e).__name__}")
            return json_response({"error": "Internal server error"}, status=500)
        return await handler(request)
    return wrapper


async def _metrics_user_id(request: web.Request, body: dict) -> int | None:
    """
    Для эндпоинтов приёма показателей (iPhone Shortcut / Apple Watch):
    принимает токен сессии ИЛИ специальный токен метрик — из заголовка
    Authorization или из поля "token" в теле (в Shortcuts так проще настроить).
    """
    token = bearer_token(request.headers) or (body.get("token") if isinstance(body, dict) else None)
    if not token:
        return None
    return verify_token(str(token), (SCOPE_SESSION, SCOPE_METRICS))


@web.middleware
async def cors_middleware(request: web.Request, handler):
    cors_headers = _get_cors_headers(request)
    if request.method == "OPTIONS":
        return web.Response(status=204, headers=cors_headers)
    if request.path.startswith("/api/") and _is_rate_limited(request, "api", limit=120, window=60):
        response = _rate_limit_response()
        for key, value in cors_headers.items():
            response.headers[key] = value
        return response
    try:
        response = await handler(request)
    except web.HTTPException as e:
        # aiohttp's own HTTP errors (404, etc.) — still attach CORS headers
        for key, value in cors_headers.items():
            e.headers[key] = value
        raise
    except Exception as e:
        logger.error(f"Unhandled exception in {request.path}: {e}", exc_info=True)
        response = web.Response(
            text=json.dumps({"error": "Internal server error"}, ensure_ascii=False),
            status=500,
            content_type="application/json",
        )
    for key, value in cors_headers.items():
        response.headers[key] = value
    return response


# HTTP сервер для Render (Health check)
async def health_check(request):
    """Endpoint для проверки здоровья сервиса"""
    return web.Response(text="OK", status=200)


# ── API endpoints ──────────────────────────────────────────────

async def api_consultation_start(request: web.Request) -> web.Response:
    """
    POST /api/consultation/start
    Гость — без токена. Авторизованный пользователь — с Authorization: Bearer,
    тогда учитываются его профиль, история и показатели. user_id из тела
    запроса НЕ принимается: только из токена.
    """
    if _is_rate_limited(request, "ai", limit=10, window=60):
        return _rate_limit_response()
    try:
        body = await request.json()
    except Exception:
        return json_response({"error": "Invalid JSON body"}, status=400)

    user_id = _token_user_id(request)
    symptoms = str(body.get("symptoms", "")).strip()

    if not symptoms:
        return json_response({"error": "Missing required field: symptoms"}, status=400)
    if len(symptoms) > 2000:
        return json_response({"error": "Symptoms text is too long (max 2000 chars)"}, status=400)

    # Согласие на обработку данных о здоровье: у вошедшего пользователя — из базы,
    # у гостя — подтверждение текущей версии текста в самом запросе (галочка).
    guest_consent = False
    if user_id:
        if not await has_consent(user_id):
            return _consent_required_response()
    elif body.get("consent_version") == CONSENT_VERSION:
        guest_consent = True
    else:
        return _consent_required_response()

    # Получаем профиль пользователя из Supabase (только если есть user_id)
    user_profile = {}
    patient_history = []
    health_metrics = {"has_any_data": False}
    if user_id:
        try:
            resp = await run_query(lambda: supabase_client.table("user_profiles").select("*").eq("user_id", user_id).limit(1).execute())
            user_profile = (resp.data[0] if resp.data else {})
        except Exception:
            user_profile = {}
        patient_history = await run_query(get_patient_history, user_id, supabase_client)
        health_metrics = await run_query(get_recent_health_metrics, user_id, supabase_client, hours=24)

    # Шаг 1: Красные флаги (с учётом метрик)
    try:
        red_flag_result = check_red_flags(symptoms, health_metrics=health_metrics)
    except Exception as e:
        logger.error(f"check_red_flags failed: {e}", exc_info=True)
        return json_response({"error": "AI service temporarily unavailable"}, status=503)
    red_flag = red_flag_result.get("red_flag", False)
    needs_fresh_metrics = red_flag_result.get("needs_fresh_metrics", [])

    # Шаг 2: Генерация уточняющих вопросов
    try:
        questions = await parse_and_generate_questions(symptoms, user_profile, patient_history)
    except Exception as e:
        logger.error(f"parse_and_generate_questions failed: {e}", exc_info=True)
        return json_response({"error": "AI service temporarily unavailable"}, status=503)

    if questions is None:
        # AI determined the input isn't a medical symptom description
        logger.info("Non-medical input rejected")
        return json_response({
            "error": "not_medical",
            "message": "Похоже, это не описание симптомов. Опишите, что вас беспокоит (например: болит голова, температура, кашель).",
        }, status=422)

    session_id = str(uuid.uuid4())
    # Ограничиваем число сессий в памяти: при переполнении удаляем самые старые
    if len(consultation_sessions) >= _MAX_CONSULTATION_SESSIONS:
        oldest = sorted(consultation_sessions, key=lambda k: consultation_sessions[k].get("_created_at"))
        for sid in oldest[: len(consultation_sessions) - _MAX_CONSULTATION_SESSIONS + 1]:
            consultation_sessions.pop(sid, None)
    consultation_sessions[session_id] = {
        "_created_at": datetime.now(timezone.utc),
        "user_id": user_id,
        "symptoms": symptoms,
        "user_profile": user_profile,
        "questions": questions,
        "answers": [],
        "duration": None,
        "anamnesis_questions": [],
        "anamnesis_answers": [],
        "health_metrics": health_metrics,
        "red_flag": red_flag,
    }
    if guest_consent:
        source = body.get("consent_source") if body.get("consent_source") in ("web", "miniapp") else "web"
        try:
            await record_consent(None, source, session_id=session_id)
        except Exception as e:
            logger.error(f"Guest consent save failed: {type(e).__name__}")

    return json_response({
        "session_id": session_id,
        "questions": questions,
        "red_flag": red_flag,
        "needs_fresh_metrics": needs_fresh_metrics,
    })


def _get_owned_session(request: web.Request, session_id) -> dict | None:
    """
    Возвращает сессию консультации, если она принадлежит текущему пользователю.
    Гостевые сессии (без user_id) доступны по одному session_id (это UUID4).
    """
    if not session_id:
        return None
    session = consultation_sessions.get(str(session_id))
    if not session:
        return None
    owner = session.get("user_id")
    if owner is not None and _token_user_id(request) != owner:
        return None
    return session


async def api_consultation_answer(request: web.Request) -> web.Response:
    """POST /api/consultation/answer"""
    try:
        body = await request.json()
    except Exception:
        return json_response({"error": "Invalid JSON"}, status=400)

    session_id = body.get("session_id")
    if not session_id:
        return json_response({"error": "session_id is required"}, status=400)

    session = _get_owned_session(request, session_id)
    if not session:
        return json_response({"error": "Session not found"}, status=404)
    if await _consent_withdrawn(session):
        return _consent_required_response()

    try:
        answers = body.get("answers", [])
        if not isinstance(answers, list):
            return json_response({"error": "'answers' must be a list"}, status=400)
        questions = session["questions"]
        # Ответов не может быть больше, чем задано вопросов: иначе большой
        # список из запроса целиком остался бы в памяти до истечения сессии
        answers = answers[:max(len(questions), 1)]

        # Сохраняем каждый ответ, сопоставляя с вопросом по индексу
        paired = []
        for i, ans in enumerate(answers):
            q_text = questions[i]["question"] if i < len(questions) else ""
            paired.append({"question": q_text, "answer": str(ans)[:500]})
        session["answers"] = paired

        return json_response({"next_step": "duration"})
    except Exception as e:
        logger.error(f"Consultation answer error: {e}", exc_info=True)
        return json_response({"error": "Internal server error"}, status=500)


async def api_consultation_duration(request: web.Request) -> web.Response:
    """POST /api/consultation/duration"""
    try:
        body = await request.json()
    except Exception:
        return json_response({"error": "Invalid JSON"}, status=400)

    session_id = body.get("session_id")
    duration = str(body.get("duration", ""))[:200]

    if not session_id:
        return json_response({"error": "session_id is required"}, status=400)

    session = _get_owned_session(request, session_id)
    if not session:
        return json_response({"error": "Session not found"}, status=404)
    if await _consent_withdrawn(session):
        return _consent_required_response()
    if _is_rate_limited(request, "ai", limit=10, window=60):
        return _rate_limit_response()

    try:
        session["duration"] = duration

        # Генерация анамнестических вопросов
        anamnesis_questions = await get_anamnesis_questions(session["symptoms"])
        session["anamnesis_questions"] = anamnesis_questions

        # Нормализуем ключ: question → text для Mini App
        normalized = [
            {"text": q.get("question", q.get("text", "")), "options": q.get("options", [])}
            for q in anamnesis_questions
        ]

        return json_response({"anamnesis_questions": normalized, "needs_fresh_metrics": []})
    except Exception as e:
        logger.error(f"Consultation duration error: {e}", exc_info=True)
        return json_response({"error": "Internal server error"}, status=500)


async def api_consultation_result(request: web.Request) -> web.Response:
    """POST /api/consultation/result"""
    try:
        body = await request.json()
    except Exception:
        return json_response({"error": "Invalid JSON"}, status=400)

    session_id = body.get("session_id")
    if not session_id:
        return json_response({"error": "session_id is required"}, status=400)

    session = _get_owned_session(request, session_id)
    if not session:
        return json_response({"error": "Session not found"}, status=404)
    if await _consent_withdrawn(session):
        return _consent_required_response()
    if _is_rate_limited(request, "ai", limit=10, window=60):
        return _rate_limit_response()

    try:
        # Анамнестические ответы могут быть переданы в теле запроса (плоский список строк или список dict)
        raw_anamnesis = body.get("anamnesis_answers", session.get("anamnesis_answers", []))
        if not isinstance(raw_anamnesis, list):
            raw_anamnesis = []
        raw_anamnesis = raw_anamnesis[:10]
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

        user_profile = session.get("user_profile") or {}

        recommendation = await get_final_recommendation(
            all_data,
            user_profile,
            health_metrics=session.get("health_metrics"),
            red_flag=bool(session.get("red_flag")),
        )

        # Сохраняем в Supabase (только для авторизованных пользователей)
        specialists_raw = recommendation.get("specialists", [])
        consultation_id = None
        if session.get("user_id"):
            try:
                recommended_doctor = specialists_raw[0]["name"] if specialists_raw else "Терапевт"
                saved = await run_query(lambda: supabase_client.table("consultations").insert({
                    "user_id": session["user_id"],
                    "symptoms": json.dumps({"text": session["symptoms"], "history": [a for a in session["answers"] if a]}, ensure_ascii=False),
                    "questions_answers": json.dumps(all_data, ensure_ascii=False),
                    "recommended_doctor": recommended_doctor,
                    "urgency_level": recommendation.get("urgency", "medium"),
                }).execute())
                consultation_id = (saved.data or [{}])[0].get("id")
            except Exception as e:
                logger.error(f"Failed to save consultation to Supabase: {e}", exc_info=True)

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
            "consultation_id": consultation_id,
            "recommendation": recommendation.get("recommendation", recommendation.get("urgency_reason", "")),
            "specialists": specialists_out,
            "urgency": recommendation.get("urgency", "medium"),
            "needs_fresh_metrics": recommendation.get("needs_fresh_metrics", []),
            "needs_fresh_metrics_message": recommendation.get("needs_fresh_metrics_message", ""),
        })

    except Exception as e:
        logger.error(f"Consultation result error: {e}", exc_info=True)
        return json_response({"error": "Internal server error"}, status=500)


_PROFILE_FIELDS = [
    "full_name", "phone", "birthdate", "gender", "height", "weight",
    "chronic_diseases", "drug_allergies", "smoking", "hereditary", "physical_activity",
]


@auth_required
async def api_profile_get(request: web.Request) -> web.Response:
    """GET /api/profile/{user_id} — читает из таблицы user_profiles по user_id"""
    user_id = request["user_id"]

    try:
        resp = await run_query(
            lambda: supabase_client.table("user_profiles")
            .select(", ".join(_PROFILE_FIELDS))
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            return json_response({"exists": False, "profile": None})

        row = rows[0]
        profile = {f: row.get(f) for f in _PROFILE_FIELDS}
        return json_response({"exists": True, "profile": profile})
    except Exception as e:
        logger.error(f"Profile GET error for user {user_id}: {e}", exc_info=True)
        return json_response({"error": "Internal server error"}, status=500)


@auth_required
@consent_required
async def api_profile_post(request: web.Request) -> web.Response:
    """POST /api/profile/{user_id} — upsert в таблицу user_profiles по user_id"""
    user_id = request["user_id"]

    try:
        body = await request.json()
    except Exception:
        return json_response({"error": "Invalid JSON"}, status=400)
    if not isinstance(body, dict):
        return json_response({"error": "Invalid JSON"}, status=400)

    # Берём только допустимые поля профиля
    update_data = {k: v for k, v in body.items() if k in _PROFILE_FIELDS}
    if not update_data:
        return json_response({"error": "No valid profile fields provided"}, status=400)

    update_data["user_id"] = user_id
    logger.info(f"Profile POST: user_id={user_id}, fields={sorted(update_data)}")

    try:
        await run_query(lambda: supabase_client.table("user_profiles").upsert(update_data, on_conflict="user_id").execute())
        return json_response({"status": "ok"})
    except Exception as e:
        logger.error(f"Profile POST error for user {user_id}: {e}", exc_info=True)
        return json_response({"error": "Internal server error"}, status=500)


def _fetch_heartrate_records(user_id: int) -> list:
    """Синхронный запрос к Supabase — вызывать только через run_query."""
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


@auth_required
async def api_health_heartrate_get(request: web.Request) -> web.Response:
    """GET /api/health/heartrate/{user_id}"""
    user_id = request["user_id"]
    try:
        records = await run_query(_fetch_heartrate_records, user_id)
    except Exception as e:
        if 'Name or service not known' in str(e):
            logger.warning(f"Heartrate GET DNS error for user_id={user_id}, retrying in 1s: {e}")
            await asyncio.sleep(1)
            try:
                records = await run_query(_fetch_heartrate_records, user_id)
            except Exception as retry_e:
                logger.error(f"Heartrate GET retry failed for user_id={user_id}: {retry_e}", exc_info=True)
                return json_response({'error': 'Internal server error'}, status=500)
        else:
            logger.error(f"Heartrate GET error for user_id={user_id}: {e}", exc_info=True)
            return json_response({'error': 'Internal server error'}, status=500)

    return json_response({'records': records, 'has_data': len(records) > 0})


async def api_health_heartrate(request: web.Request) -> web.Response:
    """POST /api/health/heartrate — требует токен сессии или токен метрик."""
    try:
        data = await request.json()
    except Exception:
        return json_response({'error': 'Invalid JSON'}, status=400)
    if not isinstance(data, dict):
        return json_response({'error': 'Invalid JSON'}, status=400)

    user_id = await _metrics_user_id(request, data)
    if user_id is None:
        return _unauthorized()
    if not await has_consent(user_id):
        return _consent_required_response()

    try:
        hr = float(data.get('heartrate'))
    except (TypeError, ValueError):
        return json_response({'error': 'heartrate required'}, status=400)
    if not 20 <= hr <= 250:
        return json_response({'error': 'heartrate out of range'}, status=400)
    timestamp = data.get('timestamp') or datetime.now(timezone.utc).isoformat()

    try:
        record = {
            'user_id': user_id,
            'metric_type': 'heartrate',
            'value': hr,
            'unit': 'bpm',
            'recorded_at': timestamp,
            'source': 'apple_watch',
        }
        await run_query(lambda: supabase_client.table('health_metrics').insert(record).execute())

        if hr > 120 or hr < 50:
            msg = f"🚨 Пульс: {hr:.0f} уд/мин! Значительно отличается от нормы. Рекомендуем обратиться к врачу."
        elif hr > 100:
            msg = f"❤️ Пульс получен: {hr:.0f} уд/мин ⚠️ Немного выше нормы. Отдохните."
        else:
            msg = f"❤️ Пульс получен: {hr:.0f} уд/мин ✅ В норме"
        await bot.send_message(user_id, msg)

        return json_response({'status': 'ok', 'message': f'Пульс сохранён: {hr:.0f} уд/мин'})
    except Exception as e:
        logger.error(f"Health heartrate error: {e}", exc_info=True)
        return json_response({'error': 'Internal server error'}, status=500)


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
    """
    POST /api/health/metrics — тихое сохранение + отложенный алерт при отклонениях.
    Требует токен сессии или токен метрик (заголовок Authorization или поле "token").
    """
    try:
        data = await request.json()
    except Exception:
        return json_response({'error': 'Invalid JSON'}, status=400)
    if not isinstance(data, dict):
        return json_response({'error': 'Invalid JSON'}, status=400)

    user_id = await _metrics_user_id(request, data)
    if user_id is None:
        return _unauthorized()
    if not await has_consent(user_id):
        return _consent_required_response()
    timestamp = data.get('timestamp') or datetime.now(timezone.utc).isoformat()

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
        if not 0 < value < 1_000_000:
            continue
        row = {
            'user_id': user_id,
            'metric_type': metric_type,
            'value': value,
            'unit': unit,
            'recorded_at': timestamp,
            'source': 'apple_watch',
        }
        records_to_insert.append(row)
        received[field] = value

    if not records_to_insert:
        return json_response({'error': 'No valid metrics provided'}, status=400)

    # Тихое сохранение в Supabase
    try:
        await run_query(lambda: supabase_client.table('health_metrics').insert(records_to_insert).execute())
    except Exception as e:
        logger.error(f"Health metrics insert error: {e}", exc_info=True)
        return json_response({'error': 'Internal server error'}, status=500)

    logger.info(f"Silent save for user {user_id}: {len(records_to_insert)} metrics")

    # Проверка отклонений — если есть, запускаем отложенный алерт через 2 минуты
    if _has_deviation(received):
        abnormal = _get_abnormal_metrics(received)
        _spawn(send_delayed_alert(user_id, received, delay=120))
        _spawn(send_remeasure_reminder(user_id, abnormal, delay=14400))
        logger.info(f"Deviation detected for user_id={user_id}, alert in 120s, reminder in 4h")

    return json_response({'status': 'ok', 'saved': len(records_to_insert)})


@auth_required
async def api_health_metrics_report(request: web.Request) -> web.Response:
    """POST /api/health/metrics/report/{user_id} — ручной отчёт о последних метриках"""
    user_id = request["user_id"]
    if _is_rate_limited(request, "report", limit=5, window=60):
        return _rate_limit_response()

    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        resp = await run_query(
            lambda: supabase_client.table('health_metrics')
            .select('metric_type, value, recorded_at')
            .eq('user_id', user_id)
            .gte('recorded_at', cutoff)
            .order('recorded_at', desc=True)
            .execute()
        )
        rows = resp.data or []
    except Exception as e:
        logger.error(f"Report fetch error for user_id={user_id}: {e}", exc_info=True)
        return json_response({'error': 'Internal server error'}, status=500)

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
        return json_response({'error': 'Telegram send failed'}, status=500)

    return json_response({'status': 'ok', 'message': 'Report sent'})


@auth_required
async def api_health_metrics_get(request: web.Request) -> web.Response:
    """GET /api/health/metrics/{user_id}?type=metric_type&limit=10"""
    user_id = request["user_id"]

    metric_type = request.rel_url.query.get('type')
    try:
        limit = max(1, min(int(request.rel_url.query.get('limit', 10)), 200))
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
        resp = await run_query(query.execute)
        records = resp.data or []
        return json_response({'records': records, 'has_data': len(records) > 0})
    except Exception as e:
        logger.error(f"Health metrics GET error user_id={user_id}: {e}", exc_info=True)
        return json_response({'error': 'Internal server error'}, status=500)


async def _check_anamnesis_fields():
    """Проверяет наличие полей анамнеза в user_profiles (миграции выполняются вручную)."""
    try:
        await run_query(lambda: supabase_client.table("user_profiles").select(
            "chronic_diseases, drug_allergies, smoking, hereditary"
        ).limit(1).execute())
        logger.info("✅ Anamnesis fields present in user_profiles")
    except Exception as e:
        logger.error(
            f"MISSING FIELDS in user_profiles: {e}. "
            "Run migration_add_anamnesis_fields.sql in Supabase SQL Editor."
        )


@auth_required
async def api_consultation_feedback(request: web.Request) -> web.Response:
    """POST /api/consultation/feedback — оценка СВОЕЙ консультации (good/bad)"""
    try:
        body = await request.json()
    except Exception:
        return json_response({"error": "Invalid JSON"}, status=400)

    consultation_id = body.get("consultation_id")
    rating = body.get("rating")  # "good" | "bad"

    if not consultation_id or rating not in ("good", "bad"):
        return json_response({"error": "consultation_id and rating (good|bad) required"}, status=400)

    user_id = request["user_id"]
    try:
        resp = await run_query(
            lambda: supabase_client.table("consultations")
            .update({"rating": rating})
            .eq("id", consultation_id)
            .eq("user_id", user_id)
            .execute()
        )
        if not resp.data:
            return json_response({"error": "Consultation not found"}, status=404)
        return json_response({"status": "ok"})
    except Exception as e:
        logger.error(f"Feedback error: {e}", exc_info=True)
        return json_response({"error": "Internal server error"}, status=500)


@auth_required
async def api_consultations_get(request: web.Request) -> web.Response:
    """GET /api/consultations/{user_id} — история консультаций для Mini App."""
    user_id = request["user_id"]
    try:
        resp = await run_query(
            lambda: supabase_client.table('consultations')
            .select('id, symptoms, recommended_doctor, urgency_level, created_at')
            .eq('user_id', user_id)
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
                elif symptoms_parsed.get('history'):
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



# ── Вход и привязка аккаунтов ─────────────────────────────────────────────────

async def _redeem_code_from_request(request: web.Request) -> tuple[dict | None, web.Response | None]:
    """Общая часть входа и привязки по коду из бота: лимиты + погашение кода."""
    if _is_rate_limited(request, "code", limit=10, window=60):
        return None, _rate_limit_response()
    try:
        body = await request.json()
    except Exception:
        return None, json_response({"error": "invalid json"}, status=400)
    entry = redeem_site_code(str(body.get("code", "")) if isinstance(body, dict) else "")
    if not entry:
        return None, json_response({"error": "invalid_code", "message": "Код неверный или истёк"}, status=400)
    return entry, None


def _session_payload(user_id: int, **user_fields) -> dict:
    """Единый формат ответа при успешном входе: токен + данные пользователя."""
    return {
        "token": issue_token(user_id),
        "id": user_id,
        "auth_date": int(datetime.now(timezone.utc).timestamp()),
        **user_fields,
    }


async def api_auth_telegram_webapp(request: web.Request) -> web.Response:
    """
    POST /api/auth/telegram-webapp {"init_data": Telegram.WebApp.initData}
    Вход из Telegram Mini App. Подпись initData проверяется по BOT_TOKEN.
    """
    if _is_rate_limited(request, "auth", limit=20, window=60):
        return _rate_limit_response()
    try:
        body = await request.json()
    except Exception:
        return json_response({"error": "invalid json"}, status=400)
    user = verify_webapp_init_data(str(body.get("init_data", "")))
    if not user:
        return _unauthorized()
    return json_response(_session_payload(
        int(user["id"]),
        first_name=user.get("first_name"),
        last_name=user.get("last_name"),
        username=user.get("username"),
        photo_url=user.get("photo_url"),
        provider="telegram",
    ))


async def api_auth_telegram_widget(request: web.Request) -> web.Response:
    """
    POST /api/auth/telegram-widget {id, first_name, ..., auth_date, hash}
    Вход на сайте через Telegram Login Widget. Подпись проверяется по BOT_TOKEN.
    """
    if _is_rate_limited(request, "auth", limit=20, window=60):
        return _rate_limit_response()
    try:
        body = await request.json()
    except Exception:
        return json_response({"error": "invalid json"}, status=400)
    user = verify_login_widget(body if isinstance(body, dict) else {})
    if not user:
        return _unauthorized()
    return json_response(_session_payload(
        int(user["id"]),
        first_name=user.get("first_name"),
        last_name=user.get("last_name"),
        username=user.get("username"),
        photo_url=user.get("photo_url"),
        provider="telegram",
    ))


async def api_auth_social(request: web.Request) -> web.Response:
    """
    POST /api/auth/social {"access_token": <Supabase session.access_token>}
    Вход через Google/email (Supabase Auth). Токен проверяется у Supabase —
    email/ID из тела запроса больше НЕ принимаются на веру.
    """
    if _is_rate_limited(request, "auth", limit=20, window=60):
        return _rate_limit_response()
    try:
        body = await request.json()
    except Exception:
        return json_response({"error": "invalid json"}, status=400)

    access_token = str(body.get("access_token", "")).strip()
    if not access_token:
        return json_response({"error": "access_token required"}, status=400)

    try:
        auth_resp = await run_query(supabase_client.auth.get_user, access_token)
        sb_user = auth_resp.user if auth_resp else None
    except Exception as e:
        logger.warning(f"Social auth: Supabase token rejected: {type(e).__name__}")
        sb_user = None
    if not sb_user:
        return _unauthorized()

    meta = sb_user.user_metadata or {}
    email = (sb_user.email or "").lower()
    name = str(meta.get("full_name") or meta.get("name") or email.split("@")[0]).strip()
    avatar = meta.get("avatar_url") or meta.get("picture")
    provider = (sb_user.app_metadata or {}).get("provider", "email")
    user_id = derive_web_user_id(sb_user.id)

    first_name = name.split()[0] if name else email.split("@")[0]
    last_name = " ".join(name.split()[1:]) or None

    try:
        existing = await run_query(
            lambda: supabase_client.table("user_profiles")
                .select("user_id").eq("user_id", user_id).limit(1).execute()
        )
        is_new = not existing.data
        if is_new:
            await run_query(
                lambda: supabase_client.table("user_profiles").insert({
                    "user_id": user_id,
                    "full_name": name or first_name,
                }).execute()
            )
            logger.info(f"Social auth: created user_id={user_id} via {provider}")
    except Exception as e:
        logger.error(f"Social auth error: {e}", exc_info=True)
        return json_response({"error": "Internal server error"}, status=500)

    return json_response(_session_payload(
        user_id,
        first_name=first_name,
        last_name=last_name,
        username=None,
        photo_url=avatar,
        provider=provider,
        email=email,
        is_new=is_new,
    ))


async def api_auth_code(request: web.Request) -> web.Response:
    """
    POST /api/auth/code {"code": "K7RM-4QXA"} — вход на сайт по коду, который
    бот прислал пользователю в его чат (/login). Код одноразовый, 5 минут.
    """
    entry, error = await _redeem_code_from_request(request)
    if error is not None:
        return error
    logger.info(f"Site code login for telegram user {entry['telegram_id']}")
    return json_response(_session_payload(
        int(entry["telegram_id"]),
        first_name=entry["first_name"],
        last_name=entry["last_name"],
        username=entry["username"],
        photo_url=None,
        provider="telegram",
    ))


_LINK_MERGE_FIELDS = [
    "birthdate", "gender", "height", "weight", "phone",
    "chronic_diseases", "drug_allergies", "smoking", "hereditary", "physical_activity",
]


@auth_required
@consent_required
async def api_auth_link(request: web.Request) -> web.Response:
    """
    POST /api/auth/link {"code": "K7RM-4QXA"} — привязать Telegram к ТЕКУЩЕМУ
    веб-аккаунту кодом из бота. Пустые поля веб-профиля заполняются из
    Telegram-профиля того же человека (код получил владелец Telegram).
    """
    web_id = request["user_id"]
    entry, error = await _redeem_code_from_request(request)
    if error is not None:
        return error
    tg_id = int(entry["telegram_id"])
    if tg_id == web_id:
        return json_response({"error": "Этот аккаунт уже является Telegram-аккаунтом"}, status=400)

    try:
        tg_resp = await run_query(lambda: supabase_client.table("user_profiles").select("*").eq("user_id", tg_id).limit(1).execute())
        web_resp = await run_query(lambda: supabase_client.table("user_profiles").select("*").eq("user_id", web_id).limit(1).execute())
        tg_profile = tg_resp.data[0] if tg_resp.data else {}
        web_profile = web_resp.data[0] if web_resp.data else {}

        update_web = {"linked_telegram_id": str(tg_id)}
        for field in _LINK_MERGE_FIELDS + ["full_name"]:
            if tg_profile.get(field) and not web_profile.get(field):
                update_web[field] = tg_profile[field]

        await run_query(lambda: supabase_client.table("user_profiles").upsert(
            {"user_id": web_id, **update_web}, on_conflict="user_id").execute())
        await run_query(lambda: supabase_client.table("user_profiles").upsert(
            {"user_id": tg_id, "linked_web_id": str(web_id)}, on_conflict="user_id").execute())
    except Exception as e:
        logger.error(f"Account link error: {e}", exc_info=True)
        return json_response({"error": "Internal server error"}, status=500)

    logger.info(f"Accounts linked: tg={tg_id} <-> web={web_id}")
    try:
        await bot.send_message(tg_id, "✅ Ваш Telegram привязан к аккаунту на сайте Symed.")
    except Exception as e:
        logger.warning(f"Link notification failed for {tg_id}: {e}")
    return json_response({"linked": True, "telegram_id": tg_id})


@auth_required
async def api_auth_me(request: web.Request) -> web.Response:
    """GET /api/auth/me — проверка токена; возвращает user_id владельца."""
    return json_response({"id": request["user_id"]})


@auth_required
async def api_auth_metrics_token(request: web.Request) -> web.Response:
    """
    GET /api/auth/metrics-token — токен ТОЛЬКО для отправки показателей
    (iPhone Shortcut / Apple Watch), действует 180 дней. Им нельзя читать данные.
    """
    token = issue_token(request["user_id"], scope=SCOPE_METRICS, ttl=180 * 24 * 3600)
    return json_response({"token": token, "expires_in": 180 * 24 * 3600})


@auth_required
async def api_consent_get(request: web.Request) -> web.Response:
    """GET /api/consent — дал ли пользователь согласие на текущую версию текста."""
    try:
        accepted = await has_consent(request["user_id"])
    except Exception as e:
        logger.error(f"Consent GET failed: {type(e).__name__}")
        return json_response({"error": "Internal server error"}, status=500)
    return json_response({"accepted": accepted, "version": CONSENT_VERSION})


@auth_required
async def api_consent_post(request: web.Request) -> web.Response:
    """POST /api/consent {"version", "source": "web"|"miniapp"} — фиксирует согласие."""
    if _is_rate_limited(request, "consent", limit=10, window=60):
        return _rate_limit_response()
    try:
        body = await request.json()
    except Exception:
        return json_response({"error": "Invalid JSON"}, status=400)
    if not isinstance(body, dict) or body.get("version") != CONSENT_VERSION:
        return json_response({"error": "outdated_consent_version", "version": CONSENT_VERSION}, status=409)
    source = body.get("source") if body.get("source") in ("web", "miniapp") else "web"
    try:
        await record_consent(request["user_id"], source)
    except Exception as e:
        logger.error(f"Consent POST failed: {type(e).__name__}")
        return json_response({"error": "Internal server error"}, status=500)
    return json_response({"accepted": True, "version": CONSENT_VERSION})


@auth_required
async def api_account_delete(request: web.Request) -> web.Response:
    """DELETE /api/account — удаляет все данные пользователя и отзывает согласие."""
    user_id = request["user_id"]
    # Незавершённые консультации в памяти тоже содержат данные о здоровье
    for sid, session in list(consultation_sessions.items()):
        if session.get("user_id") == user_id:
            consultation_sessions.pop(sid, None)
    try:
        await delete_all_user_data(user_id)
    except Exception as e:
        logger.error(f"Account delete failed: {type(e).__name__}")
        return json_response({"error": "Internal server error"}, status=500)
    return json_response({"deleted": True})


async def cleanup_stale_sessions():
    """Удаляет сессии консультаций старше 2 часов из памяти."""
    while True:
        await asyncio.sleep(3600)  # каждый час
        now = datetime.now(timezone.utc)
        stale = []
        for sid, session in list(consultation_sessions.items()):
            created = session.get("_created_at")
            if created and (now - created).total_seconds() > 7200:
                stale.append(sid)
        for sid in stale:
            consultation_sessions.pop(sid, None)
        for code, entry in list(site_codes.items()):
            if _time.time() - entry["created_at"] > 300:
                site_codes.pop(code, None)
        if stale:
            logger.info(f"Cleaned up {len(stale)} stale consultation sessions")


SUPABASE_KEEPALIVE_INTERVAL = 12 * 3600  # 12 часов


async def _ping_database() -> bool:
    """Лёгкий запрос к базе. Возвращает True, если Supabase ответил."""
    try:
        await run_query(lambda: supabase_client.table("user_profiles").select("user_id").limit(1).execute())
        return True
    except Exception as e:
        # Пишем только тип ошибки: в тексте исключения может быть адрес базы
        logger.warning(f"Supabase keepalive ping failed: {type(e).__name__}")
        return False


async def supabase_keepalive():
    """
    Бесплатный Supabase ставит проект на паузу после 7 дней без обращений к
    базе. UptimeRobot будит только Render (/health в базу не ходит), поэтому
    раз в 12 часов делаем маленький запрос — это считается активностью.
    """
    await asyncio.sleep(60)  # даём сервису спокойно стартовать
    while True:
        if await _ping_database():
            logger.info("Supabase keepalive: ok")
        await asyncio.sleep(SUPABASE_KEEPALIVE_INTERVAL)


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

        # API эндпоинты
        app.router.add_post('/api/consultation/start', api_consultation_start)
        app.router.add_post('/api/consultation/answer', api_consultation_answer)
        app.router.add_post('/api/consultation/duration', api_consultation_duration)
        app.router.add_post('/api/consultation/result', api_consultation_result)
        app.router.add_post('/api/consultation/feedback', api_consultation_feedback)
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
        app.router.add_post('/api/auth/telegram-webapp', api_auth_telegram_webapp)
        app.router.add_post('/api/auth/telegram-widget', api_auth_telegram_widget)
        app.router.add_get('/api/auth/me', api_auth_me)
        app.router.add_get('/api/auth/metrics-token', api_auth_metrics_token)
        app.router.add_post('/api/auth/code', api_auth_code)
        app.router.add_post('/api/auth/link', api_auth_link)
        app.router.add_get('/api/consent', api_consent_get)
        app.router.add_post('/api/consent', api_consent_post)
        app.router.add_delete('/api/account', api_account_delete)

        runner = web.AppRunner(app)
        await runner.setup()

        # Render использует порт из переменной окружения PORT
        import os
        port = int(os.getenv('PORT', '8080'))

        site = web.TCPSite(runner, '0.0.0.0', port)
        await site.start()

        logger.info(f"✅ Web server started successfully on http://0.0.0.0:{port}")
        logger.info("   Health check endpoints: /health, /")

        # Держим сервер запущенным
        while True:
            await asyncio.sleep(3600)

    except Exception as e:
        logger.critical(f"❌ Failed to start web server: {e}", exc_info=True)
        raise



@auth_required
@consent_required
async def api_medications_post(request: web.Request) -> web.Response:
    """POST /api/medications/{user_id} — добавить лекарство"""
    user_id = request["user_id"]
    try:
        body = await request.json()
    except Exception:
        return json_response({'error': 'invalid JSON'}, status=400)
    try:
        row = {
            'user_id': user_id,
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
        return json_response({'error': 'Internal server error'}, status=500)


@auth_required
@consent_required
async def api_diary_post(request: web.Request) -> web.Response:
    """POST /api/diary/{user_id} — добавить запись дневника"""
    user_id = request["user_id"]
    try:
        body = await request.json()
    except Exception:
        return json_response({'error': 'invalid JSON'}, status=400)
    try:
        from datetime import date, datetime
        today = date.today().isoformat()
        now_time = datetime.now().strftime('%H:%M:%S')
        row = {
            'user_id': user_id,
            'entry_date': body.get('entry_date', today),
            'entry_time': body.get('entry_time', now_time),
        }
        for field in ('temperature', 'blood_pressure_sys', 'blood_pressure_dia', 'pulse', 'weight'):
            if field in body and body[field] is not None:
                row[field] = body[field]
        for field in ('mood', 'symptoms', 'notes'):
            if body.get(field):
                row[field] = body[field]
        resp = await run_query(
            lambda: supabase_client.table('health_diary').insert(row).execute()
        )
        inserted = (resp.data or [{}])[0]
        return json_response({'ok': True, 'id': inserted.get('id')})
    except Exception as e:
        logger.error(f'Diary POST error for {user_id}: {e}', exc_info=True)
        return json_response({'error': 'Internal server error'}, status=500)


@auth_required
async def api_medications_get(request: web.Request) -> web.Response:
    """GET /api/medications/{user_id} — список активных лекарств пользователя"""
    user_id = request["user_id"]
    try:
        resp = await run_query(
            lambda: supabase_client.table('medications')
            .select('id, medication_name, dosage, frequency, times, start_date, end_date, notes')
            .eq('user_id', user_id)
            .eq('is_active', True)
            .order('created_at', desc=True)
            .execute()
        )
        return json_response({'records': resp.data or [], 'has_data': bool(resp.data)})
    except Exception as e:
        logger.error(f'Medications GET error for {user_id}: {e}', exc_info=True)
        return json_response({'records': [], 'has_data': False})


@auth_required
async def api_diary_get(request: web.Request) -> web.Response:
    """GET /api/diary/{user_id} — записи дневника здоровья"""
    user_id = request["user_id"]
    try:
        resp = await run_query(
            lambda: supabase_client.table('health_diary')
            .select('id, entry_date, entry_time, created_at, temperature, blood_pressure_sys, blood_pressure_dia, pulse, weight, mood, symptoms, notes')
            .eq('user_id', user_id)
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
        # Запускаем веб-сервер, бота и фоновую очистку параллельно.
        # return_exceptions=True нужен, чтобы падение одной задачи не отменило
        # остальные немедленно — но результаты нужно проверить явно, иначе
        # критичный сбой (например, падение polling бота) останется незамеченным
        # и процесс продолжит "жить" в полумёртвом состоянии.
        task_names = ("web_server", "bot", "cleanup_stale_sessions", "supabase_keepalive")
        results = await asyncio.gather(
            start_web_server(),
            start_bot(),
            cleanup_stale_sessions(),
            supabase_keepalive(),
            return_exceptions=True
        )
        for name, result in zip(task_names, results):
            if isinstance(result, Exception):
                logger.critical(f"❌ Task '{name}' failed: {result}", exc_info=result)
                raise result
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
