import asyncio
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import BOT_TOKEN
from bot.handlers import basic, profile, consultation, specialists, history, medications, health_diary, clinic_finder
from bot.middlewares import FSMTimeoutMiddleware
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

# Регистрация роутеров (ПОРЯДОК ВАЖЕН!)
dp.include_router(basic.router)        # Базовые команды (/start, /help)
dp.include_router(profile.router)      # Профиль и регистрация
dp.include_router(history.router)      # История консультаций
dp.include_router(medications.router)  # Напоминания о лекарствах
dp.include_router(health_diary.router) # Дневник здоровья
dp.include_router(clinic_finder.router) # Поиск клиник рядом
dp.include_router(specialists.router)  # Поиск специалистов
dp.include_router(consultation.router) # Консультации (должен быть последним)


# HTTP сервер для Render (Health check)
async def health_check(request):
    """Endpoint для проверки здоровья сервиса"""
    return web.Response(text="OK", status=200)


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

        app = web.Application()
        app.router.add_get('/health', health_check)
        app.router.add_get('/', health_check)

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
