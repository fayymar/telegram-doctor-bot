from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    ChatMemberUpdated,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    MenuButtonDefault,
    MenuButtonWebApp,
    Message,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from bot.keyboards import get_clinics_specialists_submenu, get_main_menu
from bot.states import Registration
from database.connection import run_query, supabase_client
from utils.logger import setup_logger

logger = setup_logger(__name__)
router = Router()

WEBAPP_URL = "https://symed-web.vercel.app"


async def set_webapp_menu_button(bot, chat_id: int) -> None:
    await bot.set_chat_menu_button(
        chat_id=chat_id,
        menu_button=MenuButtonWebApp(
            text="Symed",
            web_app=WebAppInfo(url=WEBAPP_URL),
        ),
    )


def get_language_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="🇷🇺 Русский"), KeyboardButton(text="🇺🇿 O'zbek")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True, one_time_keyboard=True)


def _get_start_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📱 Продолжить в Telegram", callback_data="start_telegram"),
        InlineKeyboardButton(text="🌐 Войти на сайт", callback_data="start_web"),
    ]])


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Обработчик /start. Deep link /start login — выдаёт код для сайта."""
    first_name = message.from_user.first_name or "друг"

    args = message.text.split(maxsplit=1)
    payload = args[1].strip() if len(args) > 1 else ""

    if payload in ("login", "link"):
        await _send_site_code(message)
        return

    if payload.startswith(("auth_", "link_")):
        # Старые ссылки: раньше сайт показывал код, а бот его подтверждал.
        # Это позволяло фишинг (чужая ссылка = вход злоумышленника под вами),
        # поэтому такие ссылки больше ничего не делают.
        await message.answer(
            "ℹ️ Этот способ входа больше не используется.\n\n"
            "Чтобы войти на сайт Symed или привязать Telegram, отправьте /login — "
            "бот пришлёт код, который нужно ввести на сайте.",
            reply_markup=_get_start_keyboard(),
        )
        return

    # Обычный /start
    await message.answer(
        f"👋 Привет, {first_name}!\n\nКак хотите продолжить?",
        reply_markup=_get_start_keyboard(),
    )


@router.callback_query(F.data == "start_telegram")
async def start_telegram(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    await callback.message.delete()
    try:
        response = await run_query(lambda: supabase_client.table('user_profiles').select('user_id').eq('user_id', user_id).limit(1).execute())
        if response.data:
            try:
                await set_webapp_menu_button(callback.bot, callback.message.chat.id)
            except Exception as e:
                logger.warning(f"Failed to set menu button for user_id={user_id}: {e}")
            await callback.message.answer(
                "👋 С возвращением!\n\nВыберите действие:",
                reply_markup=get_main_menu()
            )
        else:
            try:
                await callback.bot.set_chat_menu_button(
                    chat_id=callback.message.chat.id,
                    menu_button=MenuButtonDefault(),
                )
            except Exception as e:
                logger.warning(f"Failed to reset menu button for user_id={user_id}: {e}")
            await callback.message.answer(
                "👋 Welcome! / Добро пожаловать! / Xush kelibsiz!\n\n"
                "🌐 Choose your language / Выберите язык / Tilni tanlang:",
                reply_markup=get_language_keyboard()
            )
            await state.set_state(Registration.choosing_language)
    except Exception as e:
        logger.error(f"Database error in start_telegram for user {user_id}: {e}", exc_info=True)
        await callback.message.answer("❌ Ошибка. Попробуйте ещё раз.")
    await callback.answer()


@router.callback_query(F.data == "start_web")
async def start_web(callback: CallbackQuery):
    await callback.message.delete()
    await _send_site_code(callback.message, user=callback.from_user)
    await callback.answer()


async def _send_site_code(message: Message, user=None) -> None:
    """Отправляет пользователю одноразовый код для входа/привязки на сайте."""
    from bot.shared import issue_site_code, site_code_message
    # Код — это ключ к аккаунту: выдаём его только в личном чате с ботом,
    # иначе в группе его увидят все участники.
    if message.chat.type != "private":
        bot_user = await message.bot.get_me()
        await message.answer(
            "🔒 Код для входа можно получить только в личном чате с ботом.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="Открыть личный чат", url=f"https://t.me/{bot_user.username}?start=login"),
            ]]),
        )
        return
    code = issue_site_code(user or message.from_user)
    await message.answer(
        site_code_message(code),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🌐 Открыть сайт", url=f"{WEBAPP_URL}/auth"),
        ]]),
    )


@router.message(Command("login"))
async def cmd_login(message: Message):
    """/login — код для входа на сайт или привязки Telegram в профиле."""
    await _send_site_code(message)


@router.callback_query(F.data == "back_to_start")
async def back_to_start_cb(callback: CallbackQuery):
    await callback.message.edit_text(
        "👋 Как хотите продолжить?",
        reply_markup=_get_start_keyboard(),
    )
    await callback.answer()


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


@router.callback_query(F.data == "consent:accept")
async def consent_accept(callback: CallbackQuery):
    """Пользователь нажал «Согласен» — фиксируем согласие."""
    from services.consent import record_consent
    try:
        await record_consent(callback.from_user.id, "bot")
    except Exception as e:
        logger.error(f"Consent save failed for {callback.from_user.id}: {type(e).__name__}")
        await callback.answer("Не удалось сохранить согласие. Попробуйте ещё раз.", show_alert=True)
        return
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "✅ Спасибо! Согласие сохранено.\n\nКак хотите продолжить?",
        reply_markup=_get_start_keyboard(),
    )
    await callback.answer()


@router.message(Command("privacy"))
async def cmd_privacy(message: Message):
    """Текст согласия и ссылка на политику конфиденциальности."""
    from bot.middlewares import send_consent_request
    await send_consent_request(message)


@router.message(Command("help"))
async def cmd_help(message: Message):
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
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Нечего отменять 🤷\n\nВыберите действие из меню:", reply_markup=get_main_menu())
        return
    await state.clear()
    await message.answer("❌ Операция отменена\n\nВозвращаемся в главное меню:", reply_markup=get_main_menu())


@router.message(F.text == "❓ F.A.Q.")
async def help_button(message: Message):
    await cmd_help(message)


@router.message(F.text == "🏥 Клиники и специалисты")
async def clinics_specialists_menu(message: Message):
    await message.answer("🏥 Что вас интересует?", reply_markup=get_clinics_specialists_submenu())


@router.message(F.text.in_({"🔙 Назад", "🔙 В главное меню", "В главное меню", "🏠 Главное меню", "Главное меню"}))
async def back_to_main(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Главное меню", reply_markup=get_main_menu())


@router.message(Command("deletedata"))
async def cmd_delete_data(message: Message):
    await message.answer(
        "⚠️ Удалить все ваши данные и отозвать согласие?\n\n"
        "Будут удалены:\n"
        "• Профиль и медицинский анамнез\n"
        "• История консультаций\n"
        "• Лекарства и дневник здоровья\n"
        "• Показатели здоровья\n"
        "• Согласие на обработку данных\n\n"
        "Если Telegram привязан к аккаунту на сайте, данные удалятся и там.\n"
        "Это действие необратимо.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Да, удалить все данные", callback_data="confirm_delete"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_delete"),
        ]]),
    )


@router.callback_query(F.data == "confirm_delete")
async def confirm_delete(callback: CallbackQuery, state: FSMContext):
    from services.consent import delete_all_user_data
    user_id = callback.from_user.id
    await state.clear()
    try:
        await delete_all_user_data(user_id)
        await callback.message.edit_text("✅ Все данные удалены, согласие отозвано.")
    except Exception as e:
        logger.error(f"Error deleting user data for {user_id}: {type(e).__name__}")
        await callback.message.edit_text("❌ Ошибка при удалении. Попробуйте ещё раз.")
    await callback.answer()


@router.callback_query(F.data == "cancel_delete")
async def cancel_delete(callback: CallbackQuery):
    await callback.message.edit_text("❌ Удаление отменено.")
    await callback.answer()


@router.my_chat_member()
async def on_user_blocked_bot(update: ChatMemberUpdated):
    if update.new_chat_member.status == "kicked":
        from services.consent import delete_all_user_data
        user_id = update.from_user.id
        try:
            # Блокировка бота — не просьба удалить аккаунт на сайте: удаляем только Telegram-аккаунт
            await delete_all_user_data(user_id, include_linked=False)
            logger.info(f"Deleted all data for user {user_id} (bot blocked)")
        except Exception as e:
            logger.error(f"Error deleting user data for {user_id}: {type(e).__name__}")


@router.message(Command("profile"))
async def cmd_profile(message: Message):
    user_id = message.from_user.id
    try:
        resp = await run_query(lambda: supabase_client.table("user_profiles").select(
            "full_name, phone, birthdate, gender, height, weight, "
            "chronic_diseases, drug_allergies, smoking, hereditary"
        ).eq("user_id", user_id).limit(1).execute())
        rows = resp.data or []
        if not rows:
            await message.answer("Профиль не заполнен. Отправьте /start чтобы пройти регистрацию, или откройте приложение Symed.")
            return
        p = rows[0]
        name = p.get("full_name") or "не указано"
        dob_raw = p.get("birthdate")
        dob = "не указано"
        if dob_raw:
            try:
                from datetime import date as _date
                dob = _date.fromisoformat(dob_raw[:10]).strftime("%d.%m.%Y")
            except Exception:
                dob = dob_raw
        sex_map = {"male": "Мужской", "female": "Женский"}
        sex = sex_map.get(p.get("gender") or "", "не указано")
        chronic = p.get("chronic_diseases") or []
        hereditary = p.get("hereditary") or []
        allergies = (p.get("drug_allergies") or "").strip()
        smoking_map = {"yes": "🚬 Курит", "quit": "✅ Бросил(а)", "no": "🚭 Не курит"}
        lines = [
            "👤 Ваш профиль:\n",
            f"Имя: {name}", f"Дата рождения: {dob}", f"Пол: {sex}",
            f"Рост: {p.get('height') or 'не указано'} см",
            f"Вес: {p.get('weight') or 'не указано'} кг",
            f"Телефон: {p.get('phone') or 'не указано'}", "",
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
    await message.answer(
        "❤️ Отслеживание пульса\n\n"
        "Откройте приложение Symed чтобы:\n"
        "- Отправить текущий пульс с Apple Watch\n"
        "- Посмотреть историю измерений\n"
        "- Настроить автоматическую отправку\n\n"
        'Нажмите кнопку "Symed" внизу экрана (рядом с полем ввода) чтобы открыть приложение.'
    )


@router.message(Command("link"))
async def cmd_link(message: Message) -> None:
    """Привязка теперь делается на сайте кодом из бота."""
    await message.answer(
        "🔗 Чтобы привязать Telegram к аккаунту на сайте, откройте Symed → Профиль → "
        "«Подключить Telegram» и введите код, который пришлёт бот.",
    )
    await _send_site_code(message)
