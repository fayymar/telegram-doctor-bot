from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo, MenuButtonWebApp, MenuButtonDefault
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from bot.keyboards import get_main_menu, get_gender_keyboard
from bot.states import Registration
from database.connection import supabase_client
from utils.logger import setup_logger

logger = setup_logger(__name__)
router = Router()

WEBAPP_URL = "https://sympto-med-app.vercel.app"


async def set_webapp_menu_button(bot, chat_id: int) -> None:
    """Устанавливает кнопку СимптоМед в меню чата."""
    await bot.set_chat_menu_button(
        chat_id=chat_id,
        menu_button=MenuButtonWebApp(
            text="СимптоМед",
            web_app=WebAppInfo(url=WEBAPP_URL),
        ),
    )


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
        response = supabase_client.table('user_profiles').select('user_id').eq('user_id', user_id).limit(1).execute()
        logger.info(f"Start check for user_id={user_id}, result={response.data}")

        if response.data:
            # Пользователь уже зарегистрирован — восстанавливаем Menu Button на случай сброса
            try:
                await set_webapp_menu_button(message.bot, message.chat.id)
                logger.info(f"Menu button restored for user_id={user_id}")
            except Exception as e:
                logger.warning(f"Failed to set menu button for user_id={user_id}: {e}")
            await message.answer(
                "👋 С возвращением!\n\nВыберите действие:",
                reply_markup=get_main_menu()
            )
        else:
            # Новый пользователь — сбрасываем Menu Button, показываем только клавиатуру регистрации
            try:
                await message.bot.set_chat_menu_button(
                    chat_id=message.chat.id,
                    menu_button=MenuButtonDefault(),
                )
                logger.info(f"Menu button reset for new user_id={user_id}")
            except Exception as e:
                logger.warning(f"Failed to reset menu button for user_id={user_id}: {e}")
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


@router.message(Command("profile"))
async def cmd_profile(message: Message):
    """Обработчик команды /profile"""
    user_id = message.from_user.id
    try:
        resp = supabase_client.table("user_profiles").select(
            "full_name, phone, birthdate, gender, height, weight"
        ).eq("user_id", user_id).limit(1).execute()

        rows = resp.data or []
        if not rows:
            await message.answer(
                "Профиль не заполнен. Отправьте /start чтобы пройти регистрацию, "
                "или откройте приложение СимптоМед."
            )
            return

        p = rows[0]

        # Форматирование даты рождения
        dob_raw = p.get("birthdate")
        dob = "не указано"
        if dob_raw:
            try:
                from datetime import date as _date
                dob = _date.fromisoformat(dob_raw[:10]).strftime("%d.%m.%Y")
            except Exception:
                dob = dob_raw

        # Форматирование пола
        sex_map = {"male": "Мужской", "female": "Женский"}
        sex = sex_map.get(p.get("gender") or "", "не указано")

        name = p.get("full_name") or "не указано"

        lines = [
            "👤 Ваш профиль:\n",
            f"Имя: {name}",
            f"Дата рождения: {dob}",
            f"Пол: {sex}",
            f"Рост: {p.get('height') or 'не указано'} см",
            f"Вес: {p.get('weight') or 'не указано'} кг",
            f"Телефон: {p.get('phone') or 'не указано'}",
            "\nВы можете изменить данные в приложении СимптоМед (кнопка внизу экрана).",
        ]
        await message.answer("\n".join(lines))

    except Exception as e:
        logger.error(f"Profile command error for user {user_id}: {e}", exc_info=True)
        await message.answer("❌ Ошибка при загрузке профиля. Попробуйте позже.")


@router.message(Command("heartrate"))
async def cmd_heartrate(message: Message):
    """Обработчик команды /heartrate"""
    await message.answer(
        "❤️ Отслеживание пульса\n\n"
        "Откройте приложение СимптоМед чтобы:\n"
        "- Отправить текущий пульс с Apple Watch\n"
        "- Посмотреть историю измерений\n"
        "- Настроить автоматическую отправку\n\n"
        'Нажмите кнопку "СимптоМед" внизу экрана (рядом с полем ввода) чтобы открыть приложение.'
    )


# История консультаций теперь обрабатывается в отдельном модуле bot/handlers/history.py
