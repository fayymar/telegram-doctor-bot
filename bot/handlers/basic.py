from aiogram import Router, F
from aiogram.types import (
    Message, CallbackQuery, ChatMemberUpdated,
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    WebAppInfo, MenuButtonWebApp, MenuButtonDefault,
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from bot.keyboards import get_main_menu, get_gender_keyboard, get_clinics_specialists_submenu
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


_FAQ_TEXT = """❓ *F.A.Q.*

🔹 *Как начать консультацию?*
Нажмите «Новая консультация» и опишите симптомы.

🔹 *Как подключить Apple Watch?*
Откройте приложение → Показатели здоровья → Настройка Shortcut.

🔹 *Как обновить профиль?*
Нажмите кнопку «Профиль» в меню.

🔹 *Как удалить мои данные?*
Отправьте команду /deletedata

🔹 *Это замена врачу?*
Нет. Бот помогает определить к какому специалисту обратиться.
Всегда консультируйтесь с врачом.

🔹 *Мои данные в безопасности?*
Данные хранятся в зашифрованной базе и не передаются третьим лицам."""


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Обработчик команды /help"""
    await message.answer(
        _FAQ_TEXT,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="🌐 Открыть приложение",
                web_app=WebAppInfo(url=WEBAPP_URL),
            )
        ]]),
    )


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


@router.message(F.text == "❓ F.A.Q.")
async def help_button(message: Message):
    await cmd_help(message)


@router.message(F.text == "🏥 Клиники и специалисты")
async def clinics_specialists_menu(message: Message):
    await message.answer(
        "🏥 Что вас интересует?",
        reply_markup=get_clinics_specialists_submenu(),
    )


@router.message(F.text == "🔙 Назад")
async def back_to_main(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Главное меню", reply_markup=get_main_menu())


@router.message(Command("deletedata"))
async def cmd_delete_data(message: Message):
    await message.answer(
        "⚠️ Удалить все ваши данные?\n\n"
        "Будут удалены:\n"
        "• Профиль и медицинская история\n"
        "• Показатели здоровья\n"
        "• История консультаций\n\n"
        "Это действие необратимо.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Да, удалить все данные", callback_data="confirm_delete"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_delete"),
        ]]),
    )


@router.callback_query(F.data == "confirm_delete")
async def confirm_delete(callback: CallbackQuery):
    user_id = callback.from_user.id
    try:
        supabase_client.table("user_profiles").delete().eq("user_id", user_id).execute()
        supabase_client.table("health_metrics").delete().eq("user_id", user_id).execute()
        supabase_client.table("consultations").delete().eq("user_id", user_id).execute()
        logger.info(f"Deleted all data for user {user_id}")
        await callback.message.edit_text("✅ Все данные удалены.")
    except Exception as e:
        logger.error(f"Error deleting user data for {user_id}: {e}")
        await callback.message.edit_text("❌ Ошибка при удалении. Попробуйте ещё раз.")
    await callback.answer()


@router.callback_query(F.data == "cancel_delete")
async def cancel_delete(callback: CallbackQuery):
    await callback.message.edit_text("❌ Удаление отменено.")
    await callback.answer()


@router.my_chat_member()
async def on_user_blocked_bot(update: ChatMemberUpdated):
    """Удаляет данные пользователя когда он блокирует бота."""
    if update.new_chat_member.status == "kicked":
        user_id = update.from_user.id
        try:
            supabase_client.table("user_profiles").delete().eq("user_id", user_id).execute()
            supabase_client.table("health_metrics").delete().eq("user_id", user_id).execute()
            supabase_client.table("consultations").delete().eq("user_id", user_id).execute()
            logger.info(f"Deleted all data for user {user_id} (bot blocked)")
        except Exception as e:
            logger.error(f"Error deleting user data for {user_id}: {e}")


@router.message(Command("profile"))
async def cmd_profile(message: Message):
    """Обработчик команды /profile"""
    user_id = message.from_user.id
    try:
        resp = supabase_client.table("user_profiles").select(
            "full_name, phone, birthdate, gender, height, weight, "
            "chronic_diseases, drug_allergies, smoking, hereditary"
        ).eq("user_id", user_id).limit(1).execute()

        rows = resp.data or []
        if not rows:
            await message.answer(
                "Профиль не заполнен. Отправьте /start чтобы пройти регистрацию, "
                "или откройте приложение СимптоМед."
            )
            return

        p = rows[0]

        # Форматирование имени
        name = p.get("full_name") or "не указано"

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

        chronic = p.get("chronic_diseases") or []
        hereditary = p.get("hereditary") or []
        allergies = (p.get("drug_allergies") or "").strip()
        smoking_map = {"yes": "🚬 Курит", "quit": "✅ Бросил(а)", "no": "🚭 Не курит"}

        lines = [
            "👤 Ваш профиль:\n",
            f"Имя: {name}",
            f"Дата рождения: {dob}",
            f"Пол: {sex}",
            f"Рост: {p.get('height') or 'не указано'} см",
            f"Вес: {p.get('weight') or 'не указано'} кг",
            f"Телефон: {p.get('phone') or 'не указано'}",
            "",
            f"Хронические: {', '.join(chronic) if chronic else 'не указано'}",
            f"Наследственность: {', '.join(hereditary) if hereditary else 'не указано'}",
            f"Аллергии: {allergies if allergies else 'не указано'}",
            f"Курение: {smoking_map.get(p.get('smoking', 'no'), '—')}",
            "\nДля обновления используйте кнопку «Профиль» в меню.",
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
