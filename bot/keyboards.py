from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from typing import List


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Главное меню"""
    builder = ReplyKeyboardBuilder()
    builder.button(text="🩺 Новая консультация")
    builder.button(text="📋 Мои консультации")
    builder.button(text="👤 Мой профиль")
    builder.button(text="ℹ️ Помощь")
    builder.adjust(2, 2)
    return builder.as_markup(resize_keyboard=True)


def gender_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура выбора пола"""
    builder = ReplyKeyboardBuilder()
    builder.button(text="👨 Мужской")
    builder.button(text="👩 Женский")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)


def cancel_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура с кнопкой отмены"""
    builder = ReplyKeyboardBuilder()
    builder.button(text="❌ Отменить")
    return builder.as_markup(resize_keyboard=True)


def skip_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура с кнопкой пропуска"""
    builder = ReplyKeyboardBuilder()
    builder.button(text="⏭️ Пропустить")
    builder.button(text="❌ Отменить")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)


# === НОВЫЕ КЛАВИАТУРЫ ДЛЯ КОНСУЛЬТАЦИИ ===

def confirm_symptoms_keyboard() -> ReplyKeyboardMarkup:
    """Подтверждение симптомов (Этап 1)"""
    builder = ReplyKeyboardBuilder()
    builder.button(text="✅ Подтвердить")
    builder.button(text="✏️ Добавить")
    builder.button(text="🔄 Начать заново")
    builder.button(text="❌ Отменить")
    builder.adjust(2, 2)
    return builder.as_markup(resize_keyboard=True)


def duration_keyboard() -> ReplyKeyboardMarkup:
    """Выбор давности симптомов (Этап 2)"""
    builder = ReplyKeyboardBuilder()
    builder.button(text="⏱️ Меньше 24 часов")
    builder.button(text="📅 1-3 дня")
    builder.button(text="📅 3-6 дней")
    builder.button(text="📅 Больше недели")
    builder.button(text="⬅️ Назад")
    builder.button(text="❌ Отменить")
    builder.adjust(2, 2, 2)
    return builder.as_markup(resize_keyboard=True)


def additional_symptoms_keyboard(symptoms: List[str], selected: List[str] = None) -> InlineKeyboardMarkup:
    """Inline клавиатура для выбора дополнительных симптомов (Этап 3)
    
    Args:
        symptoms: список симптомов для выбора
        selected: список уже выбранных симптомов
    """
    if selected is None:
        selected = []
    
    builder = InlineKeyboardBuilder()
    
    # Кнопки с симптомами (с галочкой если выбран)
    for symptom in symptoms:
        is_selected = symptom in selected
        text = f"✓ {symptom}" if is_selected else symptom
        builder.button(
            text=text,
            callback_data=f"toggle_symptom:{symptom}"
        )
    
    # Размещаем по 2 кнопки в ряд
    builder.adjust(2)
    
    # Специальные кнопки
    builder.row(
        InlineKeyboardButton(text="❌ Ничего из этого", callback_data="no_additional_symptoms"),
        InlineKeyboardButton(text="➕ Другое", callback_data="custom_symptoms")
    )
    
    # Навигация
    builder.row(
        InlineKeyboardButton(text="✅ Готово", callback_data="additional_symptoms_done"),
        InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_duration"),
        InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_consultation")
    )
    
    return builder.as_markup()


def final_confirmation_keyboard() -> ReplyKeyboardMarkup:
    """Финальное подтверждение (Этап 4)"""
    builder = ReplyKeyboardBuilder()
    builder.button(text="✅ Подтвердить")
    builder.button(text="✏️ Добавить симптомы")
    builder.button(text="🔄 Начать заново")
    builder.button(text="❌ Отменить")
    builder.adjust(2, 2)
    return builder.as_markup(resize_keyboard=True)


def consultation_result_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура после результата консультации"""
    builder = InlineKeyboardBuilder()
    builder.button(text="📅 Записаться на консультацию", callback_data="book_appointment")
    builder.button(text="🔄 Новая консультация", callback_data="new_consultation")
    builder.button(text="📋 История", callback_data="view_history")
    builder.adjust(1, 2)
    return builder.as_markup()
