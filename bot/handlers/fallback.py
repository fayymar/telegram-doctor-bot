"""Fallback обработчик для зависших FSM состояний."""
from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from utils.logger import setup_logger

logger = setup_logger(__name__)
router = Router()


@router.message(StateFilter("*"), F.text.in_({"🔙 Главное меню", "/start", "/menu", "Отмена", "Меню"}))
async def force_reset_state(message: Message, state: FSMContext):
    """Принудительный сброс FSM по ключевым словам."""
    current = await state.get_state()
    if current:
        await state.clear()
    try:
        from bot.keyboards import get_main_menu
        await message.answer("Возвращаемся в главное меню.", reply_markup=get_main_menu())
    except Exception:
        await message.answer("Возвращаемся в главное меню.")


@router.message(StateFilter("*"))
async def fallback_handler(message: Message, state: FSMContext):
    """Ловит любое сообщение в неизвестном состоянии."""
    current = await state.get_state()
    if current is None:
        return  # Не в FSM — пропускаем
    logger.warning(
        f"Unhandled msg in state={current}, user={message.from_user.id}, text={message.text!r}"
    )
    await state.clear()
    try:
        from bot.keyboards import get_main_menu
        await message.answer(
            "Что-то пошло не так. Сбрасываю состояние.\n\nВозвращаемся в главное меню.",
            reply_markup=get_main_menu()
        )
    except Exception:
        await message.answer("Что-то пошло не так. Попробуйте /start")
