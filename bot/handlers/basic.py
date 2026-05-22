from aiogram import Router, F
from aiogram.types import (
    Message, CallbackQuery, ChatMemberUpdated,
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    WebAppInfo, MenuButtonWebApp, MenuButtonDefault,
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from bot.keyboards import get_main_menu, get_clinics_specialists_submenu
from bot.states import Registration
from database.connection import supabase_client
from utils.logger import setup_logger

logger = setup_logger(__name__)
router = Router()

WEBAPP_URL = "https://sympto-med-app.vercel.app"


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
        InlineKeyboardButton(text="🌐 Ввести код веб-версии", callback_data="start_web"),
    ]])


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Обработчик /start — поддерживает deep link auth_XXXXXX"""
    from bot.shared import web_auth_codes
    from datetime import datetime as _dt

    user_id = message.from_user.id
    first_name = message.from_user.first_name or "друг"

    # Deep link: /start auth_123456
    args = message.text.split(maxsplit=1)
    payload = args[1].strip() if len(args) > 1 else ""

    if payload.startswith("auth_"):
        code = payload[5:]
        entry = web_auth_codes.get(code)

        if not entry:
            await message.answer(
                "❌ Код не найден или уже истёк.\n\n"
                "Вернитесь на сайт и получите новый код.",
                reply_markup=_get_start_keyboard(),
            )
            return

        age = (_dt.utcnow() - entry["created_at"]).total_seconds()
        if age > 600:
            web_auth_codes.pop(code, None)
            await message.answer(
                "⏰ Код истёк (действует 10 минут).\n\n"
                "Вернитесь на сайт и получите новый код.",
                reply_markup=_get_start_keyboard(),
            )
            return

        if entry["verified"]:
            await message.answer("✅ Этот код уже использован.", reply_markup=_get_start_keyboard())
            return

        user = message.from_user
        entry["verified"] = True
        entry["telegram_id"] = user.id
        entry["first_name"] = user.first_name or ""
        entry["last_name"] = user.last_name or ""
        entry["username"] = user.username or ""
        entry["photo_url"] = None

        logger.info(f"Deep-link auth {code} verified for user_id={user.id}")

        await message.answer(
            f"✅ Вы успешно вошли в Symed, {first_name}!\n\n"
            "Вернитесь на сайт — страница автоматически обновится.",
            reply_markup=_get_start_keyboard(),
        )
        return

    if payload.startswith("link_"):
        code = payload[5:]
        from bot.shared import link_codes
        from database.connection import supabase_client as _sb
        from datetime import datetime as _dt2

        entry = link_codes.get(code)
        if not entry:
            await message.answer("❌ Код привязки не найден или истёк.\n\nОткройте Symed → Профиль → Подключить Telegram.")
            return

        age = (_dt2.utcnow() - entry["created_at"]).total_seconds()
        if age > 600:
            link_codes.pop(code, None)
            await message.answer("⏰ Код истёк (10 минут). Получите новый в Symed.")
            return

        if entry.get("verified"):
            await message.answer("✅ Аккаунты уже связаны.")
            return

        tg_id  = message.from_user.id
        web_id = entry["web_user_id"]

        try:
            tg_resp  = _sb.table("user_profiles").select("*").eq("user_id", tg_id).limit(1).execute()
            web_resp = _sb.table("user_profiles").select("*").eq("user_id", web_id).limit(1).execute()
            tg_profile  = tg_resp.data[0]  if tg_resp.data  else {}
            web_profile = web_resp.data[0] if web_resp.data else {}

            merge_fields = ["birthdate", "gender", "height", "weight", "phone",
                            "chronic_diseases", "drug_allergies", "smoking",
                            "hereditary", "physical_activity"]
            update_web = {"linked_telegram_id": str(tg_id)}
            for field in merge_fields:
                if tg_profile.get(field) and not web_profile.get(field):
                    update_web[field] = tg_profile[field]
            if not web_profile.get("full_name") and tg_profile.get("full_name"):
                update_web["full_name"] = tg_profile["full_name"]

            _sb.table("user_profiles").upsert({"user_id": web_id, **update_web}, on_conflict="user_id").execute()
            _sb.table("user_profiles").upsert({"user_id": tg_id, "linked_web_id": str(web_id)}, on_conflict="user_id").execute()

            entry["verified"]    = True
            entry["telegram_id"] = tg_id
            link_codes[code]     = entry

            logger.info(f"Deep-link account linked: tg={tg_id} <-> web={web_id}")
            await message.answer(
                f"✅ <b>Аккаунты успешно связаны, {first_name}!</b>\n\n"
                "Ваши данные в Telegram и на сайте Symed теперь синхронизированы. "
                "Вернитесь на сайт — он уже обновился.",
                parse_mode="HTML",
                reply_markup=_get_start_keyboard(),
            )
        except Exception as e:
            logger.error(f"Deep-link link error: {e}", exc_info=True)
            await message.answer("⚠️ Ошибка при связывании. Попробуйте ещё раз.")
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
        response = supabase_client.table('user_profiles').select('user_id').eq('user_id', user_id).limit(1).execute()
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
    await callback.message.edit_text(
        "🌐 <b>Авторизация на сайте Symed</b>\n\n"
        "1. Откройте <a href=\"https://symed-web.vercel.app/auth\">symed-web.vercel.app/auth</a>\n"
        "2. Нажмите <b>«Войти через Telegram»</b> — код подтвердится автоматически\n\n"
        "<i>Или скопируйте 6-значный код и отправьте его сюда вручную.</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="↩️ Назад", callback_data="back_to_start"),
        ]]),
    )
    await callback.answer()


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
    user_id = message.from_user.id
    try:
        resp = supabase_client.table("user_profiles").select(
            "full_name, phone, birthdate, gender, height, weight, "
            "chronic_diseases, drug_allergies, smoking, hereditary"
        ).eq("user_id", user_id).limit(1).execute()
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


@router.message(F.text.regexp(r'^\d{6}$'))
async def handle_web_auth_code(message: Message):
    """Обработчик ручного ввода 6-значных кодов."""
    from bot.shared import web_auth_codes
    code = message.text.strip()
    entry = web_auth_codes.get(code)
    if not entry:
        await message.answer("❌ Код не найден или уже истёк.\n\nОткройте symed-web.vercel.app и получите новый код.")
        return
    from datetime import datetime as _dt
    age = (_dt.utcnow() - entry['created_at']).total_seconds()
    if age > 600:
        web_auth_codes.pop(code, None)
        await message.answer("⏰ Код истёк (действует 10 минут).\n\nОткройте symed-web.vercel.app и получите новый код.")
        return
    if entry['verified']:
        await message.answer("✅ Этот код уже использован.")
        return
    user = message.from_user
    entry['verified'] = True
    entry['telegram_id'] = user.id
    entry['first_name'] = user.first_name or ''
    entry['last_name'] = user.last_name or ''
    entry['username'] = user.username or ''
    entry['photo_url'] = None
    logger.info(f'Web auth code {code} verified for user_id={user.id}')
    await message.answer("✅ Вы успешно вошли в Symed!\n\nВернитесь на сайт — страница автоматически обновится.")


@router.message(Command("link"))
async def cmd_link(message: Message) -> None:
    """Привязка Telegram-аккаунта к веб-профилю: /link КОД"""
    from bot.shared import link_codes
    from database.connection import supabase_client
    import json

    parts = (message.text or "").strip().split()
    if len(parts) < 2:
        await message.answer(
            "🔗 <b>Привязка аккаунта</b>\n\n"
            "Откройте Symed → Профиль → <b>Подключить Telegram</b>, "
            "получите код и введите:\n<code>/link КОД</code>",
            parse_mode="HTML"
        )
        return

    code = parts[1].strip()
    entry = link_codes.get(code)

    if not entry:
        await message.answer("❌ Код не найден или истёк.\n\nОткройте Symed → Профиль → Подключить Telegram.")
        return

    from datetime import datetime as _dt
    age = (_dt.utcnow() - entry["created_at"]).total_seconds()
    if age > 600:
        link_codes.pop(code, None)
        await message.answer("⏰ Код истёк (10 минут).\n\nПолучите новый код в Symed.")
        return

    if entry.get("verified"):
        await message.answer("✅ Этот код уже использован.")
        return

    tg_user    = message.from_user
    tg_id      = tg_user.id
    web_id     = entry["web_user_id"]

    try:
        # Load both profiles
        tg_resp  = supabase_client.table("user_profiles").select("*").eq("user_id", tg_id).limit(1).execute()
        web_resp = supabase_client.table("user_profiles").select("*").eq("user_id", web_id).limit(1).execute()

        tg_profile  = tg_resp.data[0]  if tg_resp.data  else {}
        web_profile = web_resp.data[0] if web_resp.data else {}

        # Merge: copy non-null Telegram fields into web profile (don't overwrite existing)
        merge_fields = ["birthdate", "gender", "height", "weight", "phone",
                        "chronic_diseases", "drug_allergies", "smoking",
                        "hereditary", "physical_activity"]
        update_web = {"linked_telegram_id": str(tg_id)}
        for field in merge_fields:
            tg_val  = tg_profile.get(field)
            web_val = web_profile.get(field)
            if tg_val and not web_val:
                update_web[field] = tg_val

        # Also merge full_name if web is missing
        if not web_profile.get("full_name") and tg_profile.get("full_name"):
            update_web["full_name"] = tg_profile["full_name"]

        # Update web profile
        supabase_client.table("user_profiles").upsert(
            {"user_id": web_id, **update_web}, on_conflict="user_id"
        ).execute()

        # Update telegram profile: store linked_web_id
        supabase_client.table("user_profiles").upsert(
            {"user_id": tg_id, "linked_web_id": str(web_id)}, on_conflict="user_id"
        ).execute()

        entry["verified"]    = True
        entry["telegram_id"] = tg_id
        link_codes[code]     = entry

        await message.answer(
            "✅ <b>Аккаунты успешно связаны!</b>\n\n"
            "Теперь ваши данные в Telegram и на сайте Symed синхронизированы. "
            "История консультаций и профиль — общие.",
            parse_mode="HTML"
        )
        logger.info(f"Account linked: telegram_id={tg_id} <-> web_id={web_id}")

    except Exception as e:
        logger.error(f"Link error: {e}", exc_info=True)
        await message.answer("⚠️ Ошибка при связывании. Попробуйте ещё раз.")
