from typing import Optional

from services.ai_service import AIService
from utils.logger import setup_logger

logger = setup_logger(__name__)

ai_service = AIService()

MAX_QUESTIONS = 4


def run_agent(history: list[dict], user_message: str) -> dict:
    """
    Агентный шаг консультации.

    history — список предыдущих обменов вида:
        [{"question": "...", "answer": "..."}, ...]

    user_message — последний ответ пользователя (или первичное описание симптомов).

    Возвращает JSON одного из двух видов:
        {"action": "ask", "question": "..."}
        {"action": "conclude", "specialists": [...], "urgency": "...", "urgency_reason": "..."}
    """
    question_count = len(history)

    if question_count >= MAX_QUESTIONS:
        return _conclude(history, user_message)

    system_prompt = _build_system_prompt(question_count)
    user_block = _build_user_block(history, user_message)

    try:
        raw = ai_service._call_ai(system_prompt, user_block, temperature=0.2, max_tokens=512)
        logger.info(f"Raw AI response: {raw}")
        cleaned = ai_service._extract_json_block(raw)

        from utils.json_parser import safe_parse_json_object
        result = safe_parse_json_object(cleaned, default={})

        action = result.get("action")

        if action == "ask" and result.get("question"):
            logger.info(f"Agent asks question #{question_count + 1}")
            return {"action": "ask", "question": result["question"]}

        if action == "conclude":
            specialists = result.get("specialists") or []
            urgency = result.get("urgency", "medium")
            urgency_reason = result.get("urgency_reason", "")
            if specialists:
                logger.info("Agent concludes via AI result")
                return {
                    "action": "conclude",
                    "specialists": specialists,
                    "urgency": urgency,
                    "urgency_reason": urgency_reason,
                }

        logger.warning("Agent returned unexpected structure, forcing conclude")
        return _conclude(history, user_message)

    except Exception as e:
        logger.error(f"Agent step failed: {e}", exc_info=True)
        return _conclude(history, user_message)


def _build_system_prompt(question_count: int) -> str:
    remaining = MAX_QUESTIONS - question_count
    return f"""Ты — медицинский ассистент-агент. Твоя задача — провести короткий опрос пациента (максимум {MAX_QUESTIONS} вопроса суммарно) и определить подходящего специалиста.

У тебя осталось вопросов: {remaining} (включая текущий).

ПРАВИЛА:
1. Если есть ещё вопросы — задай ОДИН наиболее важный уточняющий вопрос.
2. Если вопросов не осталось или картина ясна — сразу давай заключение.
3. Никогда не ставь диагноз — только рекомендуй специалиста.
4. Отвечай СТРОГО в JSON, без лишнего текста.
5. НИКОГДА не рекомендуй Терапевта — этот бот сам выполняет роль терапевта. Всегда рекомендуй узкого специалиста: Невролог, Гастроэнтеролог, Кардиолог, ЛОР, Дерматолог, Хирург, Уролог, Гинеколог, Ортопед и т.д.

ФОРМАТ если задаёшь вопрос:
{{"action": "ask", "question": "Текст вопроса?"}}

ФОРМАТ если даёшь заключение:
{{
  "action": "conclude",
  "specialists": [
    {{"name": "Специалист", "match_percent": 85, "reason": "Почему подходит"}}
  ],
  "urgency": "medium",
  "urgency_reason": "Пояснение"
}}

Уровни срочности: emergency | high | medium | low
Никакого текста вне JSON.
ВАЖНО: отвечай ТОЛЬКО JSON, никакого текста до или после, никаких markdown блоков"""


def _build_user_block(history: list[dict], user_message: str) -> str:
    lines = []
    if not history:
        lines.append(f"Первичные жалобы пациента:\n{user_message}")
    else:
        lines.append("История опроса:")
        for i, item in enumerate(history, 1):
            lines.append(f"В{i}: {item['question']}")
            lines.append(f"О{i}: {item['answer']}")
        lines.append(f"\nПоследний ответ пациента: {user_message}")
    return "\n".join(lines)


def _conclude(history: list[dict], last_message: str) -> dict:
    """Принудительное заключение через AI."""
    system_prompt = """Ты — медицинский ассистент. По итогам опроса дай рекомендацию специалиста.
Ответь СТРОГО в JSON:
{
  "action": "conclude",
  "specialists": [
    {"name": "Специалист", "match_percent": 85, "reason": "Почему подходит"}
  ],
  "urgency": "medium",
  "urgency_reason": "Пояснение"
}
Никакого текста вне JSON."""

    user_block = _build_user_block(history, last_message)

    try:
        raw = ai_service._call_ai(system_prompt, user_block, temperature=0.1, max_tokens=512)
        logger.info(f"Raw AI response (conclude): {raw}")
        cleaned = ai_service._extract_json_block(raw)

        from utils.json_parser import safe_parse_json_object
        result = safe_parse_json_object(cleaned, default={})

        specialists = result.get("specialists") or []
        urgency = result.get("urgency", "medium")
        if urgency not in ("emergency", "high", "medium", "low"):
            urgency = "medium"

        if specialists:
            return {
                "action": "conclude",
                "specialists": specialists,
                "urgency": urgency,
                "urgency_reason": result.get("urgency_reason", ""),
            }
    except Exception as e:
        logger.error(f"Force conclude failed: {e}", exc_info=True)

    # Финальный fallback
    all_text = " ".join(
        [h.get("answer", "") for h in history] + [last_message]
    ).lower()

    specialist = _guess_specialist(all_text)
    return {
        "action": "conclude",
        "specialists": [{"name": specialist, "match_percent": 70, "reason": "Рекомендуется для первичной консультации."}],
        "urgency": "medium",
        "urgency_reason": "Рекомендуется обратиться в ближайшее время.",
    }


def _guess_specialist(text: str) -> str:
    if any(w in text for w in ["каш", "горл", "насмор", "ухо"]):
        return "ЛОР"
    if any(w in text for w in ["голов", "онемен", "судорог"]):
        return "Невролог"
    if any(w in text for w in ["живот", "тошнот", "рвот", "понос"]):
        return "Гастроэнтеролог"
    if any(w in text for w in ["сердц", "давлен", "груд", "одыш"]):
        return "Кардиолог"
    if any(w in text for w in ["сып", "зуд", "кож"]):
        return "Дерматолог"
    return "Терапевт"
