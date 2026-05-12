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
    # Формируем URL для Яндекс.Карт с разными типами медучреждений
    # Формат: https://yandex.ru/maps/?text=поисковый_запрос&ll=долгота,широта&z=масштаб

    keyboard = [
        [InlineKeyboardButton(
            text="🏥 Больницы",
            url=f"https://yandex.ru/maps/?text=больница&ll={lon},{lat}&z=14"
        )],
        [InlineKeyboardButton(
            text="🏥 Поликлиники",
            url=f"https://yandex.ru/maps/?text=поликлиника&ll={lon},{lat}&z=14"
        )],
        [InlineKeyboardButton(
            text="💊 Аптеки",
            url=f"https://yandex.ru/maps/?text=аптека&ll={lon},{lat}&z=14"
        )],
        [InlineKeyboardButton(
            text="🚑 Скорая помощь",
            url=f"https://yandex.ru/maps/?text=скорая помощь&ll={lon},{lat}&z=14"
        )],
        [InlineKeyboardButton(
            text="👨‍⚕️ Частные клиники",
            url=f"https://yandex.ru/maps/?text=частная клиника&ll={lon},{lat}&z=14"
        )],
        [InlineKeyboardButton(
            text="🦷 Стоматологии",
            url=f"https://yandex.ru/maps/?text=стоматология&ll={lon},{lat}&z=14"
        )]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


@router.message(F.text.in_({"🗺 Найти клиники", "🏥 Найти клинику"}))
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
            "Откроется Яндекс.Карты с результатами поиска рядом с вами",
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
