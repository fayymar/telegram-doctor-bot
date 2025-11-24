"""Обработчики для дневника здоровья"""
from datetime import datetime, date
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from bot.states import HealthDiary
from bot.keyboards import get_main_menu, get_cancel_keyboard
from database.connection import supabase_client
from utils.logger import setup_logger
from utils.validators import sanitize_text

logger = setup_logger(__name__)
router = Router()


def get_diary_menu() -> ReplyKeyboardMarkup:
    """Меню дневника здоровья"""
    keyboard = [
        [KeyboardButton(text="➕ Новая запись")],
        [KeyboardButton(text="📖 Мои записи")],
        [KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="🔙 В главное меню")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_metrics_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора метрик"""
    keyboard = [
        [InlineKeyboardButton(text="🌡 Температура", callback_data="metric_temp")],
        [InlineKeyboardButton(text="💓 Давление", callback_data="metric_bp")],
        [InlineKeyboardButton(text="💗 Пульс", callback_data="metric_pulse")],
        [InlineKeyboardButton(text="⚖️ Вес", callback_data="metric_weight")],
        [InlineKeyboardButton(text="🤒 Симптомы", callback_data="metric_symptoms")],
        [InlineKeyboardButton(text="😊 Настроение", callback_data="metric_mood")],
        [InlineKeyboardButton(text="📝 Заметки", callback_data="metric_notes")],
        [InlineKeyboardButton(text="✅ Готово", callback_data="metrics_done")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_mood_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура выбора настроения"""
    keyboard = [
        [KeyboardButton(text="😊 Отлично"), KeyboardButton(text="🙂 Хорошо")],
        [KeyboardButton(text="😐 Нормально"), KeyboardButton(text="😔 Плохо")],
        [KeyboardButton(text="😣 Очень плохо")],
        [KeyboardButton(text="⏭ Пропустить"), KeyboardButton(text="❌ Отменить")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_skip_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура с кнопкой пропуска"""
    keyboard = [
        [KeyboardButton(text="⏭ Пропустить")],
        [KeyboardButton(text="❌ Отменить")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


@router.message(F.text == "📓 Дневник")
async def show_diary_menu(message: Message):
    """Показать меню дневника здоровья"""
    await message.answer(
        "📓 *Дневник здоровья*\n\n"
        "Отслеживайте свое самочувствие и показатели здоровья\n\n"
        "Выберите действие:",
        reply_markup=get_diary_menu(),
        parse_mode="Markdown"
    )


@router.message(F.text == "➕ Новая запись")
async def add_diary_entry(message: Message, state: FSMContext):
    """Начать добавление записи"""
    # Инициализируем пустую запись
    today = date.today()
    now = datetime.now()

    await state.update_data(
        entry_date=today.isoformat(),
        entry_time=now.strftime("%H:%M"),
        temperature=None,
        blood_pressure_sys=None,
        blood_pressure_dia=None,
        pulse=None,
        weight=None,
        symptoms=None,
        mood=None,
        notes=None
    )

    await message.answer(
        "➕ *Новая запись в дневник*\n\n"
        f"📅 Дата: {today.strftime('%d.%m.%Y')}\n"
        f"⏰ Время: {now.strftime('%H:%M')}\n\n"
        "Выберите, что хотите записать:",
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown"
    )

    await message.answer(
        "Выберите показатели:",
        reply_markup=get_metrics_keyboard()
    )

    await state.set_state(HealthDiary.choosing_metrics)


@router.callback_query(HealthDiary.choosing_metrics, F.data == "metric_temp")
async def ask_temperature(callback, state: FSMContext):
    """Запросить температуру"""
    await callback.message.answer(
        "🌡 *Температура тела*\n\n"
        "Введите температуру в °C\n"
        "Например: 36.6",
        reply_markup=get_skip_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(HealthDiary.waiting_for_temperature)
    await callback.answer()


@router.message(HealthDiary.waiting_for_temperature, F.text == "⏭ Пропустить")
async def skip_temperature(message: Message, state: FSMContext):
    """Пропустить температуру"""
    await return_to_metrics(message, state)


@router.message(HealthDiary.waiting_for_temperature, F.text)
async def process_temperature(message: Message, state: FSMContext):
    """Обработка температуры"""
    temp_str = sanitize_text(message.text).replace(",", ".")

    try:
        temperature = float(temp_str)

        if temperature < 32 or temperature > 45:
            await message.answer("❌ Температура должна быть в диапазоне 32-45°C")
            return

        await state.update_data(temperature=temperature)
        await message.answer(f"✅ Температура: {temperature}°C")
        await return_to_metrics(message, state)

    except ValueError:
        await message.answer("❌ Введите число, например: 36.6")


@router.callback_query(HealthDiary.choosing_metrics, F.data == "metric_bp")
async def ask_blood_pressure(callback, state: FSMContext):
    """Запросить давление"""
    await callback.message.answer(
        "💓 *Артериальное давление*\n\n"
        "Введите давление в формате: верхнее/нижнее\n"
        "Например: 120/80",
        reply_markup=get_skip_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(HealthDiary.waiting_for_blood_pressure)
    await callback.answer()


@router.message(HealthDiary.waiting_for_blood_pressure, F.text == "⏭ Пропустить")
async def skip_blood_pressure(message: Message, state: FSMContext):
    """Пропустить давление"""
    await return_to_metrics(message, state)


@router.message(HealthDiary.waiting_for_blood_pressure, F.text)
async def process_blood_pressure(message: Message, state: FSMContext):
    """Обработка давления"""
    bp_str = sanitize_text(message.text)

    try:
        parts = bp_str.replace(" ", "").split("/")
        if len(parts) != 2:
            raise ValueError()

        sys_bp = int(parts[0])
        dia_bp = int(parts[1])

        if sys_bp < 60 or sys_bp > 250:
            await message.answer("❌ Верхнее давление должно быть в диапазоне 60-250")
            return

        if dia_bp < 40 or dia_bp > 150:
            await message.answer("❌ Нижнее давление должно быть в диапазоне 40-150")
            return

        if dia_bp >= sys_bp:
            await message.answer("❌ Верхнее давление должно быть больше нижнего")
            return

        await state.update_data(blood_pressure_sys=sys_bp, blood_pressure_dia=dia_bp)
        await message.answer(f"✅ Давление: {sys_bp}/{dia_bp}")
        await return_to_metrics(message, state)

    except ValueError:
        await message.answer("❌ Введите давление в формате: 120/80")


@router.callback_query(HealthDiary.choosing_metrics, F.data == "metric_pulse")
async def ask_pulse(callback, state: FSMContext):
    """Запросить пульс"""
    await callback.message.answer(
        "💗 *Пульс*\n\n"
        "Введите пульс в ударах в минуту\n"
        "Например: 70",
        reply_markup=get_skip_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(HealthDiary.waiting_for_pulse)
    await callback.answer()


@router.message(HealthDiary.waiting_for_pulse, F.text == "⏭ Пропустить")
async def skip_pulse(message: Message, state: FSMContext):
    """Пропустить пульс"""
    await return_to_metrics(message, state)


@router.message(HealthDiary.waiting_for_pulse, F.text)
async def process_pulse(message: Message, state: FSMContext):
    """Обработка пульса"""
    pulse_str = sanitize_text(message.text)

    try:
        pulse = int(pulse_str)

        if pulse < 30 or pulse > 220:
            await message.answer("❌ Пульс должен быть в диапазоне 30-220 уд/мин")
            return

        await state.update_data(pulse=pulse)
        await message.answer(f"✅ Пульс: {pulse} уд/мин")
        await return_to_metrics(message, state)

    except ValueError:
        await message.answer("❌ Введите число, например: 70")


@router.callback_query(HealthDiary.choosing_metrics, F.data == "metric_weight")
async def ask_weight(callback, state: FSMContext):
    """Запросить вес"""
    await callback.message.answer(
        "⚖️ *Вес*\n\n"
        "Введите вес в килограммах\n"
        "Например: 70 или 70.5",
        reply_markup=get_skip_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(HealthDiary.waiting_for_weight)
    await callback.answer()


@router.message(HealthDiary.waiting_for_weight, F.text == "⏭ Пропустить")
async def skip_weight(message: Message, state: FSMContext):
    """Пропустить вес"""
    await return_to_metrics(message, state)


@router.message(HealthDiary.waiting_for_weight, F.text)
async def process_weight(message: Message, state: FSMContext):
    """Обработка веса"""
    weight_str = sanitize_text(message.text).replace(",", ".")

    try:
        weight = float(weight_str)

        if weight < 20 or weight > 300:
            await message.answer("❌ Вес должен быть в диапазоне 20-300 кг")
            return

        await state.update_data(weight=weight)
        await message.answer(f"✅ Вес: {weight} кг")
        await return_to_metrics(message, state)

    except ValueError:
        await message.answer("❌ Введите число, например: 70 или 70.5")


@router.callback_query(HealthDiary.choosing_metrics, F.data == "metric_symptoms")
async def ask_symptoms(callback, state: FSMContext):
    """Запросить симптомы"""
    await callback.message.answer(
        "🤒 *Симптомы*\n\n"
        "Опишите ваши симптомы или состояние",
        reply_markup=get_skip_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(HealthDiary.waiting_for_symptoms)
    await callback.answer()


@router.message(HealthDiary.waiting_for_symptoms, F.text == "⏭ Пропустить")
async def skip_symptoms(message: Message, state: FSMContext):
    """Пропустить симптомы"""
    await return_to_metrics(message, state)


@router.message(HealthDiary.waiting_for_symptoms, F.text)
async def process_symptoms(message: Message, state: FSMContext):
    """Обработка симптомов"""
    symptoms = sanitize_text(message.text)

    if len(symptoms) > 500:
        await message.answer("❌ Описание слишком длинное (максимум 500 символов)")
        return

    await state.update_data(symptoms=symptoms)
    await message.answer("✅ Симптомы записаны")
    await return_to_metrics(message, state)


@router.callback_query(HealthDiary.choosing_metrics, F.data == "metric_mood")
async def ask_mood(callback, state: FSMContext):
    """Запросить настроение"""
    await callback.message.answer(
        "😊 *Настроение*\n\n"
        "Как вы себя чувствуете?",
        reply_markup=get_mood_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(HealthDiary.waiting_for_mood)
    await callback.answer()


@router.message(HealthDiary.waiting_for_mood, F.text == "⏭ Пропустить")
async def skip_mood(message: Message, state: FSMContext):
    """Пропустить настроение"""
    await return_to_metrics(message, state)


@router.message(HealthDiary.waiting_for_mood, F.text.in_(["😊 Отлично", "🙂 Хорошо", "😐 Нормально", "😔 Плохо", "😣 Очень плохо"]))
async def process_mood(message: Message, state: FSMContext):
    """Обработка настроения"""
    mood = message.text
    await state.update_data(mood=mood)
    await message.answer(f"✅ Настроение: {mood}")
    await return_to_metrics(message, state)


@router.callback_query(HealthDiary.choosing_metrics, F.data == "metric_notes")
async def ask_notes(callback, state: FSMContext):
    """Запросить заметки"""
    await callback.message.answer(
        "📝 *Заметки*\n\n"
        "Добавьте дополнительные заметки",
        reply_markup=get_skip_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(HealthDiary.waiting_for_notes)
    await callback.answer()


@router.message(HealthDiary.waiting_for_notes, F.text == "⏭ Пропустить")
async def skip_notes(message: Message, state: FSMContext):
    """Пропустить заметки"""
    await return_to_metrics(message, state)


@router.message(HealthDiary.waiting_for_notes, F.text)
async def process_notes(message: Message, state: FSMContext):
    """Обработка заметок"""
    notes = sanitize_text(message.text)

    if len(notes) > 1000:
        await message.answer("❌ Заметки слишком длинные (максимум 1000 символов)")
        return

    await state.update_data(notes=notes)
    await message.answer("✅ Заметки записаны")
    await return_to_metrics(message, state)


async def return_to_metrics(message: Message, state: FSMContext):
    """Вернуться к выбору метрик"""
    await message.answer(
        "Что еще добавить?",
        reply_markup=get_metrics_keyboard()
    )
    await state.set_state(HealthDiary.choosing_metrics)


@router.callback_query(HealthDiary.choosing_metrics, F.data == "metrics_done")
async def show_diary_confirmation(callback, state: FSMContext):
    """Показать подтверждение перед сохранением"""
    data = await state.get_data()

    # Проверка что хоть что-то заполнено
    has_data = any([
        data.get('temperature'),
        data.get('blood_pressure_sys'),
        data.get('pulse'),
        data.get('weight'),
        data.get('symptoms'),
        data.get('mood'),
        data.get('notes')
    ])

    if not has_data:
        await callback.answer("❌ Заполните хотя бы один показатель", show_alert=True)
        return

    # Формируем сводку
    entry_date = datetime.fromisoformat(data['entry_date'])
    summary = f"📓 *Запись в дневник*\n\n"
    summary += f"📅 {entry_date.strftime('%d.%m.%Y')} в {data['entry_time']}\n\n"

    if data.get('temperature'):
        summary += f"🌡 Температура: {data['temperature']}°C\n"

    if data.get('blood_pressure_sys'):
        summary += f"💓 Давление: {data['blood_pressure_sys']}/{data['blood_pressure_dia']}\n"

    if data.get('pulse'):
        summary += f"💗 Пульс: {data['pulse']} уд/мин\n"

    if data.get('weight'):
        summary += f"⚖️ Вес: {data['weight']} кг\n"

    if data.get('mood'):
        summary += f"😊 Настроение: {data['mood']}\n"

    if data.get('symptoms'):
        summary += f"\n🤒 *Симптомы:*\n{data['symptoms']}\n"

    if data.get('notes'):
        summary += f"\n📝 *Заметки:*\n{data['notes']}\n"

    summary += "\n✅ Сохранить запись?"

    # Создаем клавиатуру подтверждения
    confirm_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ Сохранить")],
            [KeyboardButton(text="❌ Отменить")]
        ],
        resize_keyboard=True
    )

    await callback.message.answer(
        summary,
        reply_markup=confirm_keyboard,
        parse_mode="Markdown"
    )
    await state.set_state(HealthDiary.confirming)
    await callback.answer()


@router.message(HealthDiary.confirming, F.text == "✅ Сохранить")
async def save_diary_entry(message: Message, state: FSMContext):
    """Сохранить запись в БД"""
    try:
        data = await state.get_data()
        user_id = message.from_user.id

        entry_data = {
            'user_id': user_id,
            'entry_date': data['entry_date'],
            'entry_time': data['entry_time'],
            'temperature': data.get('temperature'),
            'blood_pressure_sys': data.get('blood_pressure_sys'),
            'blood_pressure_dia': data.get('blood_pressure_dia'),
            'pulse': data.get('pulse'),
            'weight': data.get('weight'),
            'symptoms': data.get('symptoms'),
            'mood': data.get('mood'),
            'notes': data.get('notes'),
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }

        supabase_client.table('health_diary').insert(entry_data).execute()

        await message.answer(
            "✅ *Запись сохранена!*\n\n"
            "Отслеживайте свое здоровье регулярно для лучших результатов",
            reply_markup=get_diary_menu(),
            parse_mode="Markdown"
        )

        await state.clear()
        logger.info(f"Health diary entry saved for user {user_id}")

    except Exception as e:
        logger.error(f"Error saving diary entry: {e}", exc_info=True)
        await message.answer(
            "❌ Ошибка при сохранении записи\n"
            "Попробуйте позже",
            reply_markup=get_diary_menu()
        )
        await state.clear()


@router.message(F.text == "📖 Мои записи")
async def show_diary_entries(message: Message):
    """Показать записи дневника"""
    try:
        user_id = message.from_user.id

        response = supabase_client.table('health_diary') \
            .select('*') \
            .eq('user_id', user_id) \
            .order('entry_date', desc=True) \
            .order('entry_time', desc=True) \
            .limit(10) \
            .execute()

        if not response.data or len(response.data) == 0:
            await message.answer(
                "📖 *Мои записи*\n\n"
                "У вас пока нет записей в дневнике\n\n"
                "Нажмите ➕ *Новая запись*",
                reply_markup=get_diary_menu(),
                parse_mode="Markdown"
            )
            return

        entries_text = "📖 *Последние записи*\n\n"

        for entry in response.data[:10]:
            entry_date = datetime.fromisoformat(entry['entry_date'])
            entries_text += f"📅 {entry_date.strftime('%d.%m.%Y')}"

            if entry.get('entry_time'):
                entries_text += f" в {entry['entry_time']}"

            entries_text += "\n"

            if entry.get('temperature'):
                entries_text += f"🌡 {entry['temperature']}°C  "

            if entry.get('blood_pressure_sys'):
                entries_text += f"💓 {entry['blood_pressure_sys']}/{entry['blood_pressure_dia']}  "

            if entry.get('pulse'):
                entries_text += f"💗 {entry['pulse']}  "

            if entry.get('mood'):
                entries_text += f"{entry['mood']}"

            entries_text += "\n\n"

        await message.answer(
            entries_text,
            reply_markup=get_diary_menu(),
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.error(f"Error loading diary entries: {e}", exc_info=True)
        await message.answer(
            "❌ Ошибка при загрузке записей",
            reply_markup=get_diary_menu()
        )


@router.message(F.text == "📊 Статистика")
async def show_statistics(message: Message):
    """Показать статистику (заглушка)"""
    await message.answer(
        "📊 *Статистика*\n\n"
        "Функция в разработке\n\n"
        "Скоро здесь будут графики и анализ ваших показателей",
        reply_markup=get_diary_menu(),
        parse_mode="Markdown"
    )
