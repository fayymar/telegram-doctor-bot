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
    """Клавиатура для запроса телефона"""
    keyboard = [
        [KeyboardButton(text="📱 Поделиться номером", request_contact=True)],
        [KeyboardButton(text="⏭ Пропустить")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_gender_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора пола"""
    keyboard = [
        [InlineKeyboardButton(text="👨 Мужской", callback_data="gender_male")],
        [InlineKeyboardButton(text="👩 Женский", callback_data="gender_female")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_skip_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура с кнопкой 'Пропустить'"""
    keyboard = [[KeyboardButton(text="⏭ Пропустить")]]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


# ============ ПРОФИЛЬ ============

def get_profile_menu() -> InlineKeyboardMarkup:
    """Меню профиля"""
    keyboard = [
        [InlineKeyboardButton(text="✏️ Изменить данные", callback_data="edit_profile")],
        [InlineKeyboardButton(text="🔙 В главное меню", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_edit_profile_menu() -> InlineKeyboardMarkup:
    """Меню выбора поля для редактирования"""
    keyboard = [
        [InlineKeyboardButton(text="👤 ФИО", callback_data="edit_full_name")],
        [InlineKeyboardButton(text="📱 Телефон", callback_data="edit_phone")],
        [InlineKeyboardButton(text="🎂 Дата рождения", callback_data="edit_birthdate")],
        [InlineKeyboardButton(text="⚧️ Пол", callback_data="edit_gender")],
        [InlineKeyboardButton(text="📏 Рост", callback_data="edit_height")],
        [InlineKeyboardButton(text="⚖️ Вес", callback_data="edit_weight")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_profile")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


# ============ КОНСУЛЬТАЦИЯ ============

def get_symptoms_confirmation() -> InlineKeyboardMarkup:
    """Подтверждение симптомов (Этап 1)"""
    keyboard = [
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_symptoms")],
        [InlineKeyboardButton(text="➕ Добавить", callback_data="add_symptoms")],
        [InlineKeyboardButton(text="🔄 Начать заново", callback_data="restart_symptoms")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_consultation")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_duration_keyboard() -> InlineKeyboardMarkup:
    """Выбор давности симптомов (Этап 2)"""
    keyboard = [
        [InlineKeyboardButton(text="⏱ Меньше 24 часов", callback_data="duration_24h")],
        [InlineKeyboardButton(text="📅 1-3 дня", callback_data="duration_1-3d")],
        [InlineKeyboardButton(text="📅 3-7 дней", callback_data="duration_3-7d")],
        [InlineKeyboardButton(text="📆 Больше недели", callback_data="duration_week+")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_additional_symptoms_keyboard(symptoms: list[str]) -> InlineKeyboardMarkup:
    """
    Клавиатура с дополнительными симптомами (Этап 3)
    
    Args:
        symptoms: Список симптомов от AI
    """
    keyboard = []
    
    # Добавляем симптомы (максимум 10)
    for symptom in symptoms[:10]:
        keyboard.append([InlineKeyboardButton(
            text=f"◻️ {symptom}", 
            callback_data=f"symptom_{symptom[:50]}"  # Ограничение длины callback
        )])
    
    # Служебные кнопки
    keyboard.append([InlineKeyboardButton(text="🚫 Ничего из этого", callback_data="no_additional")])
    keyboard.append([InlineKeyboardButton(text="✏️ Другое (описать)", callback_data="other_symptom")])
    keyboard.append([InlineKeyboardButton(text="✅ Готово", callback_data="done_additional")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


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


def get_final_confirmation() -> InlineKeyboardMarkup:
    """Финальное подтверждение (Этап 4)"""
    keyboard = [
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data="final_confirm")],
        [InlineKeyboardButton(text="➕ Добавить симптомы", callback_data="add_more_symptoms")],
        [InlineKeyboardButton(text="🔄 Начать заново", callback_data="restart_consultation")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_consultation")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_result_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура после получения рекомендации"""
    keyboard = [
        [InlineKeyboardButton(text="📝 Записаться (в разработке)", callback_data="book_appointment")],
        [InlineKeyboardButton(text="🩺 Новая консультация", callback_data="new_consultation")],
        [InlineKeyboardButton(text="📋 История", callback_data="view_history")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


# ============ ПОИСК СПЕЦИАЛИСТОВ ============

def get_specialist_categories() -> InlineKeyboardMarkup:
    """Категории специалистов"""
    keyboard = [
        [InlineKeyboardButton(text="❤️ Сердце и сосуды", callback_data="cat_cardio")],
        [InlineKeyboardButton(text="🧠 Нервная система", callback_data="cat_neuro")],
        [InlineKeyboardButton(text="🍽 Пищеварение", callback_data="cat_gastro")],
        [InlineKeyboardButton(text="💊 Гормоны и обмен веществ", callback_data="cat_endo")],
        [InlineKeyboardButton(text="🫁 Дыхательная система", callback_data="cat_pulmo")],
        [InlineKeyboardButton(text="🦴 Опорно-двигательный аппарат", callback_data="cat_ortho")],
        [InlineKeyboardButton(text="👁 Зрение и слух", callback_data="cat_sense")],
        [InlineKeyboardButton(text="🧬 Кожа и аллергия", callback_data="cat_derm")],
        [InlineKeyboardButton(text="👶 Женское и мужское здоровье", callback_data="cat_repro")],
        [InlineKeyboardButton(text="🩺 Другие специалисты", callback_data="cat_other")],
        [InlineKeyboardButton(text="🔙 В главное меню", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_specialists_in_category(category: str) -> InlineKeyboardMarkup:
    """
    Список специалистов в категории
    
    Args:
        category: Код категории (например, 'cardio')
    """
    specialists_map = {
        "cardio": ["Кардиолог", "Флеболог", "Сосудистый хирург"],
        "neuro": ["Невролог", "Нейрохирург", "Психиатр"],
        "gastro": ["Гастроэнтеролог", "Проктолог", "Гепатолог"],
        "endo": ["Эндокринолог", "Диабетолог"],
        "pulmo": ["Пульмонолог", "Фтизиатр"],
        "ortho": ["Ортопед-травматолог", "Ревматолог", "Мануальный терапевт"],
        "sense": ["Офтальмолог", "Отоларинголог (ЛОР)", "Сурдолог"],
        "derm": ["Дерматолог", "Аллерголог-иммунолог", "Трихолог"],
        "repro": ["Гинеколог", "Уролог", "Маммолог", "Андролог"],
        "other": ["Хирург", "Онколог", "Нефролог", "Инфекционист"]
    }
    
    specialists = specialists_map.get(category, [])
    keyboard = []
    
    for specialist in specialists:
        keyboard.append([InlineKeyboardButton(
            text=f"🩺 {specialist}", 
            callback_data=f"spec_{specialist}"
        )])
    
    keyboard.append([InlineKeyboardButton(text="🔙 К категориям", callback_data="back_to_categories")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


# ============ ОТМЕНА ============

def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура с кнопкой отмены"""
    keyboard = [[KeyboardButton(text="❌ Отменить")]]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
