from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from bot.keyboards import (
    main_menu_keyboard, cancel_keyboard, confirm_symptoms_keyboard,
    duration_keyboard, additional_symptoms_keyboard, final_confirmation_keyboard,
    consultation_result_keyboard
)
from bot.states import ConsultationStates
from database.connection import db
from services.ai_service import ai_service

router = Router()


# === НАЧАЛО КОНСУЛЬТАЦИИ ===

@router.message(F.text == "🩺 Новая консультация")
@router.callback_query(F.data == "new_consultation")
async def start_consultation(event: Message | CallbackQuery, state: FSMContext):
    """Начать новую консультацию"""
    if isinstance(event, CallbackQuery):
        message = event.message
        await event.answer()
        user_id = message.chat.id
    else:
        message = event
        user_id = event.from_user.id
    
    # Проверяем профиль
    profile = await db.get_user_profile(user_id)
    if not profile:
        await message.answer("❌ Сначала завершите регистрацию через /start")
        return
    
    # Очищаем данные консультации
    await state.set_data({
        "initial_symptoms": [],
        "duration": None,
        "additional_symptoms": [],
        "ai_suggested_symptoms": []
    })
    
    await message.answer(
        "🩺 <b>Начинаем консультацию</b>\n\n"
        "Опишите ваши симптомы текстом или голосовым сообщением.\n"
        "Можете указать несколько симптомов сразу.\n\n"
        "<i>Например: \"болит голова и тошнит\" или \"температура 38 и кашель\"</i>",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(ConsultationStates.waiting_for_symptoms)


# === ЭТАП 1: ОПИСАНИЕ СИМПТОМОВ ===

@router.message(ConsultationStates.waiting_for_symptoms)
async def process_symptoms(message: Message, state: FSMContext):
    """Обработка симптомов"""
    # Получаем текст
    if message.text:
        symptoms_text = message.text
    elif message.voice:
        # TODO: В будущем добавить распознавание голоса
        await message.answer("🎤 Обработка голосовых сообщений временно недоступна. Пожалуйста, напишите симптомы текстом.")
        return
    else:
        await message.answer("⚠️ Пожалуйста, опишите симптомы текстом или голосовым сообщением.")
        return
    
    # Простое разделение симптомов (можно улучшить)
    symptoms_list = [s.strip() for s in symptoms_text.replace(',', ' и ').split(' и ')]
    symptoms_list = [s for s in symptoms_list if s]  # Убираем пустые
    
    # Сохраняем
    data = await state.get_data()
    data["initial_symptoms"] = symptoms_list
    await state.update_data(data)
    
    # Показываем подтверждение
    symptoms_formatted = "\n• ".join(symptoms_list)
    await message.answer(
        f"📝 <b>Вы указали:</b>\n\n• {symptoms_formatted}\n\n"
        f"Всё верно?",
        reply_markup=confirm_symptoms_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(ConsultationStates.confirming_symptoms)


@router.message(ConsultationStates.confirming_symptoms, F.text == "✅ Подтвердить")
async def confirm_symptoms(message: Message, state: FSMContext):
    """Подтверждение симптомов - переход к давности"""
    await message.answer(
        "⏱️ <b>Как давно наблюдается симптоматика?</b>",
        reply_markup=duration_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(ConsultationStates.selecting_duration)


@router.message(ConsultationStates.confirming_symptoms, F.text == "✏️ Добавить")
async def add_more_symptoms(message: Message, state: FSMContext):
    """Добавить еще симптомы"""
    await message.answer(
        "✏️ Опишите дополнительные симптомы:",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(ConsultationStates.adding_symptoms)


@router.message(ConsultationStates.adding_symptoms)
async def process_additional_initial_symptoms(message: Message, state: FSMContext):
    """Обработка дополнительных начальных симптомов"""
    if not message.text:
        await message.answer("⚠️ Пожалуйста, опишите симптомы текстом.")
        return
    
    # Получаем существующие симптомы
    data = await state.get_data()
    existing_symptoms = data.get("initial_symptoms", [])
    
    # Добавляем новые
    new_symptoms = [s.strip() for s in message.text.replace(',', ' и ').split(' и ')]
    new_symptoms = [s for s in new_symptoms if s]
    
    all_symptoms = existing_symptoms + new_symptoms
    data["initial_symptoms"] = all_symptoms
    await state.update_data(data)
    
    # Показываем обновленный список
    symptoms_formatted = "\n• ".join(all_symptoms)
    await message.answer(
        f"📝 <b>Обновленный список:</b>\n\n• {symptoms_formatted}\n\n"
        f"Всё верно?",
        reply_markup=confirm_symptoms_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(ConsultationStates.confirming_symptoms)


@router.message(ConsultationStates.confirming_symptoms, F.text == "🔄 Начать заново")
async def restart_from_symptoms(message: Message, state: FSMContext):
    """Начать заново с ввода симптомов"""
    await state.update_data(initial_symptoms=[])
    await message.answer(
        "🔄 Начинаем заново.\n\n"
        "Опишите ваши симптомы:",
        reply_markup=cancel_keyboard()
    )
    await state.set_state(ConsultationStates.waiting_for_symptoms)


# === ЭТАП 2: ДАВНОСТЬ СИМПТОМОВ ===

@router.message(ConsultationStates.selecting_duration, F.text.in_([
    "⏱️ Меньше 24 часов",
    "📅 1-3 дня",
    "📅 3-6 дней",
    "📅 Больше недели"
]))
async def process_duration(message: Message, state: FSMContext):
    """Обработка выбора давности"""
    # Извлекаем текст давности
    duration_map = {
        "⏱️ Меньше 24 часов": "Меньше 24 часов",
        "📅 1-3 дня": "1-3 дня",
        "📅 3-6 дней": "3-6 дней",
        "📅 Больше недели": "Больше недели"
    }
    duration = duration_map.get(message.text, message.text)
    
    # Сохраняем
    await state.update_data(duration=duration)
    
    # Генерируем дополнительные симптомы через AI
    await message.answer("🔍 Анализирую ваши симптомы и подбираю дополнительные варианты...", reply_markup=main_menu_keyboard())
    
    data = await state.get_data()
    profile = await db.get_user_profile(message.from_user.id)
    
    suggested_symptoms = await ai_service.generate_additional_symptoms(
        initial_symptoms=data["initial_symptoms"],
        duration=duration,
        user_profile=profile
    )
    
    # Сохраняем предложенные симптомы
    await state.update_data(ai_suggested_symptoms=suggested_symptoms)
    
    # Показываем клавиатуру с симптомами
    await message.answer(
        "❓ <b>Выберите дополнительные симптомы (если есть):</b>\n\n"
        "Нажимайте на симптомы которые у вас есть. "
        "Когда закончите - нажмите <b>✅ Готово</b>",
        reply_markup=additional_symptoms_keyboard(suggested_symptoms, []),
        parse_mode="HTML"
    )
    await state.set_state(ConsultationStates.selecting_additional_symptoms)


@router.message(ConsultationStates.selecting_duration, F.text == "⬅️ Назад")
async def back_to_symptoms_confirmation(message: Message, state: FSMContext):
    """Вернуться к подтверждению симптомов"""
    data = await state.get_data()
    symptoms = data.get("initial_symptoms", [])
    symptoms_formatted = "\n• ".join(symptoms)
    
    await message.answer(
        f"📝 <b>Вы указали:</b>\n\n• {symptoms_formatted}\n\n"
        f"Всё верно?",
        reply_markup=confirm_symptoms_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(ConsultationStates.confirming_symptoms)


# === ЭТАП 3: ДОПОЛНИТЕЛЬНЫЕ СИМПТОМЫ ===

@router.callback_query(F.data.startswith("toggle_symptom:"))
async def toggle_symptom(callback: CallbackQuery, state: FSMContext):
    """Переключение выбора симптома"""
    symptom = callback.data.split(":", 1)[1]
    
    data = await state.get_data()
    selected = data.get("additional_symptoms", [])
    suggested = data.get("ai_suggested_symptoms", [])
    
    # Добавляем или убираем
    if symptom in selected:
        selected.remove(symptom)
    else:
        selected.append(symptom)
    
    await state.update_data(additional_symptoms=selected)
    
    # Обновляем клавиатуру
    await callback.message.edit_reply_markup(
        reply_markup=additional_symptoms_keyboard(suggested, selected)
    )
    await callback.answer()


@router.callback_query(F.data == "no_additional_symptoms")
async def no_additional_symptoms(callback: CallbackQuery, state: FSMContext):
    """Пользователь выбрал "Ничего из этого" """
    await state.update_data(additional_symptoms=[])
    await callback.answer("Дополнительных симптомов нет")
    
    # Переход к финальному подтверждению
    await show_final_confirmation(callback.message, state)


@router.callback_query(F.data == "custom_symptoms")
async def enter_custom_symptoms(callback: CallbackQuery, state: FSMContext):
    """Ввод своих симптомов"""
    await callback.message.answer(
        "✏️ Опишите дополнительные симптомы текстом:",
        reply_markup=cancel_keyboard()
    )
    await callback.answer()
    await state.set_state(ConsultationStates.entering_custom_symptoms)


@router.message(ConsultationStates.entering_custom_symptoms)
async def process_custom_symptoms(message: Message, state: FSMContext):
    """Обработка своих симптомов"""
    if not message.text:
        await message.answer("⚠️ Пожалуйста, опишите симптомы текстом.")
        return
    
    # Парсим симптомы
    custom = [s.strip() for s in message.text.replace(',', ' и ').split(' и ')]
    custom = [s for s in custom if s]
    
    # Добавляем к уже выбранным
    data = await state.get_data()
    selected = data.get("additional_symptoms", [])
    all_additional = selected + custom
    
    await state.update_data(additional_symptoms=all_additional)
    
    # Переход к финальному подтверждению
    await show_final_confirmation(message, state)


@router.callback_query(F.data == "additional_symptoms_done")
async def finish_additional_symptoms(callback: CallbackQuery, state: FSMContext):
    """Завершение выбора дополнительных симптомов"""
    await callback.answer()
    await show_final_confirmation(callback.message, state)


@router.callback_query(F.data == "back_to_duration")
async def back_to_duration_selection(callback: CallbackQuery, state: FSMContext):
    """Вернуться к выбору давности"""
    await callback.message.answer(
        "⏱️ <b>Как давно наблюдается симптоматика?</b>",
        reply_markup=duration_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()
    await state.set_state(ConsultationStates.selecting_duration)


# === ЭТАП 4: ФИНАЛЬНОЕ ПОДТВЕРЖДЕНИЕ ===

async def show_final_confirmation(message: Message, state: FSMContext):
    """Показать финальное подтверждение перед анализом"""
    data = await state.get_data()
    
    initial_symptoms = data.get("initial_symptoms", [])
    duration = data.get("duration", "не указана")
    additional_symptoms = data.get("additional_symptoms", [])
    
    # Форматируем анамнез
    anamnesis = f"""📋 <b>Итоговая анкета:</b>

<b>Основные симптомы:</b>
• {chr(10).join(['• ' + s for s in initial_symptoms])}

<b>Давность:</b> {duration}

<b>Дополнительные симптомы:</b>
{chr(10).join(['• ' + s for s in additional_symptoms]) if additional_symptoms else '• Нет дополнительных симптомов'}

Всё верно? Можем переходить к рекомендации врача."""
    
    await message.answer(
        anamnesis,
        reply_markup=final_confirmation_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(ConsultationStates.final_confirmation)


@router.message(ConsultationStates.final_confirmation, F.text == "✅ Подтвердить")
async def final_confirm_and_analyze(message: Message, state: FSMContext):
    """Финальное подтверждение - анализ и рекомендация"""
    await message.answer("🔍 Формирую рекомендацию специалиста...", reply_markup=main_menu_keyboard())
    
    data = await state.get_data()
    profile = await db.get_user_profile(message.from_user.id)
    
    # Получаем рекомендацию от AI
    result = await ai_service.recommend_doctor(
        initial_symptoms=data["initial_symptoms"],
        duration=data["duration"],
        additional_symptoms=data["additional_symptoms"],
        user_profile=profile
    )
    
    # Сохраняем в БД
    await db.create_consultation(
        user_id=message.from_user.id,
        symptoms=data["initial_symptoms"] + data["additional_symptoms"],
        questions_answers=[{"duration": data["duration"]}],
        recommended_doctor=result["doctor"],
        urgency_level=result["urgency"]
    )
    
    # Показываем результат
    urgency_emoji = {
        "low": "🟢",
        "medium": "🟡",
        "high": "🟠",
        "emergency": "🔴"
    }
    
    urgency_text = {
        "low": "Низкая - плановый визит",
        "medium": "Средняя - запишитесь в ближайшее время",
        "high": "Высокая - обратитесь как можно скорее",
        "emergency": "ЭКСТРЕННАЯ - немедленно вызовите скорую помощь!"
    }
    
    # Форматируем анамнез для результата
    all_symptoms = data["initial_symptoms"] + data["additional_symptoms"]
    
    recommendation_text = f"""✅ <b>Анализ завершён</b>

👨‍⚕️ <b>Рекомендуемый специалист:</b>
{result['doctor']}

{urgency_emoji.get(result['urgency'], '⚪')} <b>Срочность:</b>
{urgency_text.get(result['urgency'], 'Не определена')}

📋 <b>На основе:</b>
• Симптомы: {', '.join(all_symptoms)}
• Давность: {data['duration']}

💡 <b>Обоснование:</b>
{result['reasoning']}

<b>⚠️ ВАЖНО:</b>
Это рекомендация на основе ваших симптомов. Окончательный диагноз может поставить только врач после осмотра."""
    
    await message.answer(
        recommendation_text,
        reply_markup=consultation_result_keyboard(),
        parse_mode="HTML"
    )
    await state.clear()


@router.message(ConsultationStates.final_confirmation, F.text == "✏️ Добавить симптомы")
async def add_more_symptoms_from_final(message: Message, state: FSMContext):
    """Добавить больше симптомов с финального подтверждения"""
    data = await state.get_data()
    suggested = data.get("ai_suggested_symptoms", [])
    selected = data.get("additional_symptoms", [])
    
    await message.answer(
        "❓ <b>Выберите дополнительные симптомы (если есть):</b>\n\n"
        "Нажимайте на симптомы которые у вас есть. "
        "Когда закончите - нажмите <b>✅ Готово</b>",
        reply_markup=additional_symptoms_keyboard(suggested, selected),
        parse_mode="HTML"
    )
    await state.set_state(ConsultationStates.selecting_additional_symptoms)


@router.message(ConsultationStates.final_confirmation, F.text == "🔄 Начать заново")
async def restart_consultation(message: Message, state: FSMContext):
    """Начать консультацию заново"""
    await start_consultation(message, state)


# === РЕЗУЛЬТАТ ===

@router.callback_query(F.data == "book_appointment")
async def book_appointment(callback: CallbackQuery):
    """Запись на консультацию (в разработке)"""
    await callback.answer(
        "📅 Функционал записи на консультацию находится в разработке.",
        show_alert=True
    )


# === ИСТОРИЯ КОНСУЛЬТАЦИЙ ===

@router.message(F.text == "📋 Мои консультации")
@router.callback_query(F.data == "view_history")
async def view_consultations(event: Message | CallbackQuery):
    """Просмотр истории консультаций"""
    if isinstance(event, CallbackQuery):
        message = event.message
        user_id = message.chat.id
        await event.answer()
    else:
        message = event
        user_id = event.from_user.id
    
    consultations = await db.get_user_consultations(user_id, limit=10)
    
    if not consultations:
        await message.answer(
            "📋 У вас пока нет консультаций.\n\n"
            "Начните новую консультацию, чтобы получить рекомендацию врача.",
            reply_markup=main_menu_keyboard()
        )
        return
    
    history_text = "📋 <b>Ваши последние консультации:</b>\n\n"
    
    for i, cons in enumerate(consultations[:5], 1):
        import json
        from datetime import datetime
        
        symptoms = json.loads(cons["symptoms"])
        created_at = datetime.fromisoformat(cons["created_at"])
        
        urgency_emoji = {
            "low": "🟢",
            "medium": "🟡",
            "high": "🟠",
            "emergency": "🔴"
        }
        
        history_text += f"{i}. <b>{cons['recommended_doctor']}</b> {urgency_emoji.get(cons['urgency_level'], '⚪')}\n"
        history_text += f"   📅 {created_at.strftime('%d.%m.%Y %H:%M')}\n"
        history_text += f"   📋 Симптомы: {', '.join(symptoms[:3])}{'...' if len(symptoms) > 3 else ''}\n\n"
    
    await message.answer(history_text, parse_mode="HTML", reply_markup=main_menu_keyboard())


# === ОТМЕНА ===

@router.message(F.text == "❌ Отменить")
@router.callback_query(F.data == "cancel_consultation")
async def cancel_consultation(event: Message | CallbackQuery, state: FSMContext):
    """Отменить консультацию"""
    await state.clear()
    
    if isinstance(event, CallbackQuery):
        await event.message.answer(
            "❌ Консультация отменена.",
            reply_markup=main_menu_keyboard()
        )
        await event.answer()
    else:
        await event.answer(
            "❌ Консультация отменена.",
            reply_markup=main_menu_keyboard()
        )
