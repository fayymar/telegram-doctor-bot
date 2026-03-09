from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from bot.states import Consultation
from bot.keyboards import (
    get_main_menu,
    get_symptoms_input_keyboard,
    get_symptoms_confirmation,
    get_duration_keyboard,
    get_additional_symptoms_keyboard,
    get_additional_cancel_keyboard,
    get_manual_symptoms_keyboard,
    update_symptom_selection,
    get_final_confirmation,
    get_result_keyboard
)
from services.ai_service import AIService
from services.medical_router import MedicalRouter
from database.connection import supabase_client
from utils.logger import setup_logger

logger = setup_logger(__name__)
router = Router()
ai_service = AIService()  # Используется для генерации симптомов
medical_router = MedicalRouter()  # Используется для рекомендации врачей


# ============ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ============

def format_symptoms_with_bullets(text: str) -> str:
    """
    Форматирует текст симптомов с маркерами

    Разбивает текст на предложения и форматирует каждое с маркером.
    Предложения могут быть разделены точкой, запятой или новой строкой.

    Args:
        text: Исходный текст симптомов

    Returns:
        Отформатированный текст с маркерами
    """
    if not text or text == 'не указано':
        return text

    # Разбиваем по точкам, но сохраняем точки после сокращений (см, кг и т.д.)
    import re

    # Заменяем точки после сокращений на временный маркер
    text = re.sub(r'\b(см|кг|мм|гр|мл|др|т\.д|т\.п)\.\s*', r'\1__TEMP_DOT__ ', text)

    # Разбиваем на предложения по точкам и переносам строк
    sentences = []
    for part in text.split('\n'):
        sentences.extend([s.strip() for s in part.split('.') if s.strip()])

    # Возвращаем точки после сокращений
    sentences = [s.replace('__TEMP_DOT__', '.') for s in sentences]

    # Убираем пустые строки и дубликаты
    sentences = [s for s in sentences if s and len(s) > 2]

    # Если получилось одно предложение - возвращаем с одним маркером
    if len(sentences) == 1:
        return f"• {sentences[0]}"

    # Если несколько - форматируем каждое
    return '\n'.join([f"• {s}" for s in sentences])


async def get_user_profile(user_id: int) -> dict:
    """Получает профиль пользователя для AI"""
    try:
        response = supabase_client.table('user_profiles').select('*').eq('user_id', user_id).execute()
        if response.data:
            profile = response.data[0]
            
            if profile.get('birthdate'):
                birthdate = datetime.fromisoformat(profile['birthdate'])
                age = (datetime.now() - birthdate).days // 365
            else:
                age = None
            
            return {
                'gender': profile.get('gender'),
                'age': age,
                'height': profile.get('height'),
                'weight': profile.get('weight')
            }
    except Exception as e:
        logger.error(f"DB Error: {e}")
    
    return {'gender': None, 'age': None, 'height': None, 'weight': None}


async def save_consultation(user_id: int, data: dict):
    """Сохраняет консультацию в БД"""
    try:
        import json
        
        consultation_data = {
            'user_id': user_id,
            'symptoms': json.dumps(data.get('symptoms', {}), ensure_ascii=False),
            'questions_answers': json.dumps(data.get('questions_answers', {}), ensure_ascii=False),
            'recommended_doctor': data.get('specialist'),
            'urgency_level': data.get('urgency'),
            'created_at': datetime.now().isoformat()
        }
        
        supabase_client.table('consultations').insert(consultation_data).execute()
    except Exception as e:
        logger.error(f"DB Error: {e}")


# ============ НАЧАЛО КОНСУЛЬТАЦИИ ============

@router.message(F.text == "🩺 Новая консультация")
async def start_consultation(message: Message, state: FSMContext):
    """Начало новой консультации"""
    try:
        response = supabase_client.table('user_profiles').select('user_id').eq('user_id', message.from_user.id).execute()
        if not response.data:
            await message.answer(
                "❌ Пожалуйста, сначала зарегистрируйтесь\n"
                "Используйте /start"
            )
            return
    except Exception as e:
        logger.error(f"DB Error: {e}")
    
    await state.clear()
    
    await message.answer(
        "🩺 *Новая консультация*\n\n"
        "📝 *Этап 1 из 5*\n\n"
        "Опишите ваши симптомы максимально подробно.\n"
        "Что вас беспокоит? Какие ощущения?\n\n"
        "💡 Вы можете отправить текст или голосовое сообщение.",
        reply_markup=get_symptoms_input_keyboard(),
        parse_mode="Markdown"
    )
    
    await state.set_state(Consultation.waiting_for_symptoms)


# ============ ЭТАП 1: ОПИСАНИЕ СИМПТОМОВ ============

@router.message(Consultation.waiting_for_symptoms, F.text == "❌ Отменить")
async def cancel_from_symptoms(message: Message, state: FSMContext):
    """Отмена на первом этапе (описание симптомов)"""
    await state.clear()
    await message.answer(
        "❌ Консультация отменена",
        reply_markup=get_main_menu()
    )


