import json
from datetime import datetime

from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from bot.states import ConsultationAgent
from bot.keyboards import get_main_menu, get_cancel_keyboard
from services.consultation_agent import run_agent
from database.connection import supabase_client
from utils.logger import setup_logger

logger = setup_logger(__name__)
router = Router()

URGENCY_LABELS = {
    "emergency": "🚨 Немедленно обратитесь за помощью",
    "high": "⚠️ Обратитесь в течение 24 часов",
    "medium": "📅 Рекомендуется консультация в течение недели",
    "low": "📋 Плановый визит к врачу",
}


async def _save_consultation(user_id: int, history: list, result: dict):
    try:
        specialists = result.get("specialists", [])
        top = specialists[0] if specialists else {}
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


def _format_conclusion(result: dict) -> str:
    specialists = result.get("specialists", [])
    urgency = result.get("urgency", "medium")
    urgency_reason = result.get("urgency_reason", "")

    lines = ["🩺 *Результат консультации*\n"]

    urgency_label = URGENCY_LABELS.get(urgency, URGENCY_LABELS["medium"])
    lines.append(urgency_label)
    if urgency_reason:
        lines.append(f"_{urgency_reason}_\n")

    lines.append("*Рекомендуемые специалисты:*")
    for spec in specialists[:5]:
        name = spec.get("name", "")
        pct = spec.get("match_percent", 0)
        reason = spec.get("reason", "")
        lines.append(f"• *{name}* — {pct}%\n  {reason}")

    lines.append("\n⚠️ _Это не диагноз. Обратитесь к врачу для точного обследования._")
    return "\n".join(lines)


# ============ ХЕНДЛЕРЫ ============

@router.message(F.text == "🩺 Новая консультация")
async def start_consultation(message: Message, state: FSMContext):
    try:
        response = supabase_client.table("user_profiles").select("user_id").eq(
            "user_id", message.from_user.id
        ).execute()
        if not response.data:
            await message.answer(
                "❌ Пожалуйста, сначала зарегистрируйтесь\nИспользуйте /start"
            )
            return
    except Exception as e:
        logger.error(f"DB error in start_consultation: {e}", exc_info=True)

    await state.clear()
    await state.set_state(ConsultationAgent.in_progress)
    await state.update_data(history=[])

    await message.answer(
        "🩺 *Новая консультация*\n\n"
        "Опишите ваши симптомы — что вас беспокоит?\n\n"
        "💡 Чем подробнее опишете, тем точнее будет рекомендация.",
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown",
    )


@router.message(ConsultationAgent.in_progress, F.text == "❌ Отменить")
async def cancel_consultation(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Консультация отменена", reply_markup=get_main_menu())


@router.message(ConsultationAgent.in_progress, F.text)
async def process_agent_message(message: Message, state: FSMContext):
    user_text = message.text.strip()
    if not user_text:
        return

    data = await state.get_data()
    history: list = data.get("history", [])

    await message.answer("⏳ Анализирую...")

    result = run_agent(history, user_text)

    if result["action"] == "ask":
        question = result["question"]

        # Записываем ответ пользователя к последнему открытому вопросу
        if history and history[-1].get("answer") is None:
            history[-1]["answer"] = user_text
        else:
            # Первичные жалобы — нет предыдущего вопроса
            history.append({"question": None, "answer": user_text})

        # Добавляем новый вопрос агента (ответ будет заполнен на следующем шаге)
        history.append({"question": question, "answer": None})
        await state.update_data(history=history)

        await message.answer(question, reply_markup=get_cancel_keyboard())

    else:
        # conclude — закрываем последний открытый ответ
        if history and history[-1].get("answer") is None:
            history[-1]["answer"] = user_text
        else:
            history.append({"question": None, "answer": user_text})

        await _save_consultation(message.from_user.id, history, result)
        await state.clear()

        await message.answer(
            _format_conclusion(result),
            reply_markup=get_main_menu(),
            parse_mode="Markdown",
        )
