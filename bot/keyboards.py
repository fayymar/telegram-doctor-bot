from aiogram.types import (
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

# ============ ГЛАВНОЕ МЕНЮ ============

def get_main_menu() -> ReplyKeyboardMarkup:
    """Главное меню бота"""
    keyboard = [
        [KeyboardButton(text="🩺 Новая консультация")],
        [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="📋 История")],
        [KeyboardButton(text="💊 Лекарства"), KeyboardButton(text="📓 Дневник")],
        [KeyboardButton(text="🏥 Клиники и специалисты")],
        [KeyboardButton(text="💾 Экспорт анамнеза"), KeyboardButton(text="❓ F.A.Q.")],
        [KeyboardButton(text="🌐 Открыть приложение", web_app=WebAppInfo(url="https://sympto-med-app.vercel.app"))]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


# ============ РЕГИСТРАЦИЯ ============


def get_gender_keyboard(lang: str = "ru") -> ReplyKeyboardMarkup:
    """Клавиатура выбора пола (ОБЫЧНЫЕ КНОПКИ)"""
    options = {
        "ru": ("👨 Мужской", "👩 Женский"),
        "uz": ("👨 Erkak", "👩 Ayol"),
    }
    male_text, female_text = options.get(lang, options["ru"])

    keyboard = [
        [KeyboardButton(text=male_text), KeyboardButton(text=female_text)]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True, one_time_keyboard=True)


def get_step_keyboard_with_back(extra_buttons: list | None = None) -> ReplyKeyboardMarkup:
    """Клавиатура для шагов регистрации с кнопкой Назад."""
    keyboard = []
    if extra_buttons:
        keyboard.extend(extra_buttons)
    keyboard.append([KeyboardButton(text="◀️ Назад"), KeyboardButton(text="❌ Отмена")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_phone_keyboard_with_back() -> ReplyKeyboardMarkup:
    """Клавиатура для шага телефона с кнопкой Назад."""
    keyboard = [
        [KeyboardButton(text="📱 Поделиться номером", request_contact=True)],
        [KeyboardButton(text="◀️ Назад"), KeyboardButton(text="❌ Отмена")],
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура с кнопкой отмены"""
    keyboard = [[KeyboardButton(text="❌ Отменить")]]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


# ============ ПРОФИЛЬ ============

def get_profile_menu() -> ReplyKeyboardMarkup:
    """Меню профиля (ОБЫЧНЫЕ КНОПКИ)"""
    keyboard = [
        [KeyboardButton(text="✏️ Изменить данные профиля")],
        [KeyboardButton(text="📋 Обновить медицинскую историю")],
        [KeyboardButton(text="🔙 Главное меню")],
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_clinics_specialists_submenu() -> ReplyKeyboardMarkup:
    """Подменю клиник и специалистов"""
    keyboard = [
        [KeyboardButton(text="🏥 Найти клинику"), KeyboardButton(text="👨‍⚕️ Найти специалиста")],
        [KeyboardButton(text="🔙 Назад")],
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_edit_profile_menu() -> ReplyKeyboardMarkup:
    """Меню выбора поля для редактирования (ОБЫЧНЫЕ КНОПКИ)"""
    keyboard = [
        [KeyboardButton(text="👤 ФИО"), KeyboardButton(text="📱 Телефон")],
        [KeyboardButton(text="🎂 Дата рождения"), KeyboardButton(text="⚧️ Пол")],
        [KeyboardButton(text="📏 Рост"), KeyboardButton(text="⚖️ Вес")],
        [KeyboardButton(text="🔙 Назад к профилю")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


# ============ КОНСУЛЬТАЦИЯ ============


# ============ ПОИСК СПЕЦИАЛИСТОВ ============

def get_specialist_categories() -> ReplyKeyboardMarkup:
    """Категории специалистов (ОБЫЧНЫЕ КНОПКИ)"""
    keyboard = [
        [KeyboardButton(text="❤️ Сердце и сосуды")],
        [KeyboardButton(text="🧠 Нервная система")],
        [KeyboardButton(text="🍽 Пищеварение")],
        [KeyboardButton(text="💊 Гормоны и обмен веществ")],
        [KeyboardButton(text="🫁 Дыхательная система")],
        [KeyboardButton(text="🦴 Опорно-двигательный аппарат")],
        [KeyboardButton(text="👁 Зрение и слух")],
        [KeyboardButton(text="🧬 Кожа и аллергия")],
        [KeyboardButton(text="👶 Женское и мужское здоровье")],
        [KeyboardButton(text="🩺 Другие специалисты")],
        [KeyboardButton(text="🔙 В главное меню")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_specialists_in_category(specialists: list[str]) -> ReplyKeyboardMarkup:
    """
    Список специалистов в категории (ОБЫЧНЫЕ КНОПКИ)
    
    Args:
        specialists: Список специалистов
    """
    keyboard = [[KeyboardButton(text=f"🩺 {specialist}")] for specialist in specialists]
    keyboard.append([KeyboardButton(text="🔙 К категориям")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_specialist_actions() -> ReplyKeyboardMarkup:
    """Действия при просмотре специалиста (ОБЫЧНЫЕ КНОПКИ)"""
    keyboard = [
        [KeyboardButton(text="🩺 Начать консультацию")],
        [KeyboardButton(text="🔙 К списку специалистов")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
