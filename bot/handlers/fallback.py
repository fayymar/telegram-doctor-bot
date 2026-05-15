"""Fallback обработчик для зависших FSM состояний и необработанных сообщений."""
from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from utils.logger import setup_logger

logger = setup_logger(__name__)
router = Router()

# Тексты кнопок которые всегда должны идти в главное меню
MENU_TEXTS = {
    "🔙 Главное меню", "В главное меню", "🔙 В главное меню",
    "🏠 Главное меню", "Главное меню", "/menu", "Меню",
}


@router.message(StateFilter("*"), F.text.in_(MENU_TEXTS | {"/start", "Отмена"}))
async def force_reset_state(message: Message, state: FSMContext):
    """Принудительный сброс FSM и возврат в главное меню."""
    await state.clear()
    try:
        from bot.keyboards import get_main_menu
        await message.answer("Главное меню", reply_markup=get_main_menu())
    except Exception:
        await message.answer("Главное меню. Отправьте /start")


@router.message(StateFilter("*"))
async def fallback_handler(message: Message, state: FSMContext):
    """Ловит любое сообщение в неизвестном состоянии."""
    current = await state.get_state()

    if current is not None:
        # В FSM состоянии — сбрасываем
        logger.warning(
            f"Unhandled in state={current}, user={message.from_user.id}, text={message.text!r}"
        )
        await state.clear()
        try:
            from bot.keyboards import get_main_menu
            await message.answer(
                "Что-то пошло не так. Возвращаемся в главное меню.",
                reply_markup=get_main_menu()
            )
        except Exception:
            await message.answer("Что-то пошло не так. Попробуйте /start")
    else:
        # Вне FSM — необработанный текст
        # Не спамим, просто логируем и мягко подсказываем
        text = message.text or ""
        if text.startswith("/"):
            return  # Неизвестная команда — молчим
        logger.info(
            f"Unhandled msg (no state), user={message.from_user.id}, text={text!r}"
        )
        try:
            from bot.keyboards import get_main_menu
            await message.answer(
                "Выберите действие из меню:",
                reply_markup=get_main_menu()
            )
        except Exception:
            pass