@router.message(Consultation.waiting_for_symptoms, F.text)
async def process_symptoms_text(message: Message, state: FSMContext):
    """Обработка текстового описания симптомов"""
    
    symptoms_text = message.text.strip()
    
    # ВАЛИДАЦИЯ
    await message.answer("⏳ Проверяю ваше сообщение...")
    
    validation = ai_service.validate_symptoms(symptoms_text)
    
    if not validation['is_valid']:
        await message.answer(
            f"❌ *Ошибка валидации*\n\n"
            f"{validation['reason']}\n\n"
            f"Пожалуйста, опишите именно медицинские симптомы:\n"
            f"• Боли и их локализация\n"
            f"• Температура\n"
            f"• Тошнота, слабость\n"
            f"• Другие физические ощущения\n\n"
            f"Попробуйте ещё раз:",
            parse_mode="Markdown"
        )
        return
    
    # ОКУЛЬТУРИВАНИЕ СИМПТОМОВ
    await message.answer("✏️ Улучшаю формулировку...")
    
    improved_symptoms = ai_service.improve_symptoms_text(symptoms_text)

    await state.update_data(main_symptoms=improved_symptoms)

    # Форматируем симптомы с маркерами
    formatted_symptoms = format_symptoms_with_bullets(improved_symptoms)

    await message.answer(
        f"📝 *Ваши симптомы:*\n\n"
        f"{formatted_symptoms}\n\n"
        f"Подтвердите или добавьте детали:",
        reply_markup=get_symptoms_confirmation(),
        parse_mode="Markdown"
    )
    
    await state.set_state(Consultation.confirming_symptoms)


@router.message(Consultation.waiting_for_symptoms, F.voice)
async def process_symptoms_voice(message: Message, state: FSMContext):
    """Обработка голосового сообщения"""
    await message.answer(
        "🎤 Голосовые сообщения временно недоступны\n\n"
        "Пожалуйста, опишите симптомы текстом."
    )


# ============ ПОДТВЕРЖДЕНИЕ СИМПТОМОВ ============

@router.message(Consultation.confirming_symptoms, F.text == "✅ Подтвердить")
async def confirm_symptoms(message: Message, state: FSMContext):
    """Подтверждение симптомов"""
    await message.answer("✅ Симптомы подтверждены")

    # Генерируем дополнительные симптомы через AI
    await message.answer("⏳ Анализирую симптомы...")

    data = await state.get_data()
    main_symptoms = data.get('main_symptoms', '')

    additional_symptoms = ai_service.generate_additional_symptoms(
        main_symptoms=main_symptoms,
        duration=""  # Пока давность не известна
    )

    # Если AI не сгенерировал симптомы - предлагаем написать вручную
    if not additional_symptoms:
        logger.info("No additional symptoms generated by AI, asking user for manual input")
        await message.answer(
            "⚠️ Не удалось подобрать дополнительные симптомы автоматически.\n\n"
            "📝 Опишите дополнительные симптомы вручную или нажмите 'Готово' для продолжения:",
            reply_markup=get_manual_symptoms_keyboard()
        )
        await state.update_data(
            additional_symptoms_options=[],
            selected_additional=set()
        )
        await state.set_state(Consultation.waiting_for_other_symptoms)
        return

    await state.update_data(
        additional_symptoms_options=additional_symptoms,
        selected_additional=set()
    )

    await message.answer(
        "📋 *Этап 2 из 5*\n\n"
        "Отметьте, что ещё вас беспокоит:\n"
        "(выберите все подходящие варианты)",
        reply_markup=get_additional_cancel_keyboard(),
        parse_mode="Markdown"
    )

    # Формируем клавиатуру
    keyboard = get_additional_symptoms_keyboard(additional_symptoms)

    # ВАЖНО: Второе сообщение с инлайн-кнопками!
    await message.answer(
        "Выберите симптомы:",
        reply_markup=keyboard
    )

    await state.set_state(Consultation.selecting_additional_symptoms)


@router.message(Consultation.confirming_symptoms, F.text == "🔄 Начать заново")
async def restart_symptoms(message: Message, state: FSMContext):
    """Начать ввод симптомов заново"""
    await state.update_data(main_symptoms=None)

    await message.answer(
        "📝 Опишите ваши симптомы заново.\n\n"
        "Что вас беспокоит? Какие ощущения?\n\n"
        "💡 Вы можете отправить текст или голосовое сообщение.",
        reply_markup=get_cancel_keyboard()
    )

    await state.set_state(Consultation.waiting_for_symptoms)


