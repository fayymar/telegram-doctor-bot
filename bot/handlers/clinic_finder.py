"""Обработчики для поиска ближайших клиник"""
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

from bot.keyboards import get_main_menu
from utils.logger import setup_logger

logger = setup_logger(__name__)
router = Router()

# Хранилище геолокаций пользователей (в памяти)
_user_locations: dict[int, tuple[float, float]] = {}

CLINIC_TYPES = [
    ("🏥 Больницы", "больница"),
    ("🏥 Поликлиники", "поликлиника"),
    ("💊 Аптеки", "аптека"),
    ("🚑 Скорая помощь", "скорая помощь"),
    ("👨‍⚕️ Частные клиники", "частная клиника"),
    ("🦷 Стоматологии", "стоматология"),
    ("🔙 Главное меню", None),
]


def get_location_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="📍 Поделиться местоположением", request_location=True)],
        [KeyboardButton(text="❌ Отменить")],
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_type_keyboard() -> ReplyKeyboardMarkup:
    """Не-инлайн клавиатура выбора типа учреждения"""
    rows = [[KeyboardButton(text=label)] for label, _ in CLINIC_TYPES]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def make_map_link(label: str, query: str, lat: float, lon: float) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text=f"🗺 Открыть карту — {label}",
            url=f"https://yandex.ru/maps/?text={query}&ll={lon},{lat}&z=14"
        )
    ]])


@router.message(F.text.in_({"🗺 Найти клиники", "🏥 Найти клинику"}))
async def request_location(message: Message):
    await message.answer(
        "🗺 *Поиск ближайших клиник*\n\n"
        "Поделитесь своим местоположением, чтобы найти медучреждения рядом.\n\n"
        "⚠️ Геолокация не сохраняется.",
        reply_markup=get_location_keyboard(),
        parse_mode="Markdown",
    )


@router.message(F.location)
async def process_location(message: Message):
    try:
        lat = message.location.latitude
        lon = message.location.longitude
        user_id = message.from_user.id
        _user_locations[user_id] = (lat, lon)

        logger.info(f"Location received from user {user_id}: {lat}, {lon}")

        await message.answer(
            "✅ *Местоположение получено!*\n\nВыберите тип учреждения:",
            reply_markup=get_type_keyboard(),
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"Error processing location: {e}", exc_info=True)
        await message.answer("❌ Ошибка при обработке геолокации. Попробуйте ещё раз.", reply_markup=get_main_menu())


# Обработчик кнопок типа учреждения
TYPE_LABELS = {label: query for label, query in CLINIC_TYPES if query is not None}

@router.message(F.text.in_(list(TYPE_LABELS.keys())))
async def handle_type_selection(message: Message):
    user_id = message.from_user.id
    loc = _user_locations.get(user_id)
    label = message.text

    if not loc:
        await message.answer("Сначала отправьте геолокацию.", reply_markup=get_main_menu())
        return

    lat, lon = loc
    query = TYPE_LABELS[label]

    await message.answer(
        f"Показываю *{label.split(' ', 1)[1]}* рядом с вами:",
        reply_markup=make_map_link(label.split(' ', 1)[1], query, lat, lon),
        parse_mode="Markdown",
    )


@router.message(F.text == "🔙 Главное меню")
async def back_to_menu(message: Message):
    await message.answer("Главное меню:", reply_markup=get_main_menu())
