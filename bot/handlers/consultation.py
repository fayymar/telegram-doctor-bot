import json
from datetime import datetime

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext

from bot.states import Consultation
from bot.keyboards import get_main_menu, get_cancel_keyboard
from services.consultation_agent import (
    check_red_flags,
    parse_and_generate_questions,
    get_duration_question,
    get_anamnesis_questions,
    get_final_recommendation,
    get_patient_history,
)
from database.connection import supabase_client
from utils.logger import setup_logger

logger = setup_logger(__name__)
router = Router()


def _make_question_keyboard(options: list) -> InlineKeyboardMarkup:
    """Каждая кнопка на отдельной строке — текст не обрезается."""
    builder = InlineKeyboardBuilder()
    for i, opt in enumerate(options):
        builder.row(InlineKeyboardButton(text=opt, callback_data=f"ans:{i}"))
    builder.row(InlineKeyboardButton(text="✏️ Написать своё", callback_data="ans:custom"))
    return builder.as_markup()


def _make_duration_keyboard(options: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for i, opt in enumerate(options):
        builder.row(InlineKeyboardButton(text=opt, callback_data=f"dur:{i}"))
    return builder.as_markup()


def _is_duration_question(question_text: str) -> bool:
    """Возвращает True если вопрос касается давности симптомов (чтобы не дублировать)."""
    keywords = ["давн", "как долго", "когда появ", "сколько дней", "сколько времени", "как давно"]
    text = question_text.lower()
    return any(k in text for k in keywords)


async def _save_consultation(user_id: int, all_data: dict, result: dict):
    try:
        specialists = result.get("specialists", [])
        top = specialists[0] if specialists else {}
        history = (
            [{"question": None, "answer": all_data.get("symptoms", "")}]
            + all_data.get("followup_answers", [])
            + [{"question": "Как давно появились симптомы?", "answer": all_data.get("duration", "")}]
            + all_data.get("anamnesis_answers", [])
        )
        supabase_client.table("consultations").insert({
            "user_id": user_id,
            "symptoms": json.dumps({"history": history}, ensure_ascii=False),
            "questions_answers": json.dumps(history, ensure_ascii=False),
            "recommended_doctor": top.get("name", "Терапевт"),
            "urgency_level": result.get("urgency", "medium"),
            "created_at": datetime.now().isoformat(),
        }).execute()
    except Exception as e:
        logger.error(f"DB error in _save_consultation: {e}", exc_info=True)


def _format_result(result: dict, duration: str) -> str:
    specialists = result.get("specialists", [])
    medals = ["🥇", "🥈", "🥉"]
    lines = ["🏥 <b>Рекомендуемые специалисты:</b>"]
    for i, spec in enumerate(specialists[:3]):
        medal = medals[i] if i < len(medals) else "•"
        name = spec.get("name", "")
        pct = spec.get("match_percent", 0)
        reason = spec.get("reason", "")
        lines.append(f"{medal} <b>{name}</b> — {pct}%")
        if reason:
            lines.append(f"   {reason}")
    lines.append("────────────────")
    lines.append(f"📅 Давность: {duration}")
    lines.append("⚠️ Это не диагноз. Обратитесь к врачу для точного обследования.")
    return "\n".join(lines)


# ============ ХЕНДЛЕРЫ ============

@router.message(F.text == "🩺 Новая консультация")
async def start_consultation(message: Message, state: FSMContext):
    try:
        response = supabase_client.table("users").select("telegram_id").eq(
            "telegram_id", message.from_user.id
        ).execute()
        if not response.data:
            await message.answer(
                "❌ Пожалуйста, сначала зарегистрируйтесь\nИспользуйте /start"
            )
            return
    except Exception as e:
        logger.error(f"DB error in start_consultation: {e}", exc_info=True)

    await state.clear()
    await state.set_state(Consultation.waiting_for_symptoms)
    await state.update_data(user_id=message.from_user.id)

    await message.answer(
        "🩺 <b>Новая консультация</b>\n\n"
        "Опишите ваши симптомы — что вас беспокоит?\n\n"
        "💡 Чем подробнее опишете, тем точнее будет рекомендация.",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML",
    )


@router.message(Consultation.waiting_for_symptoms, F.text == "❌ Отменить")
@router.message(Consultation.answering_followup, F.text == "❌ Отменить")
@router.message(Consultation.waiting_for_duration, F.text == "❌ Отменить")
@router.message(Consultation.answering_anamnesis, F.text == "❌ Отменить")
async def cancel_consultation(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Консультация отменена", reply_markup=get_main_menu())


@router.message(Consultation.waiting_for_symptoms, F.text)
async def process_symptoms(message: Message, state: FSMContext):
    symptoms_text = message.text.strip()
    if not symptoms_text:
        return

    analyzing_msg = await message.answer("⏳ Анализирую симптомы...")

    # Шаг 1: Красные флаги
    red = check_red_flags(symptoms_text)
    if red.get("red_flag"):
        await analyzing_msg.delete()
        await state.clear()
        await message.answer(
            "🚨 <b>Немедленно вызовите скорую помощь!</b>\n\n"
            "Ваши симптомы требуют экстренной медицинской помощи.",
            reply_markup=get_main_menu(),
            parse_mode="HTML",
        )
        return

    # Получаем профиль пользователя
    user_profile = {}
    try:
        resp = supabase_client.table("users").select("*").eq(
            "telegram_id", message.from_user.id
        ).execute()
        if resp.data:
            user_profile = resp.data[0]
    except Exception as e:
        logger.error(f"DB error getting profile: {e}", exc_info=True)

    # Получаем историю предыдущих консультаций
    patient_history = get_patient_history(message.from_user.id, supabase_client)

    # Шаг 2: Генерируем уточняющие вопросы (фильтруем вопросы о давности — они задаются отдельно)
    questions = parse_and_generate_questions(symptoms_text, user_profile, patient_history)
    questions = [q for q in questions if not _is_duration_question(q.get("question", ""))]

    await analyzing_msg.delete()

    await state.update_data(
        symptoms=symptoms_text,
        user_profile=user_profile,
        patient_history=patient_history,
        followup_questions=questions,
        followup_index=0,
        followup_answers=[],
        waiting_custom=False,
    )

    if questions:
        await state.set_state(Consultation.answering_followup)
        q = questions[0]
        await message.answer(
            f"❓ {q['question']}",
            reply_markup=_make_question_keyboard(q["options"]),
            parse_mode="HTML",
        )
    else:
        # Нет followup-вопросов — сразу к давности
        duration_q = get_duration_question()
        await state.set_state(Consultation.waiting_for_duration)
        await message.answer(
            f"❓ {duration_q['question']}",
            reply_markup=_make_duration_keyboard(duration_q["options"]),
            parse_mode="HTML",
        )


@router.callback_query(Consultation.answering_followup, F.data.startswith("ans:"))
async def process_followup_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()

    questions = data.get("followup_questions", [])
    index = data.get("followup_index", 0)
    answers = data.get("followup_answers", [])
    suffix = callback.data.split(":", 1)[1]

    if suffix == "custom":
        await state.update_data(waiting_custom=True)
        await callback.message.answer("✏️ Напишите свой ответ:", reply_markup=get_cancel_keyboard())
        return

    opt_index = int(suffix)
    q = questions[index]
    answer_text = q["options"][opt_index] if opt_index < len(q["options"]) else "Нет"

    answers.append({"question": q["question"], "answer": answer_text})
    next_index = index + 1
    await state.update_data(followup_answers=answers, followup_index=next_index, waiting_custom=False)

    await callback.message.answer(f"› {answer_text}")
    await _advance_followup(callback.message, state, questions, next_index)


@router.message(Consultation.answering_followup, F.text)
async def process_followup_text(message: Message, state: FSMContext):
    if message.text.strip() == "❌ Отменить":
        await state.clear()
        await message.answer("❌ Консультация отменена", reply_markup=get_main_menu())
        return

    data = await state.get_data()
    if not data.get("waiting_custom"):
        return

    questions = data.get("followup_questions", [])
    index = data.get("followup_index", 0)
    answers = data.get("followup_answers", [])

    q = questions[index]
    answers.append({"question": q["question"], "answer": message.text.strip()})
    next_index = index + 1
    await state.update_data(followup_answers=answers, followup_index=next_index, waiting_custom=False)

    await _advance_followup(message, state, questions, next_index)


async def _advance_followup(msg, state: FSMContext, questions: list, next_index: int):
    """Показывает следующий followup-вопрос или переходит к вопросу о давности."""
    if next_index < len(questions):
        q = questions[next_index]
        await msg.answer(
            f"❓ {q['question']}",
            reply_markup=_make_question_keyboard(q["options"]),
            parse_mode="HTML",
        )
    else:
        duration_q = get_duration_question()
        await state.set_state(Consultation.waiting_for_duration)
        await msg.answer(
            f"❓ {duration_q['question']}",
            reply_markup=_make_duration_keyboard(duration_q["options"]),
            parse_mode="HTML",
        )


@router.callback_query(Consultation.waiting_for_duration, F.data.startswith("dur:"))
async def process_duration_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    duration_q = get_duration_question()
    opt_index = int(callback.data.split(":", 1)[1])
    duration = duration_q["options"][opt_index] if opt_index < len(duration_q["options"]) else "не указана"

    data = await state.get_data()
    symptoms = data.get("symptoms", "")

    await state.update_data(duration=duration, anamnesis_index=0, anamnesis_answers=[], waiting_custom_anamnesis=False)

    await callback.message.answer(f"› {duration}")
    preparing_msg = await callback.message.answer("⏳ Подготавливаю вопросы...")
    anamnesis_qs = get_anamnesis_questions(symptoms)
    # Фильтруем вопросы о давности — они уже заданы
    anamnesis_qs = [q for q in anamnesis_qs if not _is_duration_question(q.get("question", ""))]
    await preparing_msg.delete()
    await state.update_data(anamnesis_questions=anamnesis_qs)
    await state.set_state(Consultation.answering_anamnesis)

    q = anamnesis_qs[0]
    await callback.message.answer(
        f"❓ {q['question']}",
        reply_markup=_make_question_keyboard(q["options"]),
        parse_mode="HTML",
    )


@router.callback_query(Consultation.answering_anamnesis, F.data.startswith("ans:"))
async def process_anamnesis_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()

    questions = data.get("anamnesis_questions", [])
    index = data.get("anamnesis_index", 0)
    answers = data.get("anamnesis_answers", [])
    suffix = callback.data.split(":", 1)[1]

    if suffix == "custom":
        await state.update_data(waiting_custom_anamnesis=True)
        await callback.message.answer("✏️ Напишите свой ответ:", reply_markup=get_cancel_keyboard())
        return

    opt_index = int(suffix)
    q = questions[index]
    answer_text = q["options"][opt_index] if opt_index < len(q["options"]) else "Нет"

    answers.append({"question": q["question"], "answer": answer_text})
    next_index = index + 1
    await state.update_data(anamnesis_answers=answers, anamnesis_index=next_index, waiting_custom_anamnesis=False)

    await callback.message.answer(f"› {answer_text}")
    await _advance_anamnesis(callback.message, state, questions, next_index)


@router.message(Consultation.answering_anamnesis, F.text)
async def process_anamnesis_text(message: Message, state: FSMContext):
    if message.text.strip() == "❌ Отменить":
        await state.clear()
        await message.answer("❌ Консультация отменена", reply_markup=get_main_menu())
        return

    data = await state.get_data()
    if not data.get("waiting_custom_anamnesis"):
        return

    questions = data.get("anamnesis_questions", [])
    index = data.get("anamnesis_index", 0)
    answers = data.get("anamnesis_answers", [])

    q = questions[index]
    answers.append({"question": q["question"], "answer": message.text.strip()})
    next_index = index + 1
    await state.update_data(anamnesis_answers=answers, anamnesis_index=next_index, waiting_custom_anamnesis=False)

    await _advance_anamnesis(message, state, questions, next_index)


async def _advance_anamnesis(msg, state: FSMContext, questions: list, next_index: int):
    """Показывает следующий анамнестический вопрос или формирует финальную рекомендацию."""
    if next_index < len(questions):
        q = questions[next_index]
        await msg.answer(
            f"❓ {q['question']}",
            reply_markup=_make_question_keyboard(q["options"]),
            parse_mode="HTML",
        )
        return

    # Все вопросы заданы → финальная рекомендация
    await msg.answer("⏳ Формирую рекомендацию...")

    data = await state.get_data()
    all_data = {
        "symptoms": data.get("symptoms", ""),
        "followup_answers": data.get("followup_answers", []),
        "duration": data.get("duration", "не указана"),
        "anamnesis_answers": data.get("anamnesis_answers", []),
    }
    user_profile = data.get("user_profile", {})
    user_id = data.get("user_id")
    patient_history = data.get("patient_history", "")

    result = get_final_recommendation(all_data, user_profile, patient_history)
    duration = all_data["duration"]

    if user_id:
        await _save_consultation(user_id, all_data, result)

    await state.clear()

    await msg.answer(
        _format_result(result, duration),
        reply_markup=get_main_menu(),
        parse_mode="HTML",
    )