@router.message(
    Consultation.confirming_symptoms,
    F.text,
    ~F.text.in_(["✅ Подтвердить", "🔄 Начать заново", "❌ Отменить"])
)
async def add_details_to_symptoms(message: Message, state: FSMContext):
    """Добавление деталей к уже введённым симптомам"""
    new_details = message.text.strip()

    if len(new_details) < 2:
        await message.answer("❌ Опишите детали чуть подробнее")
        return

    data = await state.get_data()
    current_symptoms = (data.get("main_symptoms") or "").strip()

    if current_symptoms:
        combined_symptoms = f"{current_symptoms}. {new_details}"
    else:
        combined_symptoms = new_details

    await message.answer("⏳ Добавляю детали...")
    await message.answer("✏️ Обновляю формулировку...")

    try:
        improved_symptoms = ai_service.improve_symptoms_text(combined_symptoms)
    except Exception as e:
        logger.error(f"Error while improving combined symptoms: {e}", exc_info=True)
        improved_symptoms = combined_symptoms

    await state.update_data(main_symptoms=improved_symptoms)

    formatted_symptoms = format_symptoms_with_bullets(improved_symptoms)

    await message.answer(
        f"📝 *Обновлённые симптомы:*\n\n"
        f"{formatted_symptoms}\n\n"
        f"Теперь можете:\n"
        f"• нажать *✅ Подтвердить*\n"
        f"• или отправить ещё одно сообщение с деталями",
        reply_markup=get_symptoms_confirmation(),
        parse_mode="Markdown"
    )

    if len(new_details) < 2:
        await message.answer("❌ Опишите детали чуть подробнее")
        return

    data = await state.get_data()
    current_symptoms = data.get("main_symptoms", "").strip()

    # Склеиваем старые симптомы и новые детали
    if current_symptoms:
        combined_symptoms = f"{current_symptoms}. {new_details}"
    else:
        combined_symptoms = new_details

    await message.answer("⏳ Добавляю детали...")
    await message.answer("✏️ Обновляю формулировку...")

    try:
        improved_symptoms = ai_service.improve_symptoms_text(combined_symptoms)
    except Exception as e:
        logger.error(f"Error while improving combined symptoms: {e}", exc_info=True)
        improved_symptoms = combined_symptoms

    await state.update_data(main_symptoms=improved_symptoms)

    formatted_symptoms = format_symptoms_with_bullets(improved_symptoms)

    await message.answer(
        f"📝 *Обновлённые симптомы:*\n\n"
        f"{formatted_symptoms}\n\n"
        f"Теперь можете:\n"
        f"• нажать *✅ Подтвердить*\n"
        f"• или отправить ещё одно сообщение с деталями",
        reply_markup=get_symptoms_confirmation(),
        parse_mode="Markdown"
    )
    """Начать описание заново"""
    await message.answer(
        "🔄 Начинаем заново\n\n"
        "Опишите ваши симптомы:",
        reply_markup=get_symptoms_input_keyboard()
    )
    
    await state.set_state(Consultation.waiting_for_symptoms)


# ============ ЭТАП 2: ДОПОЛНИТЕЛЬНЫЕ СИМПТОМЫ ============

@router.message(Consultation.waiting_for_duration, F.text == "🔙 Назад")
async def back_from_duration(message: Message, state: FSMContext):
    """Возврат с этапа давности к уточняющим симптомам"""
    data = await state.get_data()
    options = data.get('clarifying_symptoms_options', [])

    if options:
        await message.answer(
            "📋 *Этап 3 из 5*\n\n"
            "Уточните дополнительные детали:",
            parse_mode="Markdown"
        )
        await message.answer(
            "Выберите симптомы:",
            reply_markup=get_additional_symptoms_keyboard(options)
        )
        await state.set_state(Consultation.selecting_clarifying_symptoms)
    else:
        # Если уточняющих симптомов не было - возвращаемся к дополнительным
        additional_options = data.get('additional_symptoms_options', [])
        if additional_options:
            await message.answer(
                "📋 *Этап 2 из 5*\n\n"
                "Отметьте, что ещё вас беспокоит:",
                parse_mode="Markdown"
            )
            await message.answer(
                "Выберите симптомы:",
                reply_markup=get_additional_symptoms_keyboard(additional_options)
            )
            await state.set_state(Consultation.selecting_additional_symptoms)
        else:
            # Если и дополнительных не было - к основным симптомам
            main_symptoms = data.get('main_symptoms', '')
            formatted_symptoms = format_symptoms_with_bullets(main_symptoms)
            await message.answer(
                f"📝 *Ваши симптомы:*\n\n"
                f"{formatted_symptoms}\n\n"
                f"Подтвердите или добавьте детали:",
                reply_markup=get_symptoms_confirmation(),
                parse_mode="Markdown"
            )
            await state.set_state(Consultation.confirming_symptoms)

@router.message(Consultation.waiting_for_duration, F.text.in_([
    "⏱ Меньше 24 часов", "📅 1-3 дня", "📅 3-7 дней", "📆 Больше недели"
]))
async def process_duration(message: Message, state: FSMContext):
    """Обработка выбора давности"""
    duration_text = message.text.replace("⏱ ", "").replace("📅 ", "").replace("📆 ", "")

    await state.update_data(duration=duration_text)

    await message.answer(f"✅ Давность: {duration_text}")

    # Переходим к финальному подтверждению
    await show_final_confirmation(message, state)


@router.message(Consultation.selecting_additional_symptoms, F.text == "🔙 Назад")
async def back_from_additional(message: Message, state: FSMContext):
    """Возврат с этапа дополнительных симптомов к подтверждению основных симптомов"""
    data = await state.get_data()
    main_symptoms = data.get('main_symptoms', '')

    # Форматируем симптомы с маркерами
    formatted_symptoms = format_symptoms_with_bullets(main_symptoms)

    await message.answer(
        f"📝 *Ваши симптомы:*\n\n"
        f"{formatted_symptoms}\n\n"
        f"Подтвердите или добавьте детали:",
        reply_markup=get_symptoms_confirmation(),
        parse_mode="Markdown"
    )

    await state.set_state(Consultation.confirming_symptoms)


