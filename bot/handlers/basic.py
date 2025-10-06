from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from bot.keyboards import main_menu_keyboard, gender_keyboard
from bot.states import RegistrationStates
from database.connection import db

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Обработчик команды /start"""
    await state.clear()
    
    # Проверяем, есть ли пользователь в базе
    user_profile = await db.get_user_profile(message.from_user.id)
    
    if not user_profile:
        # Новый пользователь - начинаем регистрацию
        await db.create_user_profile(
            user_id=message.from_user.id,
            username=message.from_user.username
        )
        
        await message.answer(
            "👋 Добро пожаловать в медицинского бота-ассистента!\n\n"
            "Я помогу вам определить, к какому врачу-специалисту нужно обратиться на основе ваших симптомов.\n\n"
            "Для начала давайте заполним ваш профиль. Это поможет мне дать более точные рекомендации.\n\n"
            "Укажите ваш возраст (в годах):",
            reply_markup=gender_keyboard()
        )
        await state.set_state(RegistrationStates.waiting_for_age)
    else:
        # Существующий пользователь
        await message.answer(
            f"Рад видеть вас снова!\n\n"
            f"Выберите действие:",
            reply_markup=main_menu_keyboard()
        )


@router.message(Command("help"))
@router.message(F.text == "ℹ️ Помощь")
async def cmd_help(message: Message):
    """Обработчик команды /help"""
    help_text = """
🤖 <b>Как пользоваться ботом:</b>

1️⃣ <b>Новая консультация</b>
Опишите ваши симптомы текстом или голосовым сообщением. Я задам уточняющие вопросы и порекомендую нужного специалиста.

2️⃣ <b>Мои консультации</b>
Просмотр истории предыдущих обращений.

3️⃣ <b>Мой профиль</b>
Управление личными данными (возраст, пол, рост, вес).

<b>⚠️ ВАЖНО:</b>
• Бот НЕ заменяет визит к врачу
• Это только рекомендация, куда обратиться
• При серьёзных симптомах немедленно обратитесь в скорую помощь

<b>Команды:</b>
/start - Главное меню
/help - Эта справка
/cancel - Отменить текущее действие
"""
    await message.answer(help_text, parse_mode="HTML")


@router.message(Command("cancel"))
@router.message(F.text == "❌ Отменить")
async def cmd_cancel(message: Message, state: FSMContext):
    """Отмена текущего действия"""
    current_state = await state.get_state()
    
    if current_state is None:
        await message.answer(
            "Нечего отменять 🤷‍♂️",
            reply_markup=main_menu_keyboard()
        )
        return
    
    await state.clear()
    await message.answer(
        "✅ Действие отменено. Возвращаю в главное меню.",
        reply_markup=main_menu_keyboard()
    )
