from aiogram.types import (
    ReplyKeyboardMarkup, 
    KeyboardButton, 
    InlineKeyboardMarkup, 
    InlineKeyboardButton
)


# ============ ГЛАВНОЕ МЕНЮ ============

def get_main_menu() -> ReplyKeyboardMarkup:
    """Главное меню бота"""
    keyboard = [
        [KeyboardButton(text="🩺 Новая консультация")],
        [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="📋 История")],
        [KeyboardButton(text="🔍 Найти специалиста")],
        [KeyboardButton(text="ℹ️ Помощь")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


# ============ РЕГИСТРАЦИЯ ============

def get_phone_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура для запроса телефона (ОБЯЗАТЕЛЬНО)"""
    keyboard = [
        [KeyboardButton(text="📱 Поделиться номером", request_contact=True)]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_gender_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура выбора пола (ОБЫЧНЫЕ КНОПКИ)"""
    keyboard = [
        [KeyboardButton(text="👨 Мужской"), KeyboardButton(text="👩 Женский")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True, one_time_keyboard=True)


def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура с кнопкой отмены"""
    keyboard = [[KeyboardButton(text="❌ Отменить")]]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


# ============ ПРОФИЛЬ ============

def get_profile_menu() -> ReplyKeyboardMarkup:
    """Меню профиля (ОБЫЧНЫЕ КНОПКИ)"""
    keyboard = [
        [KeyboardButton(text="✏️ Изменить данные")],
        [KeyboardButton(text="🔙 В главное меню")]
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

def get_symptoms_confirmation() -> ReplyKeyboardMarkup:
    """Подтверждение симптомов - ТОЛЬКО ОТМЕНИТЬ"""
    keyboard = [
        [KeyboardButton(text="✅ Подтвердить")],
        [KeyboardButton(text="➕ Добавить детали")],
        [KeyboardButton(text="🔄 Начать заново")],
        [KeyboardButton(text="❌ Отменить")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_duration_keyboard() -> ReplyKeyboardMarkup:
    """Выбор давности симптомов (ОБЫЧНЫЕ КНОПКИ)"""
    keyboard = [
        [KeyboardButton(text="⏱ Меньше 24 часов")],
        [KeyboardButton(text="📅 1-3 дня")],
        [KeyboardButton(text="📅 3-7 дней")],
        [KeyboardButton(text="📆 Больше недели")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True, one_time_keyboard=True)


def get_additional_symptoms_keyboard(symptoms: list[str]) -> InlineKeyboardMarkup:
    """
    Клавиатура с дополнительными симптомами (ИНЛАЙН)
    
    Args:
        symptoms: Список симптомов от AI
    """
    keyboard = []
    
    # Добавляем симптомы (максимум 10)
    for symptom in symptoms[:10]:
        keyboard.append([InlineKeyboardButton(
            text=f"◻️ {symptom}", 
            callback_data=f"symptom_{symptom[:50]}"
        )])
    
    # Служебные кнопки
    keyboard.append([InlineKeyboardButton(text="🚫 Ничего из этого", callback_data="no_additional")])
    keyboard.append([InlineKeyboardButton(text="✏️ Другое (описать)", callback_data="other_symptom")])
    keyboard.append([InlineKeyboardButton(text="✅ Готово", callback_data="done_additional")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_additional_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура для третьего этапа - только отменить"""
    keyboard = [[KeyboardButton(text="❌ Отменить")]]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def update_symptom_selection(keyboard: InlineKeyboardMarkup, selected: set) -> InlineKeyboardMarkup:
    """
    Обновляет состояние кнопок (отмечает выбранные)
    
    Args:
        keyboard: Текущая клавиатура
        selected: Множество выбранных симптомов
    """
    new_keyboard = []
    
    for row in keyboard.inline_keyboard:
        new_row = []
        for button in row:
            # Проверяем, выбран ли симптом
            if button.callback_data.startswith("symptom_"):
                symptom = button.text.replace("◻️ ", "").replace("✅ ", "")
                if symptom in selected:
                    new_button = InlineKeyboardButton(
                        text=f"✅ {symptom}",
                        callback_data=button.callback_data
                    )
                else:
                    new_button = InlineKeyboardButton(
                        text=f"◻️ {symptom}",
                        callback_data=button.callback_data
                    )
                new_row.append(new_button)
            else:
                new_row.append(button)
        new_keyboard.append(new_row)
    
    return InlineKeyboardMarkup(inline_keyboard=new_keyboard)


def get_final_confirmation() -> ReplyKeyboardMarkup:
    """Финальное подтверждение (ОБЫЧНЫЕ КНОПКИ)"""
    keyboard = [
        [KeyboardButton(text="✅ Подтвердить")],
        [KeyboardButton(text="➕ Добавить симптомы")],
        [KeyboardButton(text="🔄 Начать заново")],
        [KeyboardButton(text="❌ Отменить")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_result_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура после получения рекомендации (ОБЫЧНЫЕ КНОПКИ)"""
    keyboard = [
        [KeyboardButton(text="📝 Записаться (в разработке)")],
        [KeyboardButton(text="🏠 В главное меню")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


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
    keyboard = []
    
    for specialist in specialists:
        keyboard.append([KeyboardButton(text=f"🩺 {specialist}")])
    
    keyboard.append([KeyboardButton(text="🔙 К категориям")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_specialist_actions() -> ReplyKeyboardMarkup:
    """Действия при просмотре специалиста (ОБЫЧНЫЕ КНОПКИ)"""
    keyboard = [
        [KeyboardButton(text="🩺 Начать консультацию")],
        [KeyboardButton(text="🔙 К списку специалистов")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