@router.callback_query(Consultation.selecting_additional_symptoms, F.data.startswith("sym_"))
async def toggle_symptom(callback: CallbackQuery, state: FSMContext):
    """Переключение выбора симптома"""
    try:
        # Извлекаем индекс из callback_data
        idx = int(callback.data.split("_")[1])

        data = await state.get_data()
        options = data.get('additional_symptoms_options', [])
        selected = data.get('selected_additional', set())

        # Получаем симптом по индексу
        if idx >= len(options):
            logger.warning(f"Symptom index {idx} out of range (max {len(options)-1})")
            await callback.answer("❌ Ошибка выбора", show_alert=True)
            return

        symptom = options[idx]

        # Переключаем выбор
        if symptom in selected:
            selected.remove(symptom)
        else:
            selected.add(symptom)

        await state.update_data(selected_additional=selected)

        # Обновляем клавиатуру
        updated_keyboard = update_symptom_selection(
            callback.message.reply_markup,
            selected,
            options  # Передаём полный список
        )

        await callback.message.edit_reply_markup(reply_markup=updated_keyboard)
        await callback.answer()  # Убираем часики

    except Exception as e:
        logger.error(f"Error in toggle_symptom: {e}", exc_info=True)
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(Consultation.selecting_additional_symptoms, F.data == "no_additional")
async def no_additional_symptoms(callback: CallbackQuery, state: FSMContext):
    """Нет дополнительных симптомов"""
    await state.update_data(selected_additional=set())
    
    await callback.message.delete()
    await callback.message.answer("✅ Дополнительных симптомов нет")
    
    await show_final_confirmation(callback.message, state)
    await callback.answer()


@router.callback_query(Consultation.selecting_additional_symptoms, F.data == "other_symptom")
async def other_symptom(callback: CallbackQuery, state: FSMContext):
    """Описать другой симптом"""
    await callback.message.delete()
    await callback.message.answer(
        "✏️ Опишите дополнительный симптом:",
        reply_markup=get_additional_cancel_keyboard()
    )
    
    await state.set_state(Consultation.waiting_for_other_symptoms)
    await callback.answer()


@router.message(Consultation.waiting_for_other_symptoms, F.text == "✅ Готово")
async def done_manual_symptoms(message: Message, state: FSMContext):
    """Завершение ручного ввода симптомов"""
    data = await state.get_data()
    selected = data.get('selected_additional', set())
    
    if selected:
        symptoms_list = "\n".join([f"• {s}" for s in selected])
        await message.answer(
            f"✅ *Дополнительные симптомы:*\n\n{symptoms_list}",
            parse_mode="Markdown"
        )
    else:
        await message.answer("✅ Дополнительных симптомов не добавлено")
    
    await show_final_confirmation(message, state)


@router.message(Consultation.waiting_for_other_symptoms, F.text == "🔙 Назад")
async def back_from_other_symptom(message: Message, state: FSMContext):
    """Возврат от ввода другого симптома к выбору"""
    data = await state.get_data()
    options = data.get('additional_symptoms_options', [])

    # Если есть опции - показываем их
    if options:
        await message.answer(
            "📋 *Этап 2 из 5*\n\n"
            "Отметьте, что ещё вас беспокоит:",
            parse_mode="Markdown"
        )
        await message.answer(
            "Выберите симптомы:",
            reply_markup=get_additional_symptoms_keyboard(options)
        )
        await state.set_state(Consultation.selecting_additional_symptoms)
    else:
        # Если опций нет - возвращаемся к подтверждению основных симптомов
        main_symptoms = data.get('main_symptoms', '')
        formatted_symptoms = format_symptoms_with_bullets(main_symptoms)
        await message.answer(
            f"📝 *Ваши симптомы:*\n\n"
            f"{formatted_symptoms}\n\n"
            f"Подтвердите или добавьте детали:",
            reply_markup=get_symptoms_confirmation(),
            parse_mode="Markdown"
        )
        await state.set_state(Consultation.confirming_symptoms)


@router.message(Consultation.waiting_for_other_symptoms, F.text)
async def process_other_symptom(message: Message, state: FSMContext):
    """Обработка другого симптома"""
    other_symptom = message.text.strip()
    
    # Валидация
    validation = ai_service.validate_symptoms(other_symptom)
    
    if not validation['is_valid']:
        await message.answer(
            f"❌ {validation['reason']}\n\n"
            "Опишите медицинский симптом:"
        )
        return
    
    data = await state.get_data()
    selected = data.get('selected_additional', set())
    selected.add(validation['symptoms'] if validation['symptoms'] else other_symptom)
    
    await state.update_data(selected_additional=selected)
    
    options = data.get('additional_symptoms_options', [])
    
    # Если есть опции - возвращаемся к выбору
    if options:
        await message.answer("✅ Симптом добавлен")
        await message.answer(
            "Выберите ещё или нажмите 'Готово':",
            reply_markup=get_additional_symptoms_keyboard(options)
        )
        await state.set_state(Consultation.selecting_additional_symptoms)
    else:
        # Если опций нет - продолжаем ручной ввод
        await message.answer(
            f"✅ Симптом добавлен: {validation['symptoms'] if validation['symptoms'] else other_symptom}\n\n"
            f"Добавьте ещё симптомы или нажмите 'Готово':",
            reply_markup=get_manual_symptoms_keyboard()
        )


