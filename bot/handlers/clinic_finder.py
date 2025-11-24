"""Обработчики для поиска ближайших клиник"""
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

from bot.keyboards import get_main_menu
from utils.logger import setup_logger

logger = setup_logger(__name__)
router = Router()


def get_location_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура для запроса геолокации"""
    keyboard = [
        [KeyboardButton(text="📍 Поделиться местоположением", request_location=True)],
        [KeyboardButton(text="❌ Отменить")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_clinic_search_options(lat: float, lon: float) -> InlineKeyboardMarkup:
    """Создает кнопки с вариантами поиска клиник"""
    # Формируем URL для Google Maps с разными типами медучреждений
    base_maps_url = f"https://www.google.com/maps/search/"

    keyboard = [
        [InlineKeyboardButton(
            text="🏥 Больницы",
            url=f"{base_maps_url}больница/@{lat},{lon},15z"
        )],
        [InlineKeyboardButton(
            text="🏥 Поликлиники",
            url=f"{base_maps_url}поликлиника/@{lat},{lon},15z"
        )],
        [InlineKeyboardButton(
            text="💊 Аптеки",
            url=f"{base_maps_url}аптека/@{lat},{lon},15z"
        )],
        [InlineKeyboardButton(
            text="🚑 Скорая помощь",
            url=f"{base_maps_url}скорая+помощь/@{lat},{lon},15z"
        )],
        [InlineKeyboardButton(
            text="👨‍⚕️ Частные клиники",
            url=f"{base_maps_url}частная+клиника/@{lat},{lon},15z"
        )],
        [InlineKeyboardButton(
            text="🦷 Стоматологии",
            url=f"{base_maps_url}стоматология/@{lat},{lon},15z"
        )]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


@router.message(F.text == "🗺 Найти клиники")
async def request_location(message: Message):
    """Запросить геолокацию для поиска клиник"""
    await message.answer(
        "🗺 *Поиск ближайших клиник*\n\n"
        "Для поиска медицинских учреждений рядом с вами, "
        "поделитесь своим местоположением\n\n"
        "Нажмите кнопку ниже или отправьте геолокацию вручную\n\n"
        "⚠️ *Важно:* Ваша геолокация не сохраняется и используется "
        "только для поиска",
        reply_markup=get_location_keyboard(),
        parse_mode="Markdown"
    )


@router.message(F.location)
async def process_location(message: Message):
    """Обработка полученной геолокации"""
    try:
        lat = message.location.latitude
        lon = message.location.longitude

        logger.info(f"Location received from user {message.from_user.id}: {lat}, {lon}")

        await message.answer(
            "✅ *Местоположение получено*\n\n"
            "📍 Выберите тип медицинского учреждения:\n\n"
            "Откроется Google Maps с результатами поиска рядом с вами",
            reply_markup=get_clinic_search_options(lat, lon),
            parse_mode="Markdown"
        )

        await message.answer(
            "💡 *Полезная информация:*\n\n"
            "• Звоните заранее, чтобы уточнить часы работы\n"
            "• При экстренной ситуации звоните 103 (скорая)\n"
            "• Возьмите с собой документы и полис ОМС\n\n"
            "🔙 Вернуться в главное меню",
            reply_markup=get_main_menu(),
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.error(f"Error processing location: {e}", exc_info=True)
        await message.answer(
            "❌ Ошибка при обработке геолокации\n"
            "Попробуйте еще раз",
            reply_markup=get_main_menu()
        )
