from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder


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
    builder.button(text="⚧ Другой")
    builder.adjust(3)
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


def consultation_result_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура после результата консультации"""
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Новая консультация", callback_data="new_consultation")
    builder.button(text="📋 История", callback_data="view_history")
    builder.adjust(1)
    return builder.as_markup()