@router.callback_query(Consultation.selecting_additional_symptoms, F.data == "done_additional")
async def done_additional_symptoms(callback: CallbackQuery, state: FSMContext):
    """Завершение выбора дополнительных симптомов"""
    data = await state.get_data()
    selected = data.get('selected_additional', set())

    await callback.message.delete()

    if selected:
        symptoms_list = "\n".join([f"• {s}" for s in selected])
        await callback.message.answer(
            f"✅ *Дополнительные симптомы:*\n\n{symptoms_list}",
            parse_mode="Markdown"
        )
    else:
        await callback.message.answer("✅ Дополнительных симптомов не выбрано")

    # Генерируем уточняющие симптомы через AI
    await callback.message.answer("⏳ Подбираю уточняющие вопросы...")

    main_symptoms = data.get('main_symptoms', '')
    additional_symptoms = list(selected) if selected else []

    clarifying_symptoms = ai_service.generate_additional_symptoms(
        main_symptoms=main_symptoms + " " + " ".join(additional_symptoms),
        duration=""
    )

    # Если AI не сгенерировал симптомы - переходим к давности
    if not clarifying_symptoms:
        logger.info("No clarifying symptoms generated, skipping to duration")
        await callback.message.answer(
            "📅 *Этап 4 из 5*\n\n"
            "Как давно вас беспокоят эти симптомы?",
            reply_markup=get_duration_keyboard(),
            parse_mode="Markdown"
        )
        await state.set_state(Consultation.waiting_for_duration)
        await callback.answer()
        return

    await state.update_data(
        clarifying_symptoms_options=clarifying_symptoms,
        selected_clarifying=set()
    )

    await callback.message.answer(
        "📋 *Этап 3 из 5*\n\n"
        "Уточните дополнительные детали:\n"
        "(выберите все подходящие варианты)",
        reply_markup=get_additional_cancel_keyboard(),
        parse_mode="Markdown"
    )

    # Формируем клавиатуру
    keyboard = get_additional_symptoms_keyboard(clarifying_symptoms)

    # Второе сообщение с инлайн-кнопками
    await callback.message.answer(
        "Выберите симптомы:",
        reply_markup=keyboard
    )

    await state.set_state(Consultation.selecting_clarifying_symptoms)
    await callback.answer()


# ============ ЭТАП 3: УТОЧНЯЮЩИЕ СИМПТОМЫ ============

@router.message(Consultation.selecting_clarifying_symptoms, F.text == "🔙 Назад")
async def back_from_clarifying(message: Message, state: FSMContext):
    """Возврат с этапа уточняющих симптомов к дополнительным симптомам"""
    data = await state.get_data()
    options = data.get('additional_symptoms_options', [])

    if options:
        await message.answer(
            "📋 *Этап 2 из 5*\n\n"
            "Отметьте, что ещё вас беспокоит:",
            parse_mode="Markdown"
        )
        await message.answer(
            "Выберите симптомы:",
            reply_markup=get_additional_symptoms_keyboard(options)
        )
        await state.set_state(Consultation.selecting_additional_symptoms)
    else:
        # Если опций нет - возвращаемся к подтверждению основных симптомов
        main_symptoms = data.get('main_symptoms', '')
        formatted_symptoms = format_symptoms_with_bullets(main_symptoms)
        await message.answer(
            f"📝 *Ваши симптомы:*\n\n"
            f"{formatted_symptoms}\n\n"
            f"Подтвердите или добавьте детали:",
            reply_markup=get_symptoms_confirmation(),
            parse_mode="Markdown"
        )
        await state.set_state(Consultation.confirming_symptoms)


@router.callback_query(Consultation.selecting_clarifying_symptoms, F.data.startswith("sym_"))
async def toggle_clarifying_symptom(callback: CallbackQuery, state: FSMContext):
    """Переключение выбора уточняющего симптома"""
    try:
        idx = int(callback.data.split("_")[1])

        data = await state.get_data()
        options = data.get('clarifying_symptoms_options', [])
        selected = data.get('selected_clarifying', set())

        if idx >= len(options):
            logger.warning(f"Clarifying symptom index {idx} out of range")
            await callback.answer("❌ Ошибка выбора", show_alert=True)
            return

        symptom = options[idx]

        if symptom in selected:
            selected.remove(symptom)
        else:
            selected.add(symptom)

        await state.update_data(selected_clarifying=selected)

        updated_keyboard = update_symptom_selection(
            callback.message.reply_markup,
            selected,
            options
        )

        await callback.message.edit_reply_markup(reply_markup=updated_keyboard)
        await callback.answer()

    except Exception as e:
        logger.error(f"Error in toggle_clarifying_symptom: {e}", exc_info=True)
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(Consultation.selecting_clarifying_symptoms, F.data == "no_additional")
async def no_clarifying_symptoms(callback: CallbackQuery, state: FSMContext):
    """Нет уточняющих симптомов"""
    await state.update_data(selected_clarifying=set())

    await callback.message.delete()
    await callback.message.answer("✅ Уточняющих симптомов нет")

    # Переход к давности симптомов
    await callback.message.answer(
        "📅 *Этап 4 из 5*\n\n"
        "Как давно вас беспокоят эти симптомы?",
        reply_markup=get_duration_keyboard(),
        parse_mode="Markdown"
    )

    await state.set_state(Consultation.waiting_for_duration)
    await callback.answer()


