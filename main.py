import asyncio
import json
import logging
import uuid
from datetime import datetime
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import BOT_TOKEN
from bot.handlers import basic, profile, consultation, specialists, history, medications, health_diary, clinic_finder
from bot.middlewares import FSMTimeoutMiddleware
from utils.logger import setup_logger
from services.consultation_agent import (
    check_red_flags,
    parse_and_generate_questions,
    get_anamnesis_questions,
    get_final_recommendation,
    get_patient_history,
)
from database.connection import supabase_client


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
dp.include_router(consultation.router) # Консультации (должен быть последним)


# Хранилище сессий в памяти (для MVP)
sessions: dict = {}

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
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
    if request.method == "OPTIONS":
        return web.Response(status=204, headers=CORS_HEADERS)
    response = await handler(request)
    for key, value in CORS_HEADERS.items():
        response.headers[key] = value
    return response


# HTTP сервер для Render (Health check)
async def health_check(request):
    """Endpoint для проверки здоровья сервиса"""
    return web.Response(text="OK", status=200)


# ── API endpoints ──────────────────────────────────────────────

async def api_consultation_start(request: web.Request) -> web.Response:
    """POST /api/consultation/start"""
    try:
        body = await request.json()
    except Exception as e:
        logger.warning(f"Consultation start: failed to parse JSON body: {e}")
        return json_response({"error": "Invalid JSON body"}, status=400)

    logger.info(f"Consultation start request body: {body}")

    user_id = body.get("user_id")
    symptoms = body.get("symptoms", "").strip()

    missing = []
    if not user_id:
        missing.append("user_id")
    if not symptoms:
        missing.append("symptoms")
    if missing:
        logger.warning(f"Consultation start: missing fields {missing}, body={body}")
        return json_response(
            {"error": f"Missing required fields: {', '.join(missing)}"},
            status=400,
        )

    # Получаем профиль пользователя из Supabase
    try:
        resp = supabase_client.table("user_profiles").select("*").eq("user_id", user_id).single().execute()
        user_profile = resp.data or {}
    except Exception:
        user_profile = {}

    # История консультаций
    patient_history = get_patient_history(user_id, supabase_client)

    # Шаг 1: Красные флаги
    red_flag_result = check_red_flags(symptoms)
    red_flag = red_flag_result.get("red_flag", False)

    # Шаг 2: Генерация уточняющих вопросов
    questions = parse_and_generate_questions(symptoms, user_profile, patient_history)

    session_id = str(uuid.uuid4())
    sessions[session_id] = {
        "user_id": user_id,
        "symptoms": symptoms,
        "user_profile": user_profile,
        "questions": questions,
        "answers": [],
        "duration": None,
        "anamnesis_questions": [],
        "anamnesis_answers": [],
    }

    return json_response({
        "session_id": session_id,
        "questions": questions,
        "red_flag": red_flag,
    })


async def api_consultation_answer(request: web.Request) -> web.Response:
    """POST /api/consultation/answer"""
    try:
        body = await request.json()
    except Exception:
        return json_response({"error": "Invalid JSON"}, status=400)

    session_id = body.get("session_id")
    question_index = body.get("question_index")
    answer = body.get("answer", "")

    if not session_id or question_index is None:
        return json_response({"error": "session_id and question_index are required"}, status=400)

    session = sessions.get(session_id)
    if not session:
        return json_response({"error": "Session not found"}, status=404)

    questions = session["questions"]

    # Сохраняем ответ
    q_text = questions[question_index]["question"] if question_index < len(questions) else ""
    # Обновляем или добавляем запись по индексу
    while len(session["answers"]) <= question_index:
        session["answers"].append(None)
    session["answers"][question_index] = {"question": q_text, "answer": answer}

    next_index = question_index + 1
    if next_index < len(questions):
        return json_response({"next_question": questions[next_index], "ready_for_result": False})
    else:
        return json_response({"next_question": None, "ready_for_result": True})


