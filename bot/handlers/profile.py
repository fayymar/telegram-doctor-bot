from datetime import datetime
from aiogram import Router, F
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
)
from aiogram.fsm.context import FSMContext

from bot.states import Registration, EditProfile
from bot.handlers.basic import set_webapp_menu_button
from bot.keyboards import (
    get_main_menu,
    get_phone_keyboard,
    get_gender_keyboard,
    get_cancel_keyboard,
    get_profile_menu,
    get_edit_profile_menu,
    get_step_keyboard_with_back,
    get_phone_keyboard_with_back,
)
from database.connection import supabase_client
from postgrest.exceptions import APIError
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


_OPTIONAL_PROFILE_COLUMNS = {
    "language", "chronic_diseases", "drug_allergies", "smoking", "hereditary",
}

# Списки (не set!) — нужны для индексации в callback_data
CHRONIC_OPTIONS = [
    "Гипертония", "Диабет 1 типа", "Диабет 2 типа", "Болезни сердца",
    "Астма", "ХОБЛ", "Гастрит/язва", "Болезни почек",
    "Щитовидная железа", "Эпилепсия",
]
HEREDITARY_OPTIONS = [
    "Болезни сердца", "Инсульт", "Диабет", "Онкология",
    "Гипертония", "Альцгеймер",
]
ALLERGY_OPTIONS = [
    "Пенициллин/антибиотики", "Аспирин/НПВП", "Сульфаниламиды", "Анестетики",
]
_SMOKING_BUTTON_MAP = {
    "🚭 Не курю": "no",
    "🚬 Курю": "yes",
    "✅ Бросил(а)": "quit",
}


def build_chronic_reply_keyboard(selected: list) -> ReplyKeyboardMarkup:
    buttons = []
    for i in range(0, len(CHRONIC_OPTIONS), 2):
        row = []
        for opt in CHRONIC_OPTIONS[i:i + 2]:
            label = f"✅ {opt}" if opt in selected else opt
            row.append(KeyboardButton(text=label))
        buttons.append(row)
    buttons.append([
        KeyboardButton(text="🚫 Ничего из этого"),
        KeyboardButton(text="➡️ Готово"),
    ])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def build_hereditary_reply_keyboard(selected: list) -> ReplyKeyboardMarkup:
    buttons = []
    for i in range(0, len(HEREDITARY_OPTIONS), 2):
        row = []
        for opt in HEREDITARY_OPTIONS[i:i + 2]:
            label = f"✅ {opt}" if opt in selected else opt
            row.append(KeyboardButton(text=label))
        buttons.append(row)
    buttons.append([
        KeyboardButton(text="🚫 Ничего из этого"),
        KeyboardButton(text="➡️ Готово"),
    ])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def build_allergy_reply_keyboard(selected: list) -> ReplyKeyboardMarkup:
    buttons = []
    for i in range(0, len(ALLERGY_OPTIONS), 2):
        row = []
        for opt in ALLERGY_OPTIONS[i:i + 2]:
            label = f"✅ {opt}" if opt in selected else opt
            row.append(KeyboardButton(text=label))
        buttons.append(row)
    buttons.append([
        KeyboardButton(text="Аллергий нет"),
        KeyboardButton(text="✏️ Написать своё"),
    ])
    buttons.append([KeyboardButton(text="➡️ Готово")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def build_smoking_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[
            KeyboardButton(text="🚭 Не курю"),
            KeyboardButton(text="🚬 Курю"),
            KeyboardButton(text="✅ Бросил(а)"),
        ]],
        resize_keyboard=True,
    )


