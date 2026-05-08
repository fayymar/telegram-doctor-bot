from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext

from bot.states import Registration, EditProfile
from bot.handlers.basic import set_webapp_menu_button
from bot.keyboards import (
    get_main_menu,
    get_phone_keyboard,
    get_gender_keyboard,
    get_cancel_keyboard,
    get_profile_menu,
    get_edit_profile_menu
)
from database.connection import supabase_client
from services.phone_formatter import format_phone_number, get_phone_info
from utils.logger import setup_logger
from utils.validators import (
    validate_full_name,
    validate_age_or_birthdate,
    validate_height,
    validate_weight,
    sanitize_text
)

logger = setup_logger(__name__)
router = Router()


GENDER_TEXT_TO_CODE = {
    "👨 Мужской": "male",
    "👩 Женский": "female",
    "👨 Erkak": "male",
    "👩 Ayol": "female",
}

GENDER_CODE_TO_TEXT = {
    "ru": {
        "male": "👨 Мужской",
        "female": "👩 Женский",
    },
    "uz": {
        "male": "👨 Erkak",
        "female": "👩 Ayol",
    }
}


def _get_gender_keyboard_by_lang(lang: str = "ru"):
    return get_gender_keyboard(lang)


def _format_birthdate_and_age(birthdate_value):
    """
    Возвращает (formatted_birthdate, age)
    """
    if not birthdate_value:
        return "не указано", None

    try:
        if isinstance(birthdate_value, str):
            birthdate_obj = datetime.fromisoformat(birthdate_value)
        else:
            birthdate_obj = datetime.combine(birthdate_value, datetime.min.time())

        age = (datetime.now() - birthdate_obj).days // 365
        return birthdate_obj.strftime("%d.%m.%Y"), age
    except Exception:
        return str(birthdate_value), None


def _upsert_profile_with_fallback(profile_data: dict):
    """Сохраняет профиль в таблицу users по telegram_id."""
    return supabase_client.table("users").upsert(
        profile_data,
        on_conflict="telegram_id"
    ).execute()


async def process_phone_input(message: Message, phone_input: str) -> tuple[bool, str]:
    """
    Обрабатывает ввод телефона и отправляет результат пользователю
    """
    success, formatted_phone, error = format_phone_number(phone_input)

    if not success:
        await message.answer(
            f"{error}\n\n"
            "Примеры правильных форматов:\n"
            "• +998 90 123 45 67 (Узбекистан)\n"
            "• +7 900 123 45 67 (Россия)\n"
            "• +1 555 123 4567 (США)\n"
            "• 90 123 45 67 (для Узбекистана)\n\n"
            "Или нажмите кнопку 📱 Поделиться номером"
        )
        return False, ""

    phone_info = get_phone_info(phone_input)

    info_text = "✅ *Телефон сохранён:*\n\n"
    info_text += f"📱 {formatted_phone}\n"
    if phone_info.get("valid"):
        info_text += f"🌍 {phone_info.get('country_name')} ({phone_info.get('country_code')})\n"
        info_text += f"📞 Тип: {phone_info.get('number_type')}"

    await message.answer(
        info_text,
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="Markdown"
    )

    return True, formatted_phone


# =========================================================
# РЕГИСТРАЦИЯ
# =========================================================

@router.message(Registration.choosing_language, F.text.in_(["🇷🇺 Русский", "🇺🇿 O'zbek"]))
async def process_language_choice(message: Message, state: FSMContext):
    """Обработка выбора языка"""
    lang = "ru" if message.text == "🇷🇺 Русский" else "uz"

    await state.update_data(language=lang)

    welcome_texts = {
        "ru": (
            "👋 Добро пожаловать!\n\n"
            "🩺 *Telegram Medical Bot*\n\n"
            "Я помогу вам:\n"
            "• Определить нужного специалиста\n"
            "• Оценить срочность обращения\n"
            "• Записаться на приём\n\n"
            "Для начала давайте заполним ваш профиль."
        ),
        "uz": (
            "👋 Xush kelibsiz!\n\n"
            "🩺 *Telegram Tibbiy Bot*\n\n"
            "Men sizga yordam beraman:\n"
            "• Kerakli mutaxassisni aniqlash\n"
            "• Murojaat shoshilinchligini baholash\n"
            "• Qabulga yozilish\n\n"
            "Avval profilingizni to'ldiraylik."
        )
    }

    name_prompts = {
        "ru": "👤 *Как вас зовут?*\nВведите ФИО (например: Иванов Иван или Иван Петров)",
        "uz": "👤 *Ismingiz nima?*\nTo'liq ism-familiyangizni kiriting (masalan: Ivanov Ivan)"
    }

    await message.answer(
        welcome_texts[lang],
        parse_mode="Markdown"
    )

    await message.answer(
        name_prompts[lang],
        parse_mode="Markdown"
    )

    await state.set_state(Registration.waiting_for_full_name)