async def api_consultation_duration(request: web.Request) -> web.Response:
    """POST /api/consultation/duration"""
    try:
        body = await request.json()
    except Exception:
        return json_response({"error": "Invalid JSON"}, status=400)

    session_id = body.get("session_id")
    duration = body.get("duration", "")

    if not session_id:
        return json_response({"error": "session_id is required"}, status=400)

    session = sessions.get(session_id)
    if not session:
        return json_response({"error": "Session not found"}, status=404)

    session["duration"] = duration

    # Генерация анамнестических вопросов
    anamnesis_questions = get_anamnesis_questions(session["symptoms"])
    session["anamnesis_questions"] = anamnesis_questions

    return json_response({"anamnesis_questions": anamnesis_questions})


async def api_consultation_result(request: web.Request) -> web.Response:
    """POST /api/consultation/result"""
    try:
        body = await request.json()
    except Exception:
        return json_response({"error": "Invalid JSON"}, status=400)

    session_id = body.get("session_id")
    if not session_id:
        return json_response({"error": "session_id is required"}, status=400)

    session = sessions.get(session_id)
    if not session:
        return json_response({"error": "Session not found"}, status=404)

    # Анамнестические ответы могут быть переданы в теле запроса
    anamnesis_answers = body.get("anamnesis_answers", session.get("anamnesis_answers", []))
    session["anamnesis_answers"] = anamnesis_answers

    all_data = {
        "symptoms": session["symptoms"],
        "followup_answers": [a for a in session["answers"] if a],
        "duration": session["duration"] or "не указана",
        "anamnesis_answers": anamnesis_answers,
    }

    recommendation = get_final_recommendation(all_data, session["user_profile"])

    # Сохраняем в Supabase
    try:
        specialists = recommendation.get("specialists", [])
        recommended_doctor = specialists[0]["name"] if specialists else "Терапевт"
        supabase_client.table("consultations").insert({
            "user_id": session["user_id"],
            "symptoms": json.dumps({"text": session["symptoms"], "history": [a for a in session["answers"] if a]}, ensure_ascii=False),
            "questions_answers": json.dumps(all_data, ensure_ascii=False),
            "recommended_doctor": recommended_doctor,
            "urgency_level": recommendation.get("urgency", "medium"),
        }).execute()
    except Exception as e:
        logger.error(f"Failed to save consultation to Supabase: {e}", exc_info=True)

    return json_response(recommendation)


async def api_profile_get(request: web.Request) -> web.Response:
    """GET /api/profile/{user_id}"""
    user_id = request.match_info.get("user_id")
    if not user_id:
        return json_response({"error": "user_id is required"}, status=400)

    try:
        resp = supabase_client.table("user_profiles").select("*").eq("user_id", int(user_id)).single().execute()
        profile_data = resp.data or {}
        return json_response(profile_data)
    except Exception as e:
        logger.error(f"Failed to fetch profile for user {user_id}: {e}", exc_info=True)
        return json_response({"error": "Profile not found"}, status=404)


async def api_health_heartrate(request: web.Request) -> web.Response:
    """POST /api/health/heartrate"""
    try:
        data = await request.json()
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
        supabase_client.table('health_metrics').insert(record).execute()

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


async def start_bot():
    """Запуск бота с автоматическим перезапуском при ошибках"""
    retry_delay = 5

    while True:
        try:
            logger.info("🤖 Starting Telegram bot...")

            # Удаляем старые вебхуки (если есть)
            await bot.delete_webhook(drop_pending_updates=True)
            logger.info("✅ Webhook cleared")

            # Запускаем polling
            logger.info("✅ Bot polling started successfully!")
            await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

        except KeyboardInterrupt:
            logger.info("⚠️ Bot stopped by user")
            break

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
        app.router.add_get('/api/profile/{user_id}', api_profile_get)
        app.router.add_post('/api/health/heartrate', api_health_heartrate)

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
