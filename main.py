import asyncio
import logging
import time as _time
from datetime import datetime, timezone

from aiogram import Dispatcher
from aiogram.exceptions import TelegramConflictError
from aiogram.types import MenuButtonDefault
from aiohttp import web

from api.common import consultation_sessions, consultation_store
from api.profile import _check_anamnesis_fields
from api.routes import create_app
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
from bot.instance import bot  # общий для обработчиков и HTTP API
from bot.middlewares import ConsentMiddleware, FSMTimeoutMiddleware
from bot.shared import site_code_store, site_codes
from database.connection import run_query, supabase_client
from services import persistent_state
from services.persistent_state import PersistentMemoryStorage
from services.sessions import load_revocations, revocation_sync_loop
from utils.logger import setup_logger

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = setup_logger(__name__)


# Шаги диалогов бота (анкета, консультация, дневник) хранятся и в базе —
# чтобы перезапуск сервера не обрывал их (services/persistent_state.py)
dp = Dispatcher(storage=PersistentMemoryStorage())

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
            consultation_store.save(sid)
        for code, entry in list(site_codes.items()):
            if _time.time() - entry["created_at"] > 300:
                site_codes.pop(code, None)
                site_code_store.save(code)
        await persistent_state.purge_old_all()
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

        app = create_app()

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
        # Отозванные токены загружаем до запуска API, чтобы после перезапуска
        # не было окна, когда отозванный токен снова принимается
        try:
            await load_revocations()
        except Exception as e:
            logger.error(f"Initial token revocation load failed: {type(e).__name__}")
        # Незавершённые консультации, коды входа и шаги диалогов — до запуска
        # бота и API, чтобы первые же запросы их видели
        await persistent_state.load_all()
        task_names = ("web_server", "bot", "cleanup_stale_sessions", "supabase_keepalive", "revocation_sync")
        results = await asyncio.gather(
            start_web_server(),
            start_bot(),
            cleanup_stale_sessions(),
            supabase_keepalive(),
            revocation_sync_loop(),
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