@router.callback_query(Consultation.selecting_clarifying_symptoms, F.data == "other_symptom")
async def other_clarifying_symptom(callback: CallbackQuery, state: FSMContext):
    """Описать другой уточняющий симптом"""
    await callback.message.delete()
    await callback.message.answer(
        "✏️ Опишите дополнительный симптом:",
        reply_markup=get_additional_cancel_keyboard()
    )

    await state.set_state(Consultation.waiting_for_clarifying_symptoms)
    await callback.answer()


@router.callback_query(Consultation.selecting_clarifying_symptoms, F.data == "done_additional")
async def done_clarifying_symptoms(callback: CallbackQuery, state: FSMContext):
    """Завершение выбора уточняющих симптомов"""
    data = await state.get_data()
    selected = data.get('selected_clarifying', set())

    await callback.message.delete()

    if selected:
        symptoms_list = "\n".join([f"• {s}" for s in selected])
        await callback.message.answer(
            f"✅ *Уточняющие симптомы:*\n\n{symptoms_list}",
            parse_mode="Markdown"
        )
    else:
        await callback.message.answer("✅ Уточняющих симптомов не выбрано")

    # Переход к давности симптомов
    await callback.message.answer(
        "📅 *Этап 4 из 5*\n\n"
        "Как давно вас беспокоят эти симптомы?",
        reply_markup=get_duration_keyboard(),
        parse_mode="Markdown"
    )

    await state.set_state(Consultation.waiting_for_duration)
    await callback.answer()


@router.message(Consultation.waiting_for_clarifying_symptoms, F.text == "✅ Готово")
async def done_manual_clarifying(message: Message, state: FSMContext):
    """Завершение ручного ввода уточняющих симптомов"""
    data = await state.get_data()
    selected = data.get('selected_clarifying', set())

    if selected:
        symptoms_list = "\n".join([f"• {s}" for s in selected])
        await message.answer(
            f"✅ *Уточняющие симптомы:*\n\n{symptoms_list}",
            parse_mode="Markdown"
        )
    else:
        await message.answer("✅ Уточняющих симптомов не добавлено")

    # Переход к давности симптомов
    await message.answer(
        "📅 *Этап 4 из 5*\n\n"
        "Как давно вас беспокоят эти симптомы?",
        reply_markup=get_duration_keyboard(),
        parse_mode="Markdown"
    )

    await state.set_state(Consultation.waiting_for_duration)


@router.message(Consultation.waiting_for_clarifying_symptoms, F.text == "🔙 Назад")
async def back_from_clarifying_manual(message: Message, state: FSMContext):
    """Возврат от ручного ввода к выбору уточняющих симптомов"""
    data = await state.get_data()
    options = data.get('clarifying_symptoms_options', [])

    if options:
        await message.answer(
            "Выберите симптомы:",
            reply_markup=get_additional_symptoms_keyboard(options)
        )
        await state.set_state(Consultation.selecting_clarifying_symptoms)
    else:
        # Если опций нет - переходим к давности
        await message.answer(
            "📅 *Этап 4 из 5*\n\n"
            "Как давно вас беспокоят эти симптомы?",
            reply_markup=get_duration_keyboard(),
            parse_mode="Markdown"
        )
        await state.set_state(Consultation.waiting_for_duration)


@router.message(Consultation.waiting_for_clarifying_symptoms, F.text)
async def process_clarifying_symptom(message: Message, state: FSMContext):
    """Обработка ручного ввода уточняющего симптома"""
    clarifying_symptom = message.text.strip()

    # Валидация
    validation = ai_service.validate_symptoms(clarifying_symptom)

    if not validation['is_valid']:
        await message.answer(
            f"❌ {validation['reason']}\n\n"
            "Опишите медицинский симптом:"
        )
        return

    data = await state.get_data()
    selected = data.get('selected_clarifying', set())
    selected.add(validation['symptoms'] if validation['symptoms'] else clarifying_symptom)

    await state.update_data(selected_clarifying=selected)

    options = data.get('clarifying_symptoms_options', [])

    if options:
        await message.answer("✅ Симптом добавлен")
        await message.answer(
            "Выберите ещё или нажмите 'Готово':",
            reply_markup=get_additional_symptoms_keyboard(options)
        )
        await state.set_state(Consultation.selecting_clarifying_symptoms)
    else:
        await message.answer(
            f"✅ Симптом добавлен: {validation['symptoms'] if validation['symptoms'] else clarifying_symptom}\n\n"
            f"Добавьте ещё симптомы или нажмите 'Готово':",
            reply_markup=get_manual_symptoms_keyboard()
        )


