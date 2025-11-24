from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from bot.keyboards import get_main_menu, get_gender_keyboard
from bot.states import Registration
from database.connection import supabase_client
from utils.logger import setup_logger

logger = setup_logger(__name__)
router = Router()


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
            await message.answer(
                f"👋 С возвращением!\n\n"
                "Выберите действие:",
                reply_markup=get_main_menu()
            )
        else:
            # Новый пользователь - начинаем регистрацию
            await message.answer(
                f"👋 Добро пожаловать!\n\n"
                "🩺 *Telegram Medical Bot*\n\n"
                "Я помогу вам:\n"
                "• Определить нужного специалиста\n"
                "• Оценить срочность обращения\n"
                "• Записаться на приём\n\n"
                "Для начала давайте заполним ваш профиль.\n\n"
                "👤 *Как вас зовут?*\n"
                "Введите ФИО (например: Иванов Иван или Иван Петров)",
                parse_mode="Markdown"
            )
            await state.set_state(Registration.waiting_for_full_name)
            
    except Exception as e:
        logger.error(f"Database error in cmd_start for user {user_id}: {e}", exc_info=True)
        await message.answer(
            "❌ Произошла ошибка при подключении к базе данных.\n"
            "Попробуйте позже или обратитесь к администратору."
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


@router.message(F.text == "📋 История")
async def history_button(message: Message):
    """Обработчик кнопки История (заглушка)"""
    await message.answer(
        "📋 *История консультаций*\n\n"
        "⏳ Функция находится в разработке.\n\n"
        "Скоро вы сможете:\n"
        "• Просматривать прошлые консультации\n"
        "• Фильтровать по датам и специалистам\n"
        "• Экспортировать анамнез в PDF",
        parse_mode="Markdown"
    )