def _upsert_profile_with_fallback(profile_data: dict):
    """Сохраняет профиль; при ошибке схемы повторяет без необязательных колонок."""
    try:
        return supabase_client.table("user_profiles").upsert(
            profile_data,
            on_conflict="user_id"
        ).execute()
    except APIError as e:
        error_text = str(e).lower()
        if "column" not in error_text and "schema cache" not in error_text:
            raise
        logger.warning(f"Schema error, retrying without optional columns: {e}")
        fallback_data = {k: v for k, v in profile_data.items()
                        if k not in _OPTIONAL_PROFILE_COLUMNS}
        return supabase_client.table("user_profiles").upsert(
            fallback_data,
            on_conflict="user_id"
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
        response = supabase_client.table("user_profiles").select(
            "full_name, phone, birthdate, gender, height, weight, "
            "chronic_diseases, drug_allergies, smoking, hereditary, language"
        ).eq("user_id", message.from_user.id).execute()

        if not response.data:
            await message.answer(
                "❌ Профиль не найден\n\n"
                "Пожалуйста, пройдите регистрацию:\n"
                "Используйте /start"
            )
            return

        profile = response.data[0]
        lang = profile.get("language", "ru")

        birthdate_formatted, age = _format_birthdate_and_age(profile.get("birthdate"))

        gender_code = profile.get("gender")
        sex_text = GENDER_CODE_TO_TEXT.get(lang, GENDER_CODE_TO_TEXT["ru"]).get(gender_code, "не указано")

        profile_text = "👤 *Ваш профиль*\n\n"
        profile_text += f"*ФИО:* {profile.get('full_name', 'не указано')}\n"
        profile_text += f"*Телефон:* {profile.get('phone', 'не указано')}\n"
        profile_text += f"*Дата рождения:* {birthdate_formatted}"

        if age is not None:
            profile_text += f" ({age} лет)\n"
        else:
            profile_text += "\n"

        profile_text += f"*Пол:* {sex_text}\n"
        profile_text += f"*Рост:* {profile.get('height', 'не указано')} см\n"
        profile_text += f"*Вес:* {profile.get('weight', 'не указано')} кг\n"

        chronic = profile.get("chronic_diseases") or []
        profile_text += f"*Хронические:* {', '.join(chronic) if chronic else 'не указано'}\n"
        hereditary = profile.get("hereditary") or []
        profile_text += f"*Наследственность:* {', '.join(hereditary) if hereditary else 'не указано'}\n"
        allergies = (profile.get("drug_allergies") or "").strip()
        profile_text += f"*Аллергии:* {allergies if allergies else 'не указано'}\n"
        _sm = {"yes": "🚬 Курит", "quit": "✅ Бросил(а)", "no": "🚭 Не курит"}
        profile_text += f"*Курение:* {_sm.get(profile.get('smoking', 'no'), '—')}"

        await message.answer(
            profile_text,
            reply_markup=get_profile_menu(),
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.error(f"DB Error in show_profile: {e}", exc_info=True)
        await message.answer("❌ Ошибка при загрузке профиля")


@router.message(F.text == "🔙 Главное меню")
async def back_to_main_from_profile(message: Message, state: FSMContext):
    """Возврат в главное меню из профиля"""
    await state.clear()
    await message.answer("Главное меню", reply_markup=get_main_menu())


@router.message(F.text == "📊 Показать ИМТ")
async def show_bmi(message: Message):
    """Показать расчет ИМТ"""
    try:
        from utils.health_calculator import format_bmi_info

        response = supabase_client.table("user_profiles").select(
            "height, weight, gender"
        ).eq("user_id", message.from_user.id).execute()

        if not response.data:
            await message.answer(
                "❌ Профиль не найден.\nИспользуйте /start для регистрации"
            )
            return

        profile = response.data[0]
        weight = profile.get("weight")
        height = profile.get("height")
        gender = profile.get("gender")

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


# =========================================================
# КНОПКА НАЗАД — обработчики для каждого шага
# =========================================================

BACK_TEXT = "◀️ Назад"
CANCEL_TEXT = "❌ Отмена"

@router.message(Registration.waiting_for_phone, F.text == BACK_TEXT)
async def back_to_name(message: Message, state: FSMContext):
    """Назад к вводу ФИО."""
    data = await state.get_data()
    lang = data.get("language", "ru")
    await state.set_state(Registration.waiting_for_full_name)
    await message.answer(
        "◀️ Вернулись к шагу 1\n\nВведите ваше ФИО:",
        reply_markup=get_step_keyboard_with_back()
    )


@router.message(Registration.waiting_for_birthdate, F.text == BACK_TEXT)
async def back_to_phone(message: Message, state: FSMContext):
    """Назад к вводу телефона."""
    await state.set_state(Registration.waiting_for_phone)
    await message.answer(
        "◀️ Вернулись к шагу 2\n\n📱 Введите номер телефона:",
        reply_markup=get_phone_keyboard_with_back()
    )


@router.message(Registration.waiting_for_gender, F.text == BACK_TEXT)
async def back_to_birthdate(message: Message, state: FSMContext):
    """Назад к вводу даты рождения."""
    await state.set_state(Registration.waiting_for_birthdate)
    await message.answer(
        "◀️ Вернулись к шагу 3\n\n🎂 Введите дату рождения (ДД.ММ.ГГГГ):",
        reply_markup=get_step_keyboard_with_back()
    )


@router.message(Registration.waiting_for_height, F.text == BACK_TEXT)
async def back_to_gender(message: Message, state: FSMContext):
    """Назад к выбору пола."""
    await state.set_state(Registration.waiting_for_gender)
    await message.answer(
        "◀️ Вернулись к шагу 4\n\n⚧ Укажите ваш пол:",
        reply_markup=get_gender_keyboard()
    )


@router.message(Registration.waiting_for_weight, F.text == BACK_TEXT)
async def back_to_height(message: Message, state: FSMContext):
    """Назад к вводу роста."""
    await state.set_state(Registration.waiting_for_height)
    await message.answer(
        "◀️ Вернулись к шагу 5\n\n📏 Введите ваш рост в сантиметрах (например: 175):",
        reply_markup=get_step_keyboard_with_back()
    )


@router.message(Registration.waiting_for_chronic, F.text == BACK_TEXT)
async def back_to_weight(message: Message, state: FSMContext):
    """Назад к вводу веса."""
    await state.set_state(Registration.waiting_for_weight)
    await message.answer(
        "◀️ Вернулись к шагу 6\n\n⚖️ Введите ваш вес в кг (например: 70):",
        reply_markup=get_step_keyboard_with_back()
    )


@router.message(Registration.waiting_for_hereditary, F.text == BACK_TEXT)
async def back_to_chronic(message: Message, state: FSMContext):
    """Назад к хроническим заболеваниям."""
    data = await state.get_data()
    selected = data.get("chronic_diseases", [])
    await state.set_state(Registration.waiting_for_chronic)
    from bot.handlers.profile import build_chronic_keyboard
    await message.answer(
        "◀️ Вернулись к шагу 1 из 4 (анамнез)\n\nВыберите хронические заболевания:",
        reply_markup=build_chronic_keyboard(selected)
    )


@router.message(Registration.waiting_for_allergies, F.text == BACK_TEXT)
@router.message(Registration.waiting_for_allergies_text, F.text == BACK_TEXT)
async def back_to_hereditary(message: Message, state: FSMContext):
    """Назад к наследственным заболеваниям."""
    data = await state.get_data()
    selected = data.get("hereditary", [])
    await state.set_state(Registration.waiting_for_hereditary)
    from bot.handlers.profile import build_hereditary_keyboard
    await message.answer(
        "◀️ Вернулись к шагу 2 из 4 (анамнез)\n\nВыберите наследственные заболевания:",
        reply_markup=build_hereditary_keyboard(selected)
    )


@router.message(Registration.waiting_for_smoking, F.text == BACK_TEXT)
async def back_to_allergies(message: Message, state: FSMContext):
    """Назад к аллергиям."""
    data = await state.get_data()
    selected = data.get("allergies_selected", [])
    await state.set_state(Registration.waiting_for_allergies)
    from bot.handlers.profile import build_allergies_keyboard
    await message.answer(
        "◀️ Вернулись к шагу 3 из 4 (анамнез)\n\nЕсть ли аллергия на лекарства?",
        reply_markup=build_allergies_keyboard(selected)
    )


# Отмена регистрации из любого шага
@router.message(F.text == CANCEL_TEXT)
async def cancel_registration(message: Message, state: FSMContext):
    """Отмена из любого шага регистрации."""
    current = await state.get_state()
    if current and current.startswith("Registration"):
        await state.clear()
        await message.answer(
            "❌ Регистрация отменена.\n\nДля начала отправьте /start",
            reply_markup=ReplyKeyboardRemove()
        )
    else:
        pass  # Не наша отмена, пусть другой обработчик поймает


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
        reply_markup=get_phone_keyboard_with_back(),
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
        reply_markup=get_step_keyboard_with_back(),
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
        reply_markup=get_step_keyboard_with_back(),
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
        reply_markup=get_step_keyboard_with_back(),
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
# ЭТАП 6: ВЕС → переход к анамнезу
# =========================================================

@router.message(Registration.waiting_for_weight, F.text)
async def process_weight(message: Message, state: FSMContext):
    weight_str = sanitize_text(message.text)
    is_valid, error_message, weight = validate_weight(weight_str)
    if not is_valid:
        await message.answer(error_message)
        return
    await state.update_data(weight=weight)
    await message.answer(f"✅ Вес: {weight} кг", reply_markup=ReplyKeyboardRemove())
    await _send_chronic_step(message, state)


# =========================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ — запуск каждого шага анамнеза
# =========================================================

async def _send_chronic_step(message: Message, state: FSMContext):
    data = await state.get_data()
    selected = data.get("selected_chronic") or []
    await state.set_state(Registration.waiting_for_chronic)
    await message.answer(
        "📋 *Медицинская история (шаг 1 из 4)*\n\n"
        "Есть ли у вас хронические заболевания?\n"
        "Нажимайте кнопки для выбора/отмены:",
        reply_markup=build_chronic_reply_keyboard(selected),
        parse_mode="Markdown",
    )


async def _send_hereditary_step(message: Message, state: FSMContext):
    data = await state.get_data()
    selected = data.get("selected_hereditary") or []
    await state.set_state(Registration.waiting_for_hereditary)
    await message.answer(
        "📋 *Медицинская история (шаг 2 из 4)*\n\n"
        "Есть ли у ваших близких родственников эти заболевания?\n"
        "Нажимайте кнопки для выбора/отмены:",
        reply_markup=build_hereditary_reply_keyboard(selected),
        parse_mode="Markdown",
    )


async def _send_allergy_step(message: Message, state: FSMContext):
    data = await state.get_data()
    selected = data.get("selected_allergies") or []
    await state.set_state(Registration.waiting_for_allergies)
    await message.answer(
        "📋 *Медицинская история (шаг 3 из 4)*\n\n"
        "Есть ли у вас аллергия на лекарства?\n"
        "Нажимайте кнопки для выбора/отмены:",
        reply_markup=build_allergy_reply_keyboard(selected),
        parse_mode="Markdown",
    )


async def _send_smoking_step(message: Message, state: FSMContext):
    await state.set_state(Registration.waiting_for_smoking)
    await message.answer(
        "📋 *Медицинская история (шаг 4 из 4)*\n\nВы курите?",
        reply_markup=build_smoking_reply_keyboard(),
        parse_mode="Markdown",
    )


# =========================================================
# ЭТАПЫ 7-10: АНАМНЕЗ — REPLY KEYBOARD С TOGGLE
# =========================================================

@router.message(Registration.waiting_for_chronic, F.text)
async def handle_chronic_input(message: Message, state: FSMContext):
    text = message.text.strip()
    data = await state.get_data()
    selected = list(data.get("selected_chronic") or [])

    if text == "➡️ Готово":
        await state.update_data(selected_chronic=selected)
        await _send_hereditary_step(message, state)
        return
    if text == "🚫 Ничего из этого":
        await state.update_data(selected_chronic=[])
        await _send_hereditary_step(message, state)
        return

    clean = text[2:] if text.startswith("✅ ") else text
    if clean in CHRONIC_OPTIONS:
        if clean in selected:
            selected.remove(clean)
        else:
            selected.append(clean)
        await state.update_data(selected_chronic=selected)
        await message.answer(
            f"Выбрано: {', '.join(selected) if selected else 'пусто'}\n"
            "Продолжайте или нажмите «Готово»:",
            reply_markup=build_chronic_reply_keyboard(selected),
        )


@router.message(Registration.waiting_for_hereditary, F.text)
async def handle_hereditary_input(message: Message, state: FSMContext):
    text = message.text.strip()
    data = await state.get_data()
    selected = list(data.get("selected_hereditary") or [])

    if text == "➡️ Готово":
        await state.update_data(selected_hereditary=selected)
        await _send_allergy_step(message, state)
        return
    if text == "🚫 Ничего из этого":
        await state.update_data(selected_hereditary=[])
        await _send_allergy_step(message, state)
        return

    clean = text[2:] if text.startswith("✅ ") else text
    if clean in HEREDITARY_OPTIONS:
        if clean in selected:
            selected.remove(clean)
        else:
            selected.append(clean)
        await state.update_data(selected_hereditary=selected)
        await message.answer(
            f"Выбрано: {', '.join(selected) if selected else 'пусто'}\n"
            "Продолжайте или нажмите «Готово»:",
            reply_markup=build_hereditary_reply_keyboard(selected),
        )


@router.message(Registration.waiting_for_allergies, F.text)
async def handle_allergy_input(message: Message, state: FSMContext):
    text = message.text.strip()
    data = await state.get_data()
    selected = list(data.get("selected_allergies") or [])

    if text == "➡️ Готово":
        await state.update_data(selected_allergies=selected)
        await _send_smoking_step(message, state)
        return
    if text == "Аллергий нет":
        await state.update_data(selected_allergies=[])
        await _send_smoking_step(message, state)
        return
    if text == "✏️ Написать своё":
        await state.set_state(Registration.waiting_for_allergies_text)
        await message.answer(
            "✏️ Напишите, на какие лекарства у вас аллергия:",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    clean = text[2:] if text.startswith("✅ ") else text
    if clean in ALLERGY_OPTIONS:
        if clean in selected:
            selected.remove(clean)
        else:
            selected.append(clean)
        await state.update_data(selected_allergies=selected)
        await message.answer(
            f"Выбрано: {', '.join(selected) if selected else 'пусто'}\n"
            "Продолжайте или нажмите «Готово»:",
            reply_markup=build_allergy_reply_keyboard(selected),
        )


@router.message(Registration.waiting_for_allergies_text, F.text)
async def process_allergy_text(message: Message, state: FSMContext):
    await state.update_data(selected_allergies=[sanitize_text(message.text)])
    await _send_smoking_step(message, state)


@router.message(Registration.waiting_for_smoking, F.text.in_(set(_SMOKING_BUTTON_MAP.keys())))
async def process_smoking(message: Message, state: FSMContext):
    smoking_value = _SMOKING_BUTTON_MAP[message.text]
    data = await state.get_data()
    chronic_list = data.get("selected_chronic") or []
    hereditary_list = data.get("selected_hereditary") or []
    allergies_str = ", ".join(data.get("selected_allergies") or [])

    await message.answer(f"✅ Курение сохранено.", reply_markup=ReplyKeyboardRemove())

    is_update = data.get("is_anamnesis_update", False)

    if is_update:
        try:
            supabase_client.table("user_profiles").update({
                "chronic_diseases": chronic_list,
                "hereditary": hereditary_list,
                "drug_allergies": allergies_str,
                "smoking": smoking_value,
                "updated_at": datetime.now().isoformat(),
            }).eq("user_id", message.from_user.id).execute()
            logger.info("Anamnesis updated | user_id=%s", message.from_user.id)
            await message.answer(
                "✅ *Медицинская история обновлена!*\n\n"
                "AI-диагностика будет учитывать обновлённые данные.",
                reply_markup=get_main_menu(),
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.exception("Error updating anamnesis | user_id=%s", message.from_user.id)
            await message.answer(
                f"❌ Ошибка: {str(e)[:200]}",
                reply_markup=get_main_menu(),
            )
        await state.clear()
        return

    # Полное сохранение профиля (регистрация)
    lang = data.get("language", "ru")
    try:
        profile_data = {
            "user_id": message.from_user.id,
            "username": message.from_user.username,
            "full_name": data["full_name"],
            "phone": data["phone"],
            "birthdate": data["birthdate"],
            "gender": data["gender"],
            "height": data["height"],
            "weight": data["weight"],
            "language": lang,
            "updated_at": datetime.now().isoformat(),
            "chronic_diseases": chronic_list,
            "hereditary": hereditary_list,
            "drug_allergies": allergies_str,
            "smoking": smoking_value,
        }
        _upsert_profile_with_fallback(profile_data)
        logger.info(
            "Full profile + anamnesis saved | user_id=%s | chronic=%s | hereditary=%s | allergies=%s | smoking=%s",
            message.from_user.id, chronic_list, hereditary_list, allergies_str, smoking_value,
        )
        await message.answer(
            "🎉 *Профиль и медицинская история сохранены!*\n\n"
            "Теперь AI-диагностика будет учитывать ваши данные для более точных рекомендаций.",
            reply_markup=get_main_menu(),
            parse_mode="Markdown",
        )
        await message.answer(
            "✅ Профиль сохранён! Вы можете просматривать и редактировать его "
            "в приложении СимптоМед (кнопка внизу экрана)."
        )
        try:
            await set_webapp_menu_button(message.bot, message.chat.id)
        except Exception as menu_err:
            logger.warning("Failed to set menu button: %s", menu_err)
        await state.clear()
    except Exception as e:
        logger.exception("Ошибка при сохранении профиля user_id=%s", message.from_user.id)
        await message.answer(
            f"❌ Ошибка при сохранении профиля:\n{str(e)[:500]}\n\nПопробуйте ещё раз: /start"
        )
        await state.clear()


# =========================================================
# ОБНОВЛЕНИЕ АНАМНЕЗА (из профиля)
# =========================================================

@router.message(F.text == "📋 Обновить медицинскую историю")
async def update_anamnesis_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    pre = {"is_anamnesis_update": True, "selected_chronic": [], "selected_hereditary": [], "selected_allergies": []}
    try:
        result = supabase_client.table("user_profiles").select(
            "chronic_diseases, hereditary, drug_allergies, smoking"
        ).eq("user_id", user_id).limit(1).execute()
        if result.data:
            p = result.data[0]
            pre["selected_chronic"] = p.get("chronic_diseases") or []
            pre["selected_hereditary"] = p.get("hereditary") or []
            allergy_raw = p.get("drug_allergies") or ""
            pre["selected_allergies"] = [allergy_raw] if allergy_raw else []
    except Exception as e:
        logger.error(f"Error loading anamnesis for user {user_id}: {e}")
    await state.set_data(pre)
    await _send_chronic_step(message, state)


# =========================================================
# РЕДАКТИРОВАНИЕ ПРОФИЛЯ
# =========================================================

@router.message(F.text == "✏️ Изменить данные профиля")
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
        supabase_client.table("user_profiles").update({
            "full_name": full_name,
            "updated_at": datetime.now().isoformat(),
        }).eq("user_id", message.from_user.id).execute()

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

        supabase_client.table("user_profiles").update({
            "phone": formatted_phone,
            "updated_at": datetime.now().isoformat(),
        }).eq("user_id", message.from_user.id).execute()

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
        supabase_client.table("user_profiles").update({
            "birthdate": birthdate.date().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }).eq("user_id", message.from_user.id).execute()

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
        supabase_client.table("user_profiles").update({
            "gender": gender,
            "updated_at": datetime.now().isoformat(),
        }).eq("user_id", message.from_user.id).execute()

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
        supabase_client.table("user_profiles").update({
            "height": height,
            "updated_at": datetime.now().isoformat(),
        }).eq("user_id", message.from_user.id).execute()

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
        supabase_client.table("user_profiles").update({
            "weight": weight,
            "updated_at": datetime.now().isoformat(),
        }).eq("user_id", message.from_user.id).execute()

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