# ============ ЭТАП 5: ФИНАЛЬНОЕ ПОДТВЕРЖДЕНИЕ ============

async def show_final_confirmation(message: Message, state: FSMContext):
    """Показывает финальное подтверждение с полным анамнезом"""
    data = await state.get_data()

    main_symptoms = data.get('main_symptoms', 'не указано')
    duration = data.get('duration', 'не указано')
    additional = data.get('selected_additional', set())
    clarifying = data.get('selected_clarifying', set())

    # Форматируем основные симптомы с маркерами
    formatted_main = format_symptoms_with_bullets(main_symptoms)

    anamnesis = f"📋 *Финальное подтверждение*\n\n"
    anamnesis += f"*Основные симптомы:*\n{formatted_main}\n\n"

    if additional:
        anamnesis += "*Дополнительные симптомы:*\n"
        for symptom in additional:
            anamnesis += f"• {symptom}\n"
        anamnesis += "\n"
    else:
        anamnesis += "*Дополнительные симптомы:* нет\n\n"

    if clarifying:
        anamnesis += "*Уточняющие симптомы:*\n"
        for symptom in clarifying:
            anamnesis += f"• {symptom}\n"
        anamnesis += "\n"
    else:
        anamnesis += "*Уточняющие симптомы:* нет\n\n"

    anamnesis += f"*Давность:* {duration}\n\n"
    anamnesis += "✅ Всё верно?"

    await message.answer(
        anamnesis,
        reply_markup=get_final_confirmation(),
        parse_mode="Markdown"
    )

    await state.set_state(Consultation.final_confirmation)


@router.message(Consultation.final_confirmation, F.text == "✅ Подтвердить")
async def final_confirm(message: Message, state: FSMContext):
    """Финальное подтверждение, показ полного анамнеза и объяснение выбора врача"""
    await message.answer("✅ Данные подтверждены")
    await message.answer("⏳ Анализирую симптомы и подбираю специалиста...")

    data = await state.get_data()
    user_profile = await get_user_profile(message.from_user.id)

    # Основные данные консультации
    main_symptoms = data.get('main_symptoms', 'не указано')
    duration = data.get('duration', 'не указано')

    additional_symptoms = sorted(list(data.get('selected_additional', set())))
    clarifying_symptoms = sorted(list(data.get('selected_clarifying', set())))
    all_additional = additional_symptoms + clarifying_symptoms

    # Получаем рекомендацию
    recommendation = medical_router.recommend_doctor(
        main_symptoms=main_symptoms,
        duration=duration,
        additional_symptoms=all_additional,
        user_profile=user_profile
    )

    # Главный рекомендованный специалист
    top_specialist = recommendation['specialists'][0]['name'] if recommendation['specialists'] else 'Терапевт'
    top_reason = recommendation['specialists'][0].get('reason', '') if recommendation['specialists'] else ''

    # Сохраняем консультацию в БД
    await save_consultation(message.from_user.id, {
        'symptoms': {
            'main': main_symptoms,
            'duration': duration,
            'additional': additional_symptoms,
            'clarifying': clarifying_symptoms
        },
        'questions_answers': {},
        'specialist': top_specialist,
        'urgency': recommendation['urgency']
    })

    urgency_emoji = {
        'emergency': '🚨',
        'high': '⚠️',
        'medium': '📋',
        'low': 'ℹ️'
    }

    urgency_text = {
        'emergency': 'СРОЧНО! Требуется скорая помощь',
        'high': 'Высокая (обратиться в течение 24 часов)',
        'medium': 'Средняя (обратиться в течение недели)',
        'low': 'Низкая (плановый приём)'
    }

    # Собираем весь список симптомов для красивого объяснения
    all_symptoms_for_text = []

    if main_symptoms and main_symptoms != 'не указано':
        # Основные симптомы могут быть строкой с несколькими жалобами
        main_formatted = format_symptoms_with_bullets(main_symptoms)
        main_lines = [line.replace('• ', '').strip() for line in main_formatted.split('\n') if line.strip()]
        all_symptoms_for_text.extend(main_lines)

    all_symptoms_for_text.extend(additional_symptoms)
    all_symptoms_for_text.extend(clarifying_symptoms)

    # Убираем дубли, сохраняя порядок
    unique_symptoms = []
    seen = set()
    for symptom in all_symptoms_for_text:
        cleaned = symptom.strip()
        if cleaned and cleaned.lower() not in seen:
            unique_symptoms.append(cleaned)
            seen.add(cleaned.lower())

    # ---------- ФОРМИРУЕМ ИТОГ ----------
    result_text = "📋 *Ваш анамнез*\n\n"

    formatted_main = format_symptoms_with_bullets(main_symptoms)
    result_text += f"*Основные симптомы:*\n{formatted_main}\n\n"

    if additional_symptoms:
        result_text += "*Дополнительные симптомы:*\n"
        for symptom in additional_symptoms:
            result_text += f"• {symptom}\n"
        result_text += "\n"
    else:
        result_text += "*Дополнительные симптомы:* нет\n\n"

    if clarifying_symptoms:
        result_text += "*Уточняющие симптомы:*\n"
        for symptom in clarifying_symptoms:
            result_text += f"• {symptom}\n"
        result_text += "\n"
    else:
        result_text += "*Уточняющие симптомы:* нет\n\n"

    result_text += f"*Давность симптомов:* {duration}\n\n"

    # ---------- ОБЪЯСНЯЕМ, ПОЧЕМУ ИМЕННО ЭТОТ ВРАЧ ----------
    result_text += "🧠 *Почему рекомендован именно этот врач*\n\n"

    if unique_symptoms:
        result_text += f"На основании указанных вами симптомов:\n"
        for symptom in unique_symptoms[:8]:
            result_text += f"• {symptom}\n"
        result_text += "\n"
    else:
        result_text += "На основании описанных вами жалоб и давности симптомов.\n\n"

    result_text += (
        f"*Рекомендована консультация: {top_specialist}*\n"
    )

    if top_reason:
        result_text += f"{top_reason}\n\n"
    else:
        result_text += (
            "Этот специалист выбран, потому что указанные симптомы "
            "чаще относятся к его профилю и требуют именно такой оценки.\n\n"
        )

    if duration and duration != 'не указано':
        result_text += (
            f"Также учтена *давность симптомов* — {duration}, "
            "потому что длительность жалоб влияет на срочность обращения и профиль врача.\n\n"
        )

    # ---------- СПИСОК СПЕЦИАЛИСТОВ ----------
    result_text += "🩺 *Рекомендованные специалисты*\n\n"

    specialists = recommendation['specialists'][:5]

    if specialists:
        total = sum(spec['match_percent'] for spec in specialists)

        normalized_specialists = []
        for spec in specialists:
            normalized_percent = (spec['match_percent'] / total) * 100 if total > 0 else 0
            normalized_specialists.append({
                'name': spec['name'],
                'percent': round(normalized_percent, 1),
                'reason': spec.get('reason', 'Рекомендуется консультация для уточнения диагноза.')
            })

        current_sum = sum(s['percent'] for s in normalized_specialists)
        if current_sum != 100.0 and normalized_specialists:
            diff = round(100.0 - current_sum, 1)
            normalized_specialists[0]['percent'] = round(normalized_specialists[0]['percent'] + diff, 1)

        for idx, spec in enumerate(normalized_specialists, 1):
            result_text += f"*{idx}. {spec['name']}* — вероятность {spec['percent']}%\n"
            result_text += f"_Почему: {spec['reason']}_\n\n"
    else:
        result_text += "*1. Терапевт* — базовая рекомендация\n"
        result_text += "_Почему: подходит для первичной оценки симптомов и дальнейшего направления к узкому специалисту._\n\n"

    # ---------- СРОЧНОСТЬ ----------
    result_text += f"{urgency_emoji.get(recommendation['urgency'], '📋')} *Срочность:* "
    result_text += f"{urgency_text.get(recommendation['urgency'], 'Средняя')}\n"
    result_text += f"_{recommendation.get('urgency_reason', 'Рекомендуется консультация.')}_"

    await message.answer(
        result_text,
        reply_markup=get_result_keyboard(),
        parse_mode="Markdown"
    )

    await state.clear()