@router.message(F.text == "👤 Профиль")
async def show_profile(message: Message):
    """Показать профиль пользователя"""
    try:
        response = supabase_client.table("users").select(
            "first_name, last_name, phone, date_of_birth, sex, height, weight"
        ).eq("telegram_id", message.from_user.id).execute()

        if not response.data:
            await message.answer(
                "❌ Профиль не найден\n\n"
                "Пожалуйста, пройдите регистрацию:\n"
                "Используйте /start"
            )
            return

        profile = response.data[0]

        first_name = profile.get("first_name") or ""
        last_name = profile.get("last_name") or ""
        full_name = (first_name + " " + last_name).strip() or "не указано"

        birthdate_formatted, age = _format_birthdate_and_age(profile.get("date_of_birth"))

        sex_code = profile.get("sex")
        sex_text = GENDER_CODE_TO_TEXT["ru"].get(sex_code, "не указано")

        profile_text = "👤 *Ваш профиль*\n\n"
        profile_text += f"*ФИО:* {full_name}\n"
        profile_text += f"*Телефон:* {profile.get('phone') or 'не указано'}\n"
        profile_text += f"*Дата рождения:* {birthdate_formatted}"

        if age is not None:
            profile_text += f" ({age} лет)\n"
        else:
            profile_text += "\n"

        profile_text += f"*Пол:* {sex_text}\n"
        profile_text += f"*Рост:* {profile.get('height') or 'не указано'} см\n"
        profile_text += f"*Вес:* {profile.get('weight') or 'не указано'} кг"

        await message.answer(
            profile_text,
            reply_markup=get_profile_menu(),
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.error(f"DB Error in show_profile: {e}", exc_info=True)
        await message.answer("❌ Ошибка при загрузке профиля")


@router.message(F.text == "🔙 В главное меню")
async def back_to_main_from_profile(message: Message, state: FSMContext):
    """Возврат в главное меню из профиля"""
    await state.clear()
    await message.answer(
        "Главное меню",
        reply_markup=get_main_menu()
    )


@router.message(F.text == "📊 Показать ИМТ")
async def show_bmi(message: Message):
    """Показать расчет ИМТ"""
    try:
        from utils.health_calculator import format_bmi_info

        response = supabase_client.table("users").select(
            "height, weight, sex"
        ).eq("telegram_id", message.from_user.id).execute()

        if not response.data:
            await message.answer(
                "❌ Профиль не найден.\nИспользуйте /start для регистрации"
            )
            return

        profile = response.data[0]
        weight = profile.get("weight")
        height = profile.get("height")
        gender = profile.get("sex")

        if not weight or not height:
            await message.answer(
                "❌ Для расчета ИМТ необходимо указать рост и вес\n\n"
                "Пожалуйста, заполните ваш профиль полностью.",
                reply_markup=get_profile_menu()
            )
            return

        bmi_info = format_bmi_info(float(weight), int(height), gender)

        await message.answer(
            bmi_info,
            reply_markup=get_profile_menu(),
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.error(f"Error in show_bmi: {e}", exc_info=True)
        await message.answer(
            "❌ Ошибка при расчете ИМТ",
            reply_markup=get_profile_menu()
        )


# =========================================================
# ЭТАП 1: ФИО
# =========================================================

@router.message(Registration.waiting_for_full_name, F.text)
async def process_full_name(message: Message, state: FSMContext):
    """Обработка ФИО"""
    full_name = sanitize_text(message.text)

    is_valid, error_message = validate_full_name(full_name)
    if not is_valid:
        await message.answer(error_message)
        return

    await state.update_data(full_name=full_name)

    await message.answer(
        f"✅ ФИО: {full_name}",
        reply_markup=ReplyKeyboardRemove()
    )

    await message.answer(
        "📱 *Шаг 2 из 6*\n\n"
        "Поделитесь номером телефона\n\n"
        "Вы можете:\n"
        "• Нажать кнопку ниже\n"
        "• Ввести номер вручную (в любом формате)\n\n"
        "Примеры:\n"
        "• +998 90 123 45 67\n"
        "• 998901234567\n"
        "• 90 123 45 67",
        reply_markup=get_phone_keyboard(),
        parse_mode="Markdown"
    )

    await state.set_state(Registration.waiting_for_phone)


# =========================================================
# ЭТАП 2: ТЕЛЕФОН
# =========================================================

@router.message(Registration.waiting_for_phone, F.contact)
async def process_phone_contact(message: Message, state: FSMContext):
    """Обработка номера через кнопку 'Поделиться номером'"""
    phone = message.contact.phone_number

    success, formatted_phone = await process_phone_input(message, phone)
    if not success:
        return

    await state.update_data(phone=formatted_phone)

    await message.answer(
        "🎂 *Шаг 3 из 6*\n\n"
        "Введите ваш возраст\n\n"
        "Можно просто числом:\n"
        "• 29\n\n"
        "Или датой рождения:\n"
        "• 15.03.1990",
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown"
    )

    await state.set_state(Registration.waiting_for_birthdate)


@router.message(Registration.waiting_for_phone, F.text)
async def process_phone_text(message: Message, state: FSMContext):
    """Обработка номера, введённого текстом"""
    phone_input = message.text.strip()

    success, formatted_phone = await process_phone_input(message, phone_input)
    if not success:
        return

    await state.update_data(phone=formatted_phone)

    await message.answer(
        "🎂 *Шаг 3 из 6*\n\n"
        "Введите ваш возраст\n\n"
        "Можно просто числом:\n"
        "• 29\n\n"
        "Или датой рождения:\n"
        "• 15.03.1990",
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown"
    )

    await state.set_state(Registration.waiting_for_birthdate)


# =========================================================
# ЭТАП 3: ВОЗРАСТ / ДАТА РОЖДЕНИЯ
# =========================================================

@router.message(Registration.waiting_for_birthdate, F.text)
async def process_birthdate(message: Message, state: FSMContext):
    """Обработка возраста или даты рождения"""
    value = sanitize_text(message.text)

    is_valid, error_message, birthdate, age = validate_age_or_birthdate(value)
    if not is_valid or birthdate is None or age is None:
        await message.answer(error_message)
        return

    await state.update_data(
        birthdate=birthdate.date().isoformat(),
        age=age
    )

    if value.isdigit():
        success_text = f"✅ Возраст: {age} лет"
    else:
        success_text = f"✅ Дата рождения: {birthdate.strftime('%d.%m.%Y')} ({age} лет)"

    await message.answer(
        success_text,
        reply_markup=ReplyKeyboardRemove()
    )

    data = await state.get_data()
    lang = data.get("language", "ru")

    await message.answer(
        "⚧️ *Шаг 4 из 6*\n\n"
        "Выберите пол:",
        reply_markup=_get_gender_keyboard_by_lang(lang),
        parse_mode="Markdown"
    )

    await state.set_state(Registration.waiting_for_gender)


# =========================================================
# ЭТАП 4: ПОЛ
# =========================================================

@router.message(Registration.waiting_for_gender, F.text.in_(list(GENDER_TEXT_TO_CODE.keys())))
async def process_gender(message: Message, state: FSMContext):
    """Обработка выбора пола"""
    gender = GENDER_TEXT_TO_CODE[message.text]

    await state.update_data(gender=gender)

    await message.answer(
        f"✅ Пол: {message.text}",
        reply_markup=ReplyKeyboardRemove()
    )

    await message.answer(
        "📏 *Шаг 5 из 6*\n\n"
        "Введите ваш рост в сантиметрах\n"
        "Например: 175",
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown"
    )

    await state.set_state(Registration.waiting_for_height)


@router.message(Registration.waiting_for_gender, F.text)
async def process_gender_invalid(message: Message, state: FSMContext):
    """Подсказка при неверном вводе пола на регистрации"""
    data = await state.get_data()
    await message.answer(
        "Пожалуйста, выберите пол кнопкой ниже.",
        reply_markup=_get_gender_keyboard_by_lang(data.get("language", "ru"))
    )


# =========================================================
# ЭТАП 5: РОСТ
# =========================================================

@router.message(Registration.waiting_for_height, F.text)
async def process_height(message: Message, state: FSMContext):
    """Обработка роста"""
    height_str = sanitize_text(message.text)

    is_valid, error_message, height = validate_height(height_str)
    if not is_valid:
        await message.answer(error_message)
        return

    await state.update_data(height=height)

    await message.answer(
        f"✅ Рост: {height} см",
        reply_markup=ReplyKeyboardRemove()
    )

    await message.answer(
        "⚖️ *Шаг 6 из 6*\n\n"
        "Введите ваш вес в килограммах\n"
        "Например: 70 или 70.5",
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown"
    )

    await state.set_state(Registration.waiting_for_weight)


# =========================================================
# ЭТАП 6: ВЕС
# =========================================================

@router.message(Registration.waiting_for_weight, F.text)
async def process_weight(message: Message, state: FSMContext):
    """Обработка веса и завершение регистрации"""
    weight_str = sanitize_text(message.text)

    is_valid, error_message, weight = validate_weight(weight_str)
    if not is_valid:
        await message.answer(error_message)
        return

    await state.update_data(weight=weight)

    await message.answer(
        f"✅ Вес: {weight} кг",
        reply_markup=ReplyKeyboardRemove()
    )

    data = await state.get_data()

    try:
        full_name_parts = data["full_name"].strip().split()
        first_name = full_name_parts[0] if full_name_parts else ""
        last_name = " ".join(full_name_parts[1:]) if len(full_name_parts) > 1 else None

        profile_data = {
            "telegram_id": message.from_user.id,
            "first_name": first_name,
            "last_name": last_name,
            "phone": data["phone"],
            "date_of_birth": data["birthdate"],
            "sex": data["gender"],
            "height": data["height"],
            "weight": data["weight"],
        }

        result = _upsert_profile_with_fallback(profile_data)

        logger.info(
            "Профиль сохранён успешно | user_id=%s | result=%s",
            message.from_user.id,
            result
        )

        completion_texts = {
            "ru": (
                "🎉 *Регистрация завершена!*\n\n"
                "Ваш профиль успешно создан.\n"
                "Теперь вы можете пользоваться всеми функциями бота!"
            ),
            "uz": (
                "🎉 *Ro'yxatdan o'tish yakunlandi!*\n\n"
                "Profilingiz muvaffaqiyatli yaratildi.\n"
                "Endi siz botning barcha funksiyalaridan foydalanishingiz mumkin!"
            )
        }

        await message.answer(
            completion_texts.get(lang, completion_texts["ru"]),
            reply_markup=get_main_menu(),
            parse_mode="Markdown"
        )

        await message.answer(
            "✅ Профиль сохранён! Вы можете просматривать и редактировать его "
            "в приложении СимптоМед (кнопка внизу экрана)."
        )

        # Устанавливаем Menu Button после завершения регистрации
        try:
            await set_webapp_menu_button(message.bot, message.chat.id)
            logger.info("Menu button set after registration | user_id=%s", message.from_user.id)
        except Exception as menu_err:
            logger.warning("Failed to set menu button | user_id=%s: %s", message.from_user.id, menu_err)

        await state.clear()

    except Exception as e:
        logger.exception("Ошибка при сохранении профиля user_id=%s", message.from_user.id)

        error_text = str(e)
        if len(error_text) > 500:
            error_text = error_text[:500] + "..."

        await message.answer(
            f"❌ Ошибка при сохранении профиля:\n{error_text}\n\n"
            "Попробуйте ещё раз: /start"
        )
        await state.clear()


# =========================================================
# РЕДАКТИРОВАНИЕ ПРОФИЛЯ
# =========================================================

@router.message(F.text == "✏️ Изменить данные")
async def edit_profile_menu(message: Message, state: FSMContext):
    """Меню редактирования профиля"""
    await message.answer(
        "✏️ *Редактирование профиля*\n\n"
        "Что вы хотите изменить?",
        reply_markup=get_edit_profile_menu(),
        parse_mode="Markdown"
    )

    await state.set_state(EditProfile.choosing_field)


@router.message(F.text == "🔙 Назад к профилю")
async def back_to_profile(message: Message, state: FSMContext):
    """Возврат к профилю"""
    await state.clear()
    await show_profile(message)


# =========================================================
# ВЫБОР ПОЛЯ ДЛЯ РЕДАКТИРОВАНИЯ
# =========================================================

@router.message(EditProfile.choosing_field, F.text == "👤 ФИО")
async def edit_full_name_start(message: Message, state: FSMContext):
    await message.answer(
        "👤 Введите новое ФИО:",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(EditProfile.waiting_for_full_name)


@router.message(EditProfile.choosing_field, F.text == "📱 Телефон")
async def edit_phone_start(message: Message, state: FSMContext):
    await message.answer(
        "📱 Введите новый номер телефона\n\n"
        "Примеры форматов:\n"
        "• +998 90 123 45 67\n"
        "• +7 900 123 45 67\n"
        "• 90 123 45 67",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(EditProfile.waiting_for_phone)


@router.message(EditProfile.choosing_field, F.text == "🎂 Дата рождения")
async def edit_birthdate_start(message: Message, state: FSMContext):
    await message.answer(
        "🎂 Введите возраст или дату рождения\n\n"
        "Примеры:\n"
        "• 29\n"
        "• 15.03.1990",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(EditProfile.waiting_for_birthdate)


@router.message(EditProfile.choosing_field, F.text == "⚧️ Пол")
async def edit_gender_start(message: Message, state: FSMContext):
    data = await state.get_data()
    await message.answer(
        "⚧️ Выберите пол:",
        reply_markup=_get_gender_keyboard_by_lang(data.get("language", "ru"))
    )
    await state.set_state(EditProfile.waiting_for_gender)


@router.message(EditProfile.choosing_field, F.text == "📏 Рост")
async def edit_height_start(message: Message, state: FSMContext):
    await message.answer(
        "📏 Введите новый рост (в см):",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(EditProfile.waiting_for_height)


@router.message(EditProfile.choosing_field, F.text == "⚖️ Вес")
async def edit_weight_start(message: Message, state: FSMContext):
    await message.answer(
        "⚖️ Введите новый вес (в кг):",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(EditProfile.waiting_for_weight)


# =========================================================
# ОБРАБОТКА РЕДАКТИРОВАНИЯ
# =========================================================

@router.message(EditProfile.waiting_for_full_name, F.text)
async def edit_full_name(message: Message, state: FSMContext):
    full_name = sanitize_text(message.text)

    is_valid, error_message = validate_full_name(full_name)
    if not is_valid:
        await message.answer(error_message)
        return

    try:
        parts = full_name.strip().split()
        first_name = parts[0] if parts else ""
        last_name = " ".join(parts[1:]) if len(parts) > 1 else None
        supabase_client.table("users").update({
            "first_name": first_name,
            "last_name": last_name,
        }).eq("telegram_id", message.from_user.id).execute()

        await message.answer(f"✅ ФИО обновлено: {full_name}")
        await message.answer("Что ещё хотите изменить?", reply_markup=get_edit_profile_menu())
        await state.set_state(EditProfile.choosing_field)

    except Exception as e:
        logger.error(f"DB Error in edit_full_name: {e}", exc_info=True)
        await message.answer("❌ Ошибка при сохранении")


@router.message(EditProfile.waiting_for_phone, F.text)
async def edit_phone(message: Message, state: FSMContext):
    phone_input = message.text.strip()

    success, formatted_phone, error = format_phone_number(phone_input)
    if not success:
        await message.answer(
            f"{error}\n\nПопробуйте ещё раз:"
        )
        return

    try:
        phone_info = get_phone_info(phone_input)

        supabase_client.table("users").update({
            "phone": formatted_phone,
        }).eq("telegram_id", message.from_user.id).execute()

        info_text = "✅ *Телефон обновлён:*\n\n"
        info_text += f"📱 {formatted_phone}\n"
        if phone_info.get("valid"):
            info_text += f"🌍 {phone_info.get('country_name')} ({phone_info.get('country_code')})\n"
            info_text += f"📞 Тип: {phone_info.get('number_type')}"

        await message.answer(info_text, parse_mode="Markdown")
        await message.answer("Что ещё хотите изменить?", reply_markup=get_edit_profile_menu())
        await state.set_state(EditProfile.choosing_field)

    except Exception as e:
        logger.error(f"DB Error in edit_phone: {e}", exc_info=True)
        await message.answer("❌ Ошибка при сохранении телефона")


@router.message(EditProfile.waiting_for_birthdate, F.text)
async def edit_birthdate(message: Message, state: FSMContext):
    """Редактирование возраста или даты рождения"""
    value = sanitize_text(message.text)

    is_valid, error_message, birthdate, age = validate_age_or_birthdate(value)
    if not is_valid or birthdate is None or age is None:
        await message.answer(error_message)
        return

    try:
        supabase_client.table("users").update({
            "date_of_birth": birthdate.date().isoformat(),
        }).eq("telegram_id", message.from_user.id).execute()

        if value.isdigit():
            text = f"✅ Возраст обновлён: {age} лет"
        else:
            text = f"✅ Дата рождения обновлена: {birthdate.strftime('%d.%m.%Y')} ({age} лет)"

        await message.answer(text)
        await message.answer("Что ещё хотите изменить?", reply_markup=get_edit_profile_menu())
        await state.set_state(EditProfile.choosing_field)

    except Exception as e:
        logger.error(f"DB Error in edit_birthdate: {e}", exc_info=True)
        await message.answer(f"❌ Ошибка при сохранении:\n{str(e)}")


@router.message(EditProfile.waiting_for_gender, F.text.in_(list(GENDER_TEXT_TO_CODE.keys())))
async def edit_gender(message: Message, state: FSMContext):
    gender = GENDER_TEXT_TO_CODE[message.text]

    try:
        supabase_client.table("users").update({
            "sex": gender,
        }).eq("telegram_id", message.from_user.id).execute()

        await message.answer(
            f"✅ Пол обновлён: {message.text}",
            reply_markup=ReplyKeyboardRemove()
        )
        await message.answer("Что ещё хотите изменить?", reply_markup=get_edit_profile_menu())
        await state.set_state(EditProfile.choosing_field)

    except Exception as e:
        logger.error(f"DB Error in edit_gender: {e}", exc_info=True)
        await message.answer("❌ Ошибка при сохранении")


@router.message(EditProfile.waiting_for_gender, F.text)
async def edit_gender_invalid(message: Message, state: FSMContext):
    await message.answer(
        "Пожалуйста, выберите пол кнопкой ниже.",
        reply_markup=_get_gender_keyboard_by_lang((await state.get_data()).get("language", "ru"))
    )


@router.message(EditProfile.waiting_for_height, F.text)
async def edit_height(message: Message, state: FSMContext):
    height_str = sanitize_text(message.text)

    is_valid, error_message, height = validate_height(height_str)
    if not is_valid:
        await message.answer(error_message)
        return

    try:
        supabase_client.table("users").update({
            "height": height,
        }).eq("telegram_id", message.from_user.id).execute()

        await message.answer(f"✅ Рост обновлён: {height} см")
        await message.answer("Что ещё хотите изменить?", reply_markup=get_edit_profile_menu())
        await state.set_state(EditProfile.choosing_field)

    except Exception as e:
        logger.error(f"DB Error in edit_height: {e}", exc_info=True)
        await message.answer("❌ Ошибка при сохранении")


@router.message(EditProfile.waiting_for_weight, F.text)
async def edit_weight(message: Message, state: FSMContext):
    weight_str = sanitize_text(message.text)

    is_valid, error_message, weight = validate_weight(weight_str)
    if not is_valid:
        await message.answer(error_message)
        return

    try:
        supabase_client.table("users").update({
            "weight": weight,
        }).eq("telegram_id", message.from_user.id).execute()

        await message.answer(f"✅ Вес обновлён: {weight} кг")
        await message.answer("Что ещё хотите изменить?", reply_markup=get_edit_profile_menu())
        await state.set_state(EditProfile.choosing_field)

    except Exception as e:
        logger.error(f"DB Error in edit_weight: {e}", exc_info=True)
        await message.answer("❌ Ошибка при сохранении")


# =========================================================
# ОТМЕНА
# =========================================================

@router.message(F.text == "❌ Отменить")
async def cancel_profile_action(message: Message, state: FSMContext):
    """Отмена действия в профиле"""
    current_state = await state.get_state()

    if current_state and current_state.startswith("Registration:"):
        await state.clear()
        await message.answer(
            "❌ Регистрация отменена\n\n"
            "Для начала регистрации используйте /start",
            reply_markup=ReplyKeyboardRemove()
        )
    elif current_state and current_state.startswith("EditProfile:"):
        await message.answer(
            "❌ Изменение отменено",
            reply_markup=get_edit_profile_menu()
        )
        await state.set_state(EditProfile.choosing_field)
    else:
        await state.clear()
        await message.answer(
            "Главное меню",
            reply_markup=get_main_menu()
        )
