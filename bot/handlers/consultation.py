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
from database.connection import supabase_client


router = Router()
ai_service = AIService()


# ============ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ============

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
        print(f"DB Error: {e}")
    
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
        print(f"DB Error: {e}")


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
        print(f"DB Error: {e}")
    
    await state.clear()
    
    await message.answer(
        "🩺 *Новая консультация*\n\n"
        "📝 *Этап 1 из 4*\n\n"
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
    
    await message.answer(
        f"📝 *Ваши симптомы:*\n\n"
        f"{improved_symptoms}\n\n"
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
    
    # ОТДЕЛЬНОЕ сообщение для вопроса о давности
    await message.answer(
        "📅 *Этап 2 из 4*\n\n"
        "Как давно вас беспокоят эти симптомы?",
        reply_markup=get_duration_keyboard(),
        parse_mode="Markdown"
    )
    
    await state.set_state(Consultation.waiting_for_duration)


@router.message(Consultation.confirming_symptoms, F.text == "🔄 Начать заново")
async def restart_symptoms(message: Message, state: FSMContext):
    """Начать описание заново"""
    await message.answer(
        "🔄 Начинаем заново\n\n"
        "Опишите ваши симптомы:",
        reply_markup=get_symptoms_input_keyboard()
    )
    
    await state.set_state(Consultation.waiting_for_symptoms)


# ============ ЭТАП 2: ДАВНОСТЬ СИМПТОМОВ ============

@router.message(Consultation.waiting_for_duration, F.text == "🔙 Назад")
async def back_from_duration(message: Message, state: FSMContext):
    """Возврат с этапа давности к подтверждению симптомов"""
    data = await state.get_data()
    main_symptoms = data.get('main_symptoms', '')
    
    await message.answer(
        f"📝 *Ваши симптомы:*\n\n"
        f"{main_symptoms}\n\n"
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
    
    await message.answer(f"📅 Давность: {duration_text}")
    
    # Генерируем дополнительные симптомы через AI
    await message.answer("⏳ Анализирую симптомы...")
    
    data = await state.get_data()
    main_symptoms = data.get('main_symptoms', '')
    
    additional_symptoms = ai_service.generate_additional_symptoms(
        main_symptoms=main_symptoms,
        duration=duration_text
    )
    
    # ЛОГИРОВАНИЕ для отладки
    print(f"DEBUG: Generated {len(additional_symptoms)} symptoms: {additional_symptoms}")
    
    # Если AI не сгенерировал симптомы - предлагаем написать вручную
    if not additional_symptoms:
        print("DEBUG: No symptoms generated by AI, asking user to write manually")
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
        "📋 *Этап 3 из 4*\n\n"
        "Отметьте, что ещё вас беспокоит:\n"
        "(выберите все подходящие варианты)",
        reply_markup=get_additional_cancel_keyboard(),
        parse_mode="Markdown"
    )
    
    # Формируем клавиатуру
    keyboard = get_additional_symptoms_keyboard(additional_symptoms)
    print(f"DEBUG: Keyboard has {len(keyboard.inline_keyboard)} rows")
    
    # ВАЖНО: Второе сообщение с инлайн-кнопками!
    await message.answer(
        "Выберите симптомы:",
        reply_markup=keyboard
    )
    
    await state.set_state(Consultation.selecting_additional_symptoms)


# ============ ЭТАП 3: ДОПОЛНИТЕЛЬНЫЕ СИМПТОМЫ ============

@router.message(Consultation.selecting_additional_symptoms, F.text == "🔙 Назад")
async def back_from_additional(message: Message, state: FSMContext):
    """Возврат с этапа дополнительных симптомов к выбору давности"""
    await message.answer(
        "📅 *Этап 2 из 4*\n\n"
        "Как давно вас беспокоят эти симптомы?",
        reply_markup=get_duration_keyboard(),
        parse_mode="Markdown"
    )
    
    await state.set_state(Consultation.waiting_for_duration)


@router.callback_query(Consultation.selecting_additional_symptoms, F.data.startswith("sym_"))
async def toggle_symptom(callback: CallbackQuery, state: FSMContext):
    """Переключение выбора симптома"""
    print(f"DEBUG: Callback received: {callback.data}")
    
    try:
        # Извлекаем индекс из callback_data
        idx = int(callback.data.split("_")[1])
        print(f"DEBUG: Symptom index: {idx}")
        
        data = await state.get_data()
        options = data.get('additional_symptoms_options', [])
        selected = data.get('selected_additional', set())
        
        print(f"DEBUG: Total options: {len(options)}, Selected: {len(selected)}")
        
        # Получаем симптом по индексу
        if idx >= len(options):
            print(f"DEBUG ERROR: Index {idx} out of range (max {len(options)-1})")
            await callback.answer("❌ Ошибка выбора", show_alert=True)
            return
        
        symptom = options[idx]
        print(f"DEBUG: Toggling symptom: {symptom}")
        
        # Переключаем выбор
        if symptom in selected:
            selected.remove(symptom)
            print(f"DEBUG: Removed symptom, now {len(selected)} selected")
        else:
            selected.add(symptom)
            print(f"DEBUG: Added symptom, now {len(selected)} selected")
        
        await state.update_data(selected_additional=selected)
        
        # Обновляем клавиатуру
        updated_keyboard = update_symptom_selection(
            callback.message.reply_markup,
            selected,
            options  # Передаём полный список
        )
        
        print(f"DEBUG: Updating keyboard with {len(updated_keyboard.inline_keyboard)} rows")
        
        await callback.message.edit_reply_markup(reply_markup=updated_keyboard)
        await callback.answer()  # Убираем часики
        
    except Exception as e:
        print(f"DEBUG ERROR: Exception in toggle_symptom: {e}")
        import traceback
        traceback.print_exc()
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
            "Выберите симптомы:",
            reply_markup=get_additional_symptoms_keyboard(options)
        )
        await state.set_state(Consultation.selecting_additional_symptoms)
    else:
        # Если опций нет - возвращаемся к выбору давности
        await message.answer(
            "📅 *Этап 2 из 4*\n\n"
            "Как давно вас беспокоят эти симптомы?",
            reply_markup=get_duration_keyboard(),
            parse_mode="Markdown"
        )
        await state.set_state(Consultation.waiting_for_duration)


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
    
    await show_final_confirmation(callback.message, state)
    await callback.answer()


# ============ ЭТАП 4: ФИНАЛЬНОЕ ПОДТВЕРЖДЕНИЕ ============

async def show_final_confirmation(message: Message, state: FSMContext):
    """Показывает финальное подтверждение с полным анамнезом"""
    data = await state.get_data()
    
    main_symptoms = data.get('main_symptoms', 'не указано')
    duration = data.get('duration', 'не указано')
    additional = data.get('selected_additional', set())
    
    anamnesis = f"📋 *Финальное подтверждение*\n\n"
    anamnesis += f"*Основные симптомы:*\n{main_symptoms}\n\n"
    anamnesis += f"*Давность:* {duration}\n\n"
    
    if additional:
        anamnesis += "*Дополнительные симптомы:*\n"
        for symptom in additional:
            anamnesis += f"• {symptom}\n"
    else:
        anamnesis += "*Дополнительные симптомы:* нет\n"
    
    anamnesis += "\n✅ Всё верно?"
    
    await message.answer(
        anamnesis,
        reply_markup=get_final_confirmation(),
        parse_mode="Markdown"
    )
    
    await state.set_state(Consultation.final_confirmation)


@router.message(Consultation.final_confirmation, F.text == "✅ Подтвердить")
async def final_confirm(message: Message, state: FSMContext):
    """Финальное подтверждение и получение рекомендации"""
    await message.answer("✅ Данные подтверждены")
    
    await message.answer("⏳ Анализирую симптомы и подбираю специалиста...")
    
    data = await state.get_data()
    user_profile = await get_user_profile(message.from_user.id)
    
    recommendation = ai_service.recommend_doctor(
        main_symptoms=data.get('main_symptoms', ''),
        duration=data.get('duration', ''),
        additional_symptoms=list(data.get('selected_additional', set())),
        user_profile=user_profile
    )
    
    await save_consultation(message.from_user.id, {
        'symptoms': {
            'main': data.get('main_symptoms'),
            'duration': data.get('duration'),
            'additional': list(data.get('selected_additional', set()))
        },
        'questions_answers': {},
        'specialist': recommendation['specialist'],
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
    
    result_text = f"🩺 *Рекомендация специалиста*\n\n"
    result_text += f"*Специалист:* {recommendation['specialist']}\n\n"
    result_text += f"{urgency_emoji.get(recommendation['urgency'], '📋')} *Срочность:* "
    result_text += f"{urgency_text.get(recommendation['urgency'], 'Средняя')}\n\n"
    result_text += f"*Обоснование:*\n{recommendation['reasoning']}"
    
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
