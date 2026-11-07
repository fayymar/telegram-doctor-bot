"""Middleware для бота"""
import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, TelegramObject

from config import FSM_TIMEOUT
from utils.logger import setup_logger

logger = setup_logger(__name__)


class FSMTimeoutMiddleware(BaseMiddleware):
    """
    Middleware для автоматической очистки устаревших FSM состояний

    Проверяет время последнего обновления состояния и очищает его
    если прошло больше FSM_TIMEOUT секунд
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any]
    ) -> Any:
        """
        Обработчик middleware

        Args:
            handler: Следующий обработчик в цепочке
            event: Событие (Message, CallbackQuery и т.д.)
            data: Данные контекста

        Returns:
            Результат выполнения handler
        """
        # Получаем FSM context
        state: FSMContext = data.get("state")

        if state:
            try:
                # Получаем данные состояния
                state_data = await state.get_data()
                current_state = await state.get_state()

                # Если есть активное состояние
                if current_state:
                    # Проверяем время последнего обновления
                    last_update = state_data.get('_last_update', time.time())
                    time_passed = time.time() - last_update

                    # Если прошло больше FSM_TIMEOUT - очищаем состояние
                    if time_passed > FSM_TIMEOUT:
                        logger.warning(
                            f"FSM state timeout for user (state: {current_state}, "
                            f"inactive for {int(time_passed)}s)"
                        )
                        await state.clear()

                        # Если это Message - отправляем уведомление
                        if isinstance(event, Message):
                            await event.answer(
                                "⏱ Время сессии истекло\n\n"
                                "Пожалуйста, начните сначала.\n"
                                "Используйте /start"
                            )
                        return

                # Обновляем время последнего обновления
                await state.update_data(_last_update=time.time())

            except Exception as e:
                logger.error(f"Error in FSMTimeoutMiddleware: {e}")

        # Продолжаем обработку
        return await handler(event, data)


# ── Согласие на обработку данных ──────────────────────────────────────────────
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

# Что можно делать без согласия: команды и кнопки, которые не собирают данные о здоровье
_FREE_COMMANDS = ("/start", "/help", "/login", "/link", "/deletedata", "/cancel", "/privacy")
_FREE_CALLBACKS = ("consent:", "start_web", "back_to_start", "confirm_delete", "cancel_delete")
_FREE_TEXTS = ("❓ F.A.Q.",)


def consent_keyboard() -> InlineKeyboardMarkup:
    from services.consent import PRIVACY_URL
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Согласен", callback_data="consent:accept")],
        [InlineKeyboardButton(text="📄 Подробнее", url=PRIVACY_URL)],
    ])


async def send_consent_request(message: Message) -> None:
    from services.consent import CONSENT_TEXT_HTML
    await message.answer(CONSENT_TEXT_HTML, parse_mode="HTML", reply_markup=consent_keyboard())


class ConsentMiddleware(BaseMiddleware):
    """
    Пока пользователь не дал согласие на текущую версию текста, бот не принимает
    от него данные: вместо обработки показывает текст согласия с кнопками.
    Разрешены только команды и кнопки, не связанные с данными о здоровье.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        if user is None or self._is_free(event):
            return await handler(event, data)

        from services.consent import has_consent
        try:
            if await has_consent(user.id):
                return await handler(event, data)
        except Exception as e:
            # База недоступна — не пускаем дальше, чтобы не обработать данные без согласия
            logger.error(f"Consent check failed for {user.id}: {type(e).__name__}")
            target = event.message if isinstance(event, CallbackQuery) else event
            if target is not None:
                await target.answer("⚠️ Сервис временно недоступен. Попробуйте чуть позже.")
            if isinstance(event, CallbackQuery):
                await event.answer()
            return None

        if isinstance(event, CallbackQuery):
            await event.answer()
            if event.message is not None:
                await send_consent_request(event.message)
        elif isinstance(event, Message):
            await send_consent_request(event)
        return None

    @staticmethod
    def _is_free(event: TelegramObject) -> bool:
        if isinstance(event, CallbackQuery):
            return any((event.data or "").startswith(p) for p in _FREE_CALLBACKS)
        if isinstance(event, Message):
            text = (event.text or "").strip()
            command = text.split(maxsplit=1)[0].split("@")[0] if text.startswith("/") else ""
            return command in _FREE_COMMANDS or text in _FREE_TEXTS
        return True
