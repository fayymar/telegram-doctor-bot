from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from bot.states import Consultation
from bot.keyboards import (
    get_main_menu,
    get_symptoms_confirmation,
    get_duration_keyboard,
    get_additional_symptoms_keyboard,
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
            
            # Вычисляем возраст
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
    # Проверяем регистрацию
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
    
    # Очищаем предыдущие данные
    await state.clear()
    
    await message.answer(
        "🩺 *Новая консультация*\n\n"
        "📝 *Этап 1 из 4*\n\n"
        "Опишите ваши симптомы максимально подробно.\n"
        "Что вас беспокоит? Какие ощущения?\n\n"
        "💡 Вы можете отправить текст или голосовое сообщение.\n\n"
        "❌ Для отмены используйте /cancel",
        parse_mode="Markdown"
    )
    
    await state.set_state(Consultation.waiting_for_symptoms)


# ============ ЭТАП 1: ОПИСАНИЕ СИМПТОМОВ ============

@router.message(Consultation.waiting_for_symptoms, F.text)
async def process_symptoms_text(message: Message, state: FSMContext):
    """Обработка текстового описания симптомов"""
    
    symptoms_text = message.text.strip()
    
    # ВАЛИДАЦИЯ: Проверяем, что это действительно симптомы
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
    
    # Используем очищенные симптомы от AI
    clean_symptoms = validation['symptoms'] if validation['symptoms'] else symptoms_text
    
    await state.update_data(main_symptoms=clean_symptoms)
    
    await message.answer(
        f"📝 *Ваши симптомы:*\n\n"
        f"{clean_symptoms}\n\n"
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

@router.callback_query(Consultation.confirming_symptoms, F.data == "confirm_symptoms")
async def confirm_symptoms(callback: CallbackQuery, state: FSMContext):
    """Подтверждение симптомов"""
    await callback.message.edit_text(
        "✅ Симптомы подтверждены"
    )
    
    await callback.message.answer(
        "📅 *Этап 2 из 4*\n\n"
        "Как давно вас беспокоят эти симптомы?",
        reply_markup=get_duration_keyboard(),
        parse_mode="Markdown"
    )
    
    await state.set_state(Consultation.waiting_for_duration)
    await callback.answer()


@router.callback_query(Consultation.confirming_symptoms, F.data == "add_symptoms")
async def add_more_symptoms(callback: CallbackQuery, state: FSMContext):
    """Добавление дополнительных деталей"""
    await callback.message.edit_text(
        "📝 Добавьте дополнительные детали к описанию симптомов:"
    )
    
    await state.set_state(Consultation.waiting_for_symptoms)
    await callback.answer()


@router.callback_query(Consultation.confirming_symptoms, F.data == "restart_symptoms")
async def restart_symptoms(callback: CallbackQuery, state: FSMContext):
    """Начать описание заново"""
    await callback.message.edit_text(
        "🔄 Начинаем заново\n\n"
        "Опишите ваши симптомы:"
    )
    
    await state.set_state(Consultation.waiting_for_symptoms)
    await callback.answer()


# ============ ЭТАП 2: ДАВНОСТЬ СИМПТОМОВ ============

@router.callback_query(Consultation.waiting_for_duration, F.data.startswith("duration_"))
async def process_duration(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора давности"""
    duration_map = {
        "24h": "Меньше 24 часов",
        "1-3d": "1-3 дня",
        "3-7d": "3-7 дней",
        "week+": "Больше недели"
    }
    
    duration_key = callback.data.split("_")[1]
    duration_text = duration_map.get(duration_key, "не указано")
    
    await state.update_data(duration=duration_text)
    
    await callback.message.edit_text(
        f"📅 Давность: {duration_text}"
    )
    
    # Генерируем дополнительные симптомы через AI
    await callback.message.answer("⏳ Анализирую симптомы...")
    
    data = await state.get_data()
    main_symptoms = data.get('main_symptoms', '')
    
    additional_symptoms = ai_service.generate_additional_symptoms(
        main_symptoms=main_symptoms,
        duration=duration_text
    )
    
    if not additional_symptoms:
        # Если AI не смог сгенерировать, переходим к финалу
        await callback.message.answer(
            "❌ Не удалось сгенерировать дополнительные вопросы\n"
            "Переходим к финальному этапу..."
        )
        await show_final_confirmation(callback.message, state)
        await callback.answer()
        return
    
    await state.update_data(
        additional_symptoms_options=additional_symptoms,
        selected_additional=set()
    )
    
    await callback.message.answer(
        "📋 *Этап 3 из 4*\n\n"
        "Отметьте, что ещё вас беспокоит:\n"
        "(выберите все подходящие варианты)",
        reply_markup=get_additional_symptoms_keyboard(additional_symptoms),
        parse_mode="Markdown"
    )
    
    await state.set_state(Consultation.selecting_additional_symptoms)
    await callback.answer()


# ============ ЭТАП 3: ДОПОЛНИТЕЛЬНЫЕ СИМПТОМЫ ============

@router.callback_query(Consultation.selecting_additional_symptoms, F.data.startswith("symptom_"))
async def toggle_symptom(callback: CallbackQuery, state: FSMContext):
    """Переключение выбора симптома"""
    # Извлекаем название симптома из текста кнопки
    symptom = callback.data.replace("symptom_", "")
    
    # Находим полное название из опций
    data = await state.get_data()
    options = data.get('additional_symptoms_options', [])
    selected = data.get('selected_additional', set())
    
    # Ищем полное совпадение
    full_symptom = None
    for opt in options:
        if opt.startswith(symptom) or symptom in opt:
            full_symptom = opt
            break
    
    if not full_symptom:
        await callback.answer("Ошибка выбора")
        return
    
    # Переключаем выбор
    if full_symptom in selected:
        selected.remove(full_symptom)
    else:
        selected.add(full_symptom)
    
    await state.update_data(selected_additional=selected)
    
    # Обновляем клавиатуру
    updated_keyboard = update_symptom_selection(
        callback.message.reply_markup,
        selected
    )
    
    await callback.message.edit_reply_markup(reply_markup=updated_keyboard)
    await callback.answer()


@router.callback_query(Consultation.selecting_additional_symptoms, F.data == "no_additional")
async def no_additional_symptoms(callback: CallbackQuery, state: FSMContext):
    """Нет дополнительных симптомов"""
    await state.update_data(selected_additional=set())
    
    await callback.message.edit_text(
        "✅ Дополнительных симптомов нет"
    )
    
    await show_final_confirmation(callback.message, state)
    await callback.answer()


@router.callback_query(Consultation.selecting_additional_symptoms, F.data == "other_symptom")
async def other_symptom(callback: CallbackQuery, state: FSMContext):
    """Описать другой симптом"""
    await callback.message.edit_text(
        "✏️ Опишите дополнительный симптом:"
    )
    
    await state.set_state(Consultation.waiting_for_other_symptoms)
    await callback.answer()


@router.message(Consultation.waiting_for_other_symptoms)
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
    
    # Добавляем к выбранным
    data = await state.get_data()
    selected = data.get('selected_additional', set())
    selected.add(validation['symptoms'] if validation['symptoms'] else other_symptom)
    
    await state.update_data(selected_additional=selected)
    
    # Возвращаемся к выбору
    options = data.get('additional_symptoms_options', [])
    
    await message.answer(
        "✅ Симптом добавлен\n\n"
        "Выберите ещё или нажмите 'Готово':",
        reply_markup=get_additional_symptoms_keyboard(options)
    )
    
    await state.set_state(Consultation.selecting_additional_symptoms)


@router.callback_query(Consultation.selecting_additional_symptoms, F.data == "done_additional")
async def done_additional_symptoms(callback: CallbackQuery, state: FSMContext):
    """Завершение выбора дополнительных симптомов"""
    data = await state.get_data()
    selected = data.get('selected_additional', set())
    
    if selected:
        symptoms_list = "\n".join([f"• {s}" for s in selected])
        await callback.message.edit_text(
            f"✅ *Дополнительные симптомы:*\n\n{symptoms_list}",
            parse_mode="Markdown"
        )
    else:
        await callback.message.edit_text("✅ Дополнительных симптомов не выбрано")
    
    await show_final_confirmation(callback.message, state)
    await callback.answer()


# ============ ЭТАП 4: ФИНАЛЬНОЕ ПОДТВЕРЖДЕНИЕ ============

async def show_final_confirmation(message: Message, state: FSMContext):
    """Показывает финальное подтверждение с полным анамнезом"""
    data = await state.get_data()
    
    main_symptoms = data.get('main_symptoms', 'не указано')
    duration = data.get('duration', 'не указано')
    additional = data.get('selected_additional', set())
    
    # Формируем текст анамнеза
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


@router.callback_query(Consultation.final_confirmation, F.data == "final_confirm")
async def final_confirm(callback: CallbackQuery, state: FSMContext):
    """Финальное подтверждение и получение рекомендации"""
    await callback.message.edit_text("✅ Данные подтверждены")
    
    await callback.message.answer("⏳ Анализирую симптомы и подбираю специалиста...")
    
    # Получаем данные
    data = await state.get_data()
    user_profile = await get_user_profile(callback.from_user.id)
    
    # Получаем рекомендацию от AI
    recommendation = ai_service.recommend_doctor(
        main_symptoms=data.get('main_symptoms', ''),
        duration=data.get('duration', ''),
        additional_symptoms=list(data.get('selected_additional', set())),
        user_profile=user_profile
    )
    
    # Сохраняем консультацию
    await save_consultation(callback.from_user.id, {
        'symptoms': {
            'main': data.get('main_symptoms'),
            'duration': data.get('duration'),
            'additional': list(data.get('selected_additional', set()))
        },
        'questions_answers': {},
        'specialist': recommendation['specialist'],
        'urgency': recommendation['urgency']
    })
    
    # Формируем ответ
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
    
    await callback.message.answer(
        result_text,
        reply_markup=get_result_keyboard(),
        parse_mode="Markdown"
    )
    
    await state.clear()
    await callback.answer()


@router.callback_query(Consultation.final_confirmation, F.data == "add_more_symptoms")
async def add_more_from_final(callback: CallbackQuery, state: FSMContext):
    """Добавить симптомы с финального этапа"""
    await callback.message.edit_text("✏️ Опишите дополнительные симптомы:")
    
    await state.set_state(Consultation.waiting_for_other_symptoms)
    await callback.answer()


@router.callback_query(Consultation.final_confirmation, F.data == "restart_consultation")
async def restart_consultation(callback: CallbackQuery, state: FSMContext):
    """Начать консультацию заново"""
    await callback.message.delete()
    await state.clear()
    
    fake_message = callback.message
    fake_message.text = "🩺 Новая консультация"
    
    await start_consultation(fake_message, state)
    await callback.answer()


# ============ ДЕЙСТВИЯ ПОСЛЕ РЕЗУЛЬТАТА ============

@router.callback_query(F.data == "new_consultation")
async def new_consultation_callback(callback: CallbackQuery, state: FSMContext):
    """Новая консультация из результата"""
    await callback.message.delete()
    await state.clear()
    
    fake_message = callback.message
    fake_message.text = "🩺 Новая консультация"
    
    await start_consultation(fake_message, state)
    await callback.answer()


@router.callback_query(F.data == "book_appointment")
async def book_appointment(callback: CallbackQuery):
    """Заглушка для записи к врачу"""
    await callback.answer(
        "📝 Функция записи к врачу находится в разработке",
        show_alert=True
    )


# ============ ОТМЕНА КОНСУЛЬТАЦИИ ============

@router.callback_query(F.data == "cancel_consultation")
async def cancel_consultation_callback(callback: CallbackQuery, state: FSMContext):
    """Отмена консультации"""
    await state.clear()
    await callback.message.edit_text("❌ Консультация отменена")
    await callback.message.answer(
        "Главное меню",
        reply_markup=get_main_menu()
    )
    await callback.answer()


@router.message(F.text == "/cancel")
async def cancel_consultation_command(message: Message, state: FSMContext):
    """Отмена через команду"""
    await state.clear()
    await message.answer(
        "❌ Консультация отменена",
        reply_markup=get_main_menu()
    )
