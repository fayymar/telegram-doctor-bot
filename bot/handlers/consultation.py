from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from bot.keyboards import main_menu_keyboard, cancel_keyboard, consultation_result_keyboard
from bot.states import ConsultationStates
from database.connection import db
from services.ai_service import ai_service

router = Router()


@router.message(F.text == "🩺 Новая консультация")
@router.callback_query(F.data == "new_consultation")
async def start_consultation(event: Message | CallbackQuery, state: FSMContext):
    """Начать новую консультацию"""
    # Определяем тип события
    if isinstance(event, CallbackQuery):
        message = event.message
        await event.answer()
    else:
        message = event
    
    user_id = message.chat.id if isinstance(event, CallbackQuery) else event.from_user.id
    
    # Проверяем профиль
    profile = await db.get_user_profile(user_id)
    if not profile:
        await message.answer("❌ Сначала завершите регистрацию через /start")
        return
    
    # Инициализируем данные консультации
    await state.update_data(
        symptoms=[],
        qa_history=[],
        current_question=None
    )
    
    await message.answer(
        "🩺 <b>Начинаем консультацию</b>\n\n"
        "Опишите ваши симптомы текстом или голосовым сообщением.\n"
        "Можете указать несколько симптомов сразу.\n\n"
        "<i>Например: \"болит голова и тошнит\" или \"температура 38 и кашель\"</i>",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(ConsultationStates.waiting_for_symptoms)


@router.message(ConsultationStates.waiting_for_symptoms)
async def process_symptoms(message: Message, state: FSMContext):
    """Обработка симптомов"""
    # Получаем текст (из текстового или голосового сообщения)
    if message.text:
        symptoms_text = message.text
    elif message.voice:
        await message.answer("🎤 Обработка голосового сообщения временно недоступна. Пожалуйста, напишите симптомы текстом.")
        return
    else:
        await message.answer("⚠️ Пожалуйста, опишите симптомы текстом или голосовым сообщением.")
        return
    
    # Сохраняем симптомы
    data = await state.get_data()
    symptoms = data.get("symptoms", [])
    symptoms.append(symptoms_text)
    await state.update_data(symptoms=symptoms)
    
    # Отправляем на анализ AI
    await message.answer("🔍 Анализирую ваши симптомы...")
    
    profile = await db.get_user_profile(message.from_user.id)
    qa_history = data.get("qa_history", [])
    
    result = await ai_service.analyze_symptoms(
        symptoms=symptoms,
        qa_history=qa_history,
        user_profile=profile
    )
    
    if result["action"] == "ask_question":
        # AI хочет задать уточняющий вопрос
        await state.update_data(current_question=result["question"])
        await message.answer(
            f"❓ <b>Уточняющий вопрос:</b>\n\n{result['question']}",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML"
        )
        await state.set_state(ConsultationStates.waiting_for_answer)
        
    elif result["action"] == "recommend_doctor":
        # AI готов рекомендовать врача
        await show_recommendation(message, state, result, profile)


@router.message(ConsultationStates.waiting_for_answer)
async def process_answer(message: Message, state: FSMContext):
    """Обработка ответа на уточняющий вопрос"""
    if not message.text:
        await message.answer("⚠️ Пожалуйста, ответьте текстом.")
        return
    
    data = await state.get_data()
    qa_history = data.get("qa_history", [])
    current_question = data.get("current_question")
    
    # Сохраняем вопрос-ответ
    qa_history.append({
        "question": current_question,
        "answer": message.text
    })
    await state.update_data(qa_history=qa_history)
    
    # Снова анализируем
    await message.answer("🔍 Обрабатываю ответ...")
    
    profile = await db.get_user_profile(message.from_user.id)
    symptoms = data.get("symptoms", [])
    
    result = await ai_service.analyze_symptoms(
        symptoms=symptoms,
        qa_history=qa_history,
        user_profile=profile
    )
    
    if result["action"] == "ask_question":
        # Ещё один вопрос
        await state.update_data(current_question=result["question"])
        await message.answer(
            f"❓ <b>Уточняющий вопрос:</b>\n\n{result['question']}",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML"
        )
        # Остаёмся в том же состоянии
        
    elif result["action"] == "recommend_doctor":
        # Готова рекомендация
        await show_recommendation(message, state, result, profile)


async def show_recommendation(message: Message, state: FSMContext, result: dict, profile: dict):
    """Показать рекомендацию врача"""
    data = await state.get_data()
    symptoms = data.get("symptoms", [])
    qa_history = data.get("qa_history", [])
    
    # Сохраняем консультацию в БД
    await db.create_consultation(
        user_id=message.from_user.id,
        symptoms=symptoms,
        questions_answers=qa_history,
        recommended_doctor=result["doctor"],
        urgency_level=result["urgency"]
    )
    
    # Формируем сообщение с рекомендацией
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
    
    recommendation_text = f"""
✅ <b>Анализ завершён</b>

👨‍⚕️ <b>Рекомендуемый специалист:</b>
{result['doctor']}

{urgency_emoji.get(result['urgency'], '⚪')} <b>Срочность:</b>
{urgency_text.get(result['urgency'], 'Не определена')}

💡 <b>Обоснование:</b>
{result['reasoning']}

<b>⚠️ ВАЖНО:</b>
Это рекомендация на основе ваших симптомов. Окончательный диагноз может поставить только врач после осмотра.
"""
    
    await message.answer(
        recommendation_text,
        reply_markup=consultation_result_keyboard(),
        parse_mode="HTML"
    )
    
    await state.clear()


# === История консультаций ===

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
        history_text += f"   Симптомы: {symptoms[0][:50]}...\n"
        history_text += f"   Дата: {created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
    
    await message.answer(history_text, parse_mode="HTML", reply_markup=main_menu_keyboard())