@router.message(Consultation.final_confirmation, F.text == "➕ Добавить симптомы")
async def add_more_from_final(message: Message, state: FSMContext):
    """Добавить симптомы с финального этапа"""
    await message.answer(
        "✏️ Опишите дополнительные симптомы:",
        reply_markup=get_additional_cancel_keyboard()
    )
    
    await state.set_state(Consultation.waiting_for_other_symptoms)


@router.message(Consultation.final_confirmation, F.text == "🔄 Начать заново")
async def restart_consultation(message: Message, state: FSMContext):
    """Начать консультацию заново"""
    await state.clear()
    await start_consultation(message, state)


# ============ ДЕЙСТВИЯ ПОСЛЕ РЕЗУЛЬТАТА ============

@router.message(F.text == "🏠 В главное меню")
async def back_to_main_menu(message: Message, state: FSMContext):
    """Возврат в главное меню"""
    await state.clear()
    await message.answer(
        "Главное меню",
        reply_markup=get_main_menu()
    )


@router.message(F.text == "📝 Записаться (в разработке)")
async def book_appointment(message: Message):
    """Заглушка для записи к врачу"""
    await message.answer(
        "📝 Функция записи к врачу находится в разработке",
        reply_markup=get_result_keyboard()
    )


# ============ ОТМЕНА КОНСУЛЬТАЦИИ ============

@router.message(F.text == "❌ Отменить")
async def cancel_consultation_button(message: Message, state: FSMContext):
    """Отмена консультации через кнопку"""
    await state.clear()
    await message.answer(
        "❌ Консультация отменена",
        reply_markup=get_main_menu()
    )


@router.message(F.text == "/cancel")
async def cancel_consultation_command(message: Message, state: FSMContext):
    """Отмена через команду"""
    await state.clear()
    await message.answer(
        "❌ Консультация отменена",
        reply_markup=get_main_menu()
    )
