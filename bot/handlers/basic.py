from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from bot.keyboards import get_main_menu, get_gender_keyboard
from bot.states import Registration
from database.connection import supabase_client
from utils.logger import setup_logger

logger = setup_logger(__name__)
router = Router()


def get_language_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура выбора языка"""
    keyboard = [
        [KeyboardButton(text="🇷🇺 Русский"), KeyboardButton(text="🇺🇿 O'zbek")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True, one_time_keyboard=True)


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Обработчик команды /start"""
    user_id = message.from_user.id
    username = message.from_user.username

    # Проверяем, зарегистрирован ли пользователь
    try:
        response = supabase_client.table('user_profiles').select('*').eq('user_id', user_id).execute()

        if response.data:
            # Пользователь уже зарегистрирован
            lang = response.data[0].get('language', 'ru')

            welcome_text = {
                'ru': "👋 С возвращением!\n\nВыберите действие:",
                'uz': "👋 Qaytganingiz bilan!\n\nAmalni tanlang:"
            }

            await message.answer(
                welcome_text.get(lang, welcome_text['ru']),
                reply_markup=get_main_menu()
            )
        else:
            # Новый пользователь - выбор языка
            await message.answer(
                "👋 Welcome! / Добро пожаловать! / Xush kelibsiz!\n\n"
                "🌐 Choose your language / Выберите язык / Tilni tanlang:",
                reply_markup=get_language_keyboard()
            )
            await state.set_state(Registration.choosing_language)

    except Exception as e:
        logger.error(f"Database error in cmd_start for user {user_id}: {e}", exc_info=True)
        await message.answer(
            "❌ Database error / Ошибка БД / Ma'lumotlar bazasi xatosi\n"
            "Try again later / Попробуйте позже / Keyinroq urinib ko'ring"
        )


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Обработчик команды /help"""
    help_text = (
        "ℹ️ *Справка по боту*\n\n"
        "*Команды:*\n"
        "/start - Начать работу\n"
        "/help - Показать эту справку\n"
        "/cancel - Отменить текущую операцию\n\n"
        "*Основные функции:*\n\n"
        "🩺 *Новая консультация*\n"
        "Опишите ваши симптомы, и бот порекомендует специалиста.\n\n"
        "👤 *Профиль*\n"
        "Просмотр и редактирование ваших данных.\n\n"
        "🔍 *Найти специалиста*\n"
        "Поиск врача по категориям и специализациям.\n\n"
        "📋 *История*\n"
        "Просмотр прошлых консультаций (в разработке).\n\n"
        "*Как работает консультация:*\n"
        "1. Опишите симптомы\n"
        "2. Укажите давность\n"
        "3. Выберите дополнительные симптомы\n"
        "4. Получите рекомендацию\n\n"
        "💡 *Совет:* Чем подробнее вы опишете симптомы, тем точнее будет рекомендация."
    )
    
    await message.answer(help_text, parse_mode="Markdown")


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    """Обработчик команды /cancel"""
    current_state = await state.get_state()
    
    if current_state is None:
        await message.answer(
            "Нечего отменять 🤷\n\n"
            "Выберите действие из меню:",
            reply_markup=get_main_menu()
        )
        return
    
    await state.clear()
    await message.answer(
        "❌ Операция отменена\n\n"
        "Возвращаемся в главное меню:",
        reply_markup=get_main_menu()
    )


@router.message(F.text == "ℹ️ Помощь")
async def help_button(message: Message):
    """Обработчик кнопки Помощь"""
    await cmd_help(message)


# История консультаций теперь обрабатывается в отдельном модуле bot/handlers/history.py
