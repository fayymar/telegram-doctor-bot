"""Middleware для бота"""
import time
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject
from aiogram.fsm.context import FSMContext
from utils.logger import setup_logger
from config import FSM_TIMEOUT

logger = setup_logger(__name__)


class FSMTimeoutMiddleware(BaseMiddleware):
    """
    Middleware для автоматической очистки устаревших FSM состояний

    Проверяет время последнего обновления состояния и очищает его
    если прошло больше FSM_TIMEOUT секунд
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
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
