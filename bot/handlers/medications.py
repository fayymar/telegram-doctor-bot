"""Обработчики для напоминаний о лекарствах"""
from datetime import datetime, time
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext

from bot.states import MedicationReminder
from bot.keyboards import get_main_menu, get_cancel_keyboard
from database.connection import supabase_client
from utils.logger import setup_logger
from utils.validators import sanitize_text

logger = setup_logger(__name__)
router = Router()


def get_medications_menu() -> ReplyKeyboardMarkup:
    """Меню напоминаний о лекарствах"""
    keyboard = [
        [KeyboardButton(text="➕ Добавить лекарство")],
        [KeyboardButton(text="📋 Мои лекарства")],
        [KeyboardButton(text="🔙 В главное меню")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_frequency_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура выбора частоты приема"""
    keyboard = [
        [KeyboardButton(text="1 раз в день")],
        [KeyboardButton(text="2 раза в день")],
        [KeyboardButton(text="3 раза в день")],
        [KeyboardButton(text="Свой вариант")],
        [KeyboardButton(text="❌ Отменить")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_skip_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура с кнопкой пропуска"""
    keyboard = [
        [KeyboardButton(text="⏭ Пропустить")],
        [KeyboardButton(text="❌ Отменить")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_confirmation_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура подтверждения"""
    keyboard = [
        [KeyboardButton(text="✅ Сохранить")],
        [KeyboardButton(text="❌ Отменить")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


@router.message(F.text == "💊 Лекарства")
async def show_medications_menu(message: Message):
    """Показать меню напоминаний"""
    await message.answer(
        "💊 *Напоминания о лекарствах*\n\n"
        "Здесь вы можете настроить напоминания о приеме лекарств\n\n"
        "Выберите действие:",
        reply_markup=get_medications_menu(),
        parse_mode="Markdown"
    )


@router.message(F.text == "➕ Добавить лекарство")
async def add_medication_start(message: Message, state: FSMContext):
    """Начать добавление лекарства"""
    await message.answer(
        "💊 *Добавление лекарства*\n\n"
        "📝 Шаг 1 из 6\n\n"
        "Введите название лекарства:",
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(MedicationReminder.waiting_for_medication_name)


@router.message(MedicationReminder.waiting_for_medication_name, F.text)
async def process_medication_name(message: Message, state: FSMContext):
    """Обработка названия лекарства"""
    medication_name = sanitize_text(message.text)

    if len(medication_name) < 2:
        await message.answer("❌ Название слишком короткое. Попробуйте еще раз:")
        return

    if len(medication_name) > 100:
        await message.answer("❌ Название слишком длинное (максимум 100 символов)")
        return

    await state.update_data(medication_name=medication_name)

    await message.answer(
        f"✅ Лекарство: {medication_name}\n\n"
        f"📝 Шаг 2 из 6\n\n"
        f"Введите дозировку (например: '1 таблетка', '5 мл', '2 капсулы'):",
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(MedicationReminder.waiting_for_dosage)


@router.message(MedicationReminder.waiting_for_dosage, F.text)
async def process_dosage(message: Message, state: FSMContext):
    """Обработка дозировки"""
    dosage = sanitize_text(message.text)

    if len(dosage) < 1:
        await message.answer("❌ Дозировка не может быть пустой")
        return

    if len(dosage) > 50:
        await message.answer("❌ Дозировка слишком длинная (максимум 50 символов)")
        return

    await state.update_data(dosage=dosage)

    await message.answer(
        f"✅ Дозировка: {dosage}\n\n"
        f"📝 Шаг 3 из 6\n\n"
        f"Как часто нужно принимать?",
        reply_markup=get_frequency_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(MedicationReminder.waiting_for_frequency)


@router.message(MedicationReminder.waiting_for_frequency, F.text)
async def process_frequency(message: Message, state: FSMContext):
    """Обработка частоты приема"""
    frequency_map = {
        "1 раз в день": ("once", "09:00"),
        "2 раза в день": ("twice", "09:00,21:00"),
        "3 раза в день": ("thrice", "09:00,14:00,21:00")
    }

    if message.text in frequency_map:
        frequency, default_times = frequency_map[message.text]
        await state.update_data(frequency=frequency, times=default_times.split(","))

        await message.answer(
            f"✅ Частота: {message.text}\n"
            f"⏰ Время приема по умолчанию: {default_times.replace(',', ', ')}\n\n"
            f"📝 Шаг 4 из 6\n\n"
            f"Введите время приема в формате ЧЧ:ММ\n"
            f"Если несколько раз, укажите через запятую\n"
            f"Например: 09:00, 21:00\n\n"
            f"Или нажмите ⏭ Пропустить для времени по умолчанию",
            reply_markup=get_skip_keyboard(),
            parse_mode="Markdown"
        )
        await state.set_state(MedicationReminder.waiting_for_times)

    elif message.text == "Свой вариант":
        await message.answer(
            "⏰ Введите время приема в формате ЧЧ:ММ\n"
            "Если несколько раз, укажите через запятую\n"
            "Например: 08:00, 14:00, 20:00",
            reply_markup=get_cancel_keyboard()
        )
        await state.update_data(frequency="custom")
        await state.set_state(MedicationReminder.waiting_for_times)
    else:
        await message.answer("❌ Пожалуйста, выберите вариант из меню")


@router.message(MedicationReminder.waiting_for_times, F.text == "⏭ Пропустить")
async def skip_custom_times(message: Message, state: FSMContext):
    """Пропустить ввод времени, использовать по умолчанию"""
    await message.answer(
        "✅ Используется время по умолчанию\n\n"
        "📝 Шаг 5 из 6\n\n"
        "Введите дату начала приема в формате ДД.ММ.ГГГГ\n"
        "Или введите 'сегодня':",
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(MedicationReminder.waiting_for_start_date)


@router.message(MedicationReminder.waiting_for_times, F.text)
async def process_times(message: Message, state: FSMContext):
    """Обработка времени приема"""
    times_text = sanitize_text(message.text)

    # Парсим времена
    times = [t.strip() for t in times_text.split(",")]

    # Валидация времен
    valid_times = []
    for time_str in times:
        try:
            # Проверяем формат HH:MM
            time_obj = datetime.strptime(time_str, "%H:%M").time()
            valid_times.append(time_str)
        except ValueError:
            await message.answer(
                f"❌ Неверный формат времени: {time_str}\n\n"
                f"Используйте формат ЧЧ:ММ (например: 09:00)"
            )
            return

    if len(valid_times) == 0:
        await message.answer("❌ Не указано ни одного времени")
        return

    if len(valid_times) > 10:
        await message.answer("❌ Слишком много времен (максимум 10)")
        return

    await state.update_data(times=valid_times)

    await message.answer(
        f"✅ Время приема: {', '.join(valid_times)}\n\n"
        f"📝 Шаг 5 из 6\n\n"
        f"Введите дату начала приема в формате ДД.ММ.ГГГГ\n"
        f"Или введите 'сегодня':",
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(MedicationReminder.waiting_for_start_date)


@router.message(MedicationReminder.waiting_for_start_date, F.text)
async def process_start_date(message: Message, state: FSMContext):
    """Обработка даты начала приема"""
    date_text = sanitize_text(message.text.lower())

    if date_text == "сегодня":
        start_date = datetime.now().date()
    else:
        try:
            # Заменяем разделители
            normalized = date_text.replace("/", ".").replace(" ", ".").replace("-", ".")
            start_date = datetime.strptime(normalized, "%d.%m.%Y").date()

            # Проверка что дата не в прошлом
            if start_date < datetime.now().date():
                await message.answer("❌ Дата начала не может быть в прошлом")
                return

        except ValueError:
            await message.answer(
                "❌ Неверный формат даты\n\n"
                "Используйте формат: ДД.ММ.ГГГГ\n"
                "Например: 15.03.2024\n"
                "Или введите 'сегодня'"
            )
            return

    await state.update_data(start_date=start_date.isoformat())

    await message.answer(
        f"✅ Дата начала: {start_date.strftime('%d.%m.%Y')}\n\n"
        f"📝 Шаг 6 из 6\n\n"
        f"Введите дату окончания приема в формате ДД.ММ.ГГГГ\n"
        f"Или нажмите ⏭ Пропустить (без срока окончания):",
        reply_markup=get_skip_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(MedicationReminder.waiting_for_end_date)


@router.message(MedicationReminder.waiting_for_end_date, F.text == "⏭ Пропустить")
async def skip_end_date(message: Message, state: FSMContext):
    """Пропустить дату окончания"""
    await state.update_data(end_date=None)

    await message.answer(
        "✅ Без даты окончания\n\n"
        "Добавить заметку? (например, 'принимать после еды')\n"
        "Или нажмите ⏭ Пропустить:",
        reply_markup=get_skip_keyboard()
    )
    await state.set_state(MedicationReminder.waiting_for_notes)


@router.message(MedicationReminder.waiting_for_end_date, F.text)
async def process_end_date(message: Message, state: FSMContext):
    """Обработка даты окончания приема"""
    date_text = sanitize_text(message.text)

    try:
        # Заменяем разделители
        normalized = date_text.replace("/", ".").replace(" ", ".").replace("-", ".")
        end_date = datetime.strptime(normalized, "%d.%m.%Y").date()

        # Проверка что дата позже начала
        data = await state.get_data()
        start_date = datetime.fromisoformat(data['start_date']).date()

        if end_date <= start_date:
            await message.answer("❌ Дата окончания должна быть позже даты начала")
            return

    except ValueError:
        await message.answer(
            "❌ Неверный формат даты\n\n"
            "Используйте формат: ДД.ММ.ГГГГ\n"
            "Например: 30.03.2024"
        )
        return

    await state.update_data(end_date=end_date.isoformat())

    await message.answer(
        f"✅ Дата окончания: {end_date.strftime('%d.%m.%Y')}\n\n"
        f"Добавить заметку? (например, 'принимать после еды')\n"
        f"Или нажмите ⏭ Пропустить:",
        reply_markup=get_skip_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(MedicationReminder.waiting_for_notes)


@router.message(MedicationReminder.waiting_for_notes, F.text == "⏭ Пропустить")
async def skip_notes(message: Message, state: FSMContext):
    """Пропустить заметки"""
    await state.update_data(notes=None)
    await show_confirmation(message, state)


@router.message(MedicationReminder.waiting_for_notes, F.text)
async def process_notes(message: Message, state: FSMContext):
    """Обработка заметок"""
    notes = sanitize_text(message.text)

    if len(notes) > 500:
        await message.answer("❌ Заметка слишком длинная (максимум 500 символов)")
        return

    await state.update_data(notes=notes)
    await show_confirmation(message, state)


async def show_confirmation(message: Message, state: FSMContext):
    """Показать подтверждение перед сохранением"""
    data = await state.get_data()

    # Форматируем сводку
    summary = "📋 *Проверьте данные:*\n\n"
    summary += f"💊 *Лекарство:* {data['medication_name']}\n"
    summary += f"📏 *Дозировка:* {data['dosage']}\n"
    summary += f"⏰ *Время приема:* {', '.join(data['times'])}\n"

    start_date = datetime.fromisoformat(data['start_date'])
    summary += f"📅 *Начало:* {start_date.strftime('%d.%m.%Y')}\n"

    if data.get('end_date'):
        end_date = datetime.fromisoformat(data['end_date'])
        summary += f"📅 *Окончание:* {end_date.strftime('%d.%m.%Y')}\n"
    else:
        summary += "📅 *Окончание:* без срока\n"

    if data.get('notes'):
        summary += f"\n📝 *Заметка:* {data['notes']}\n"

    summary += "\n✅ Нажмите *Сохранить* для создания напоминания"

    await message.answer(
        summary,
        reply_markup=get_confirmation_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(MedicationReminder.confirming)


@router.message(MedicationReminder.confirming, F.text == "✅ Сохранить")
async def save_medication(message: Message, state: FSMContext):
    """Сохранить лекарство в БД"""
    try:
        data = await state.get_data()
        user_id = message.from_user.id

        medication_data = {
            'user_id': user_id,
            'medication_name': data['medication_name'],
            'dosage': data['dosage'],
            'frequency': data.get('frequency', 'custom'),
            'times': data['times'],
            'start_date': data['start_date'],
            'end_date': data.get('end_date'),
            'notes': data.get('notes'),
            'is_active': True,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }

        supabase_client.table('medications').insert(medication_data).execute()

        await message.answer(
            "✅ *Напоминание создано!*\n\n"
            f"Вы будете получать напоминания о приеме\n"
            f"*{data['medication_name']}* в указанное время",
            reply_markup=get_medications_menu(),
            parse_mode="Markdown"
        )

        await state.clear()
        logger.info(f"Medication reminder created for user {user_id}")

    except Exception as e:
        logger.error(f"Error saving medication: {e}", exc_info=True)
        await message.answer(
            "❌ Ошибка при сохранении напоминания\n"
            "Попробуйте позже",
            reply_markup=get_medications_menu()
        )
        await state.clear()


@router.message(F.text == "📋 Мои лекарства")
async def show_medications_list(message: Message):
    """Показать список лекарств пользователя"""
    try:
        user_id = message.from_user.id

        response = supabase_client.table('medications') \
            .select('*') \
            .eq('user_id', user_id) \
            .eq('is_active', True) \
            .order('created_at', desc=True) \
            .execute()

        if not response.data or len(response.data) == 0:
            await message.answer(
                "📋 *Мои лекарства*\n\n"
                "У вас пока нет активных напоминаний\n\n"
                "Нажмите ➕ *Добавить лекарство*",
                reply_markup=get_medications_menu(),
                parse_mode="Markdown"
            )
            return

        medications_text = "📋 *Мои лекарства*\n\n"
        medications_text += f"Всего активных: {len(response.data)}\n\n"

        for idx, med in enumerate(response.data, 1):
            medications_text += f"*{idx}. {med['medication_name']}*\n"
            medications_text += f"   📏 {med['dosage']}\n"
            medications_text += f"   ⏰ {', '.join(med['times'])}\n"

            start_date = datetime.fromisoformat(med['start_date'])
            medications_text += f"   📅 С {start_date.strftime('%d.%m.%Y')}"

            if med.get('end_date'):
                end_date = datetime.fromisoformat(med['end_date'])
                medications_text += f" до {end_date.strftime('%d.%m.%Y')}"

            medications_text += "\n\n"

        medications_text += "💡 Для управления напоминаниями используйте меню"

        await message.answer(
            medications_text,
            reply_markup=get_medications_menu(),
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.error(f"Error loading medications: {e}", exc_info=True)
        await message.answer(
            "❌ Ошибка при загрузке списка лекарств",
            reply_markup=get_medications_menu()
        )
