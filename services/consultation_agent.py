from typing import List, Dict

from services.ai_service import AIService
from services.symptom_parser import parse_symptoms
from services.red_flags import detect_red_flags
from services.medical_router import MedicalRouter

medical_router = MedicalRouter()
from utils.logger import setup_logger
from utils.json_parser import safe_parse_json_array

logger = setup_logger(__name__)

ai_service = AIService()


def check_red_flags(symptoms_text: str) -> dict:
    """
    Шаг 1: Проверяет наличие красных флагов (экстренных симптомов).
    Использует services/red_flags.py.
    Возвращает {"red_flag": True} если опасно, иначе {"red_flag": False}.
    """
    try:
        parsed = parse_symptoms(symptoms_text)
        result = detect_red_flags(parsed, None)
        if result.get("urgency") == "emergency":
            return {"red_flag": True}
        return {"red_flag": False}
    except Exception as e:
        logger.error(f"check_red_flags error: {e}", exc_info=True)
        return {"red_flag": False}


def parse_and_generate_questions(symptoms_text: str, user_profile: dict) -> list:
    """
    Шаг 2: Классифицирует симптомы и генерирует через Groq уточняющие вопросы (1-3).
    Учитывает возраст и пол из user_profile.
    НИКОГДА не генерирует вопросы про давность.
    Возвращает: [{"question": "...", "options": [...]}]
    """
    parsed = parse_symptoms(symptoms_text)
    primary_cluster = parsed.get("primary_cluster", "general")
    confidence = parsed.get("confidence", "low")

    age = user_profile.get("age", "не указан")
    gender_raw = user_profile.get("gender", "")
    gender = "мужчина" if gender_raw == "male" else ("женщина" if gender_raw == "female" else "не указан")

    if confidence == "high":
        num_questions = 1
    elif confidence == "medium":
        num_questions = 2
    else:
        num_questions = 3

    system_prompt = f"""Ты — медицинский ассистент. Сгенерируй {num_questions} уточняющих вопроса для пациента по его симптомам.

ВАЖНО:
- НЕ задавай вопросы про давность симптомов (она задаётся отдельно)
- Каждый вопрос должен иметь 3-4 варианта ответа, последний вариант — "Ничего из этого"
- Учитывай пол пациента: {gender}, возраст: {age} лет
- Кластер симптомов: {primary_cluster}
- Вопросы должны помогать уточнить специалиста

Ответь СТРОГО JSON-массивом, без лишнего текста:
[
  {{
    "question": "Текст вопроса?",
    "options": ["Вариант 1", "Вариант 2", "Вариант 3", "Ничего из этого"]
  }}
]"""

    user_message = f"Симптомы пациента: {symptoms_text}"

    try:
        raw = ai_service._call_ai(system_prompt, user_message, temperature=0.3, max_tokens=800)
        cleaned = ai_service._extract_json_block(raw)
        questions = safe_parse_json_array(cleaned, default=[])

        valid = []
        for q in questions:
            if isinstance(q, dict) and q.get("question") and isinstance(q.get("options"), list):
                options = [str(o) for o in q["options"][:5]]
                if "Ничего из этого" not in options:
                    options.append("Ничего из этого")
                valid.append({"question": q["question"], "options": options})

        if valid:
            return valid[:num_questions]

        logger.warning("Questions generation returned no valid questions, using fallback")
        return _fallback_questions(primary_cluster)

    except Exception as e:
        logger.error(f"parse_and_generate_questions error: {e}", exc_info=True)
        return _fallback_questions(primary_cluster)


def _fallback_questions(cluster: str) -> list:
    fallbacks = {
        "neuro": [
            {
                "question": "Где локализована боль или дискомфорт?",
                "options": ["Вся голова", "Одна сторона", "Затылок", "Ничего из этого"]
            }
        ],
        "gastro": [
            {
                "question": "Когда усиливается дискомфорт в животе?",
                "options": ["После еды", "До еды", "Ночью", "Ничего из этого"]
            }
        ],
        "respiratory": [
            {
                "question": "Есть ли повышение температуры?",
                "options": ["Да, высокая (38+)", "Небольшая (37-38)", "Нет", "Ничего из этого"]
            }
        ],
        "cardio": [
            {
                "question": "Как проявляется дискомфорт в груди?",
                "options": ["Давящий", "Колющий", "Жжение", "Ничего из этого"]
            }
        ],
    }
    return fallbacks.get(cluster, [
        {
            "question": "Как бы вы оценили интенсивность симптомов?",
            "options": ["Сильные", "Умеренные", "Слабые", "Ничего из этого"]
        }
    ])


def get_duration_question() -> dict:
    """
    Шаг 3: Возвращает фиксированный вопрос о давности симптомов.
    """
    return {
        "question": "Как давно появились симптомы?",
        "options": ["Сегодня", "2-3 дня", "Около недели", "2-4 недели", "Больше месяца"]
    }


def get_anamnesis_questions(symptoms_text: str) -> list:
    """
    Шаг 4: Генерирует через Groq 1-2 анамнестических вопроса, релевантных симптомам.
    Возвращает: [{"question": "...", "options": [...]}]
    """
    system_prompt = """Ты — медицинский ассистент. Сгенерируй 1-2 анамнестических вопроса, релевантных симптомам пациента.

Примеры:
- "Есть хронические заболевания?" ["Есть","Нет","Не знаю"]
- "Повышалась температура?" ["Да","Нет","Не измерял"]
- "Принимаете лекарства?" ["Да","Нет"]
- "Были похожие эпизоды раньше?" ["Да","Нет"]

Ответь СТРОГО JSON-массивом из 1-2 объектов, без лишнего текста:
[
  {
    "question": "Текст вопроса?",
    "options": ["Вариант 1", "Вариант 2", "Вариант 3"]
  }
]"""

    user_message = f"Симптомы пациента: {symptoms_text}"

    try:
        raw = ai_service._call_ai(system_prompt, user_message, temperature=0.3, max_tokens=400)
        cleaned = ai_service._extract_json_block(raw)
        questions = safe_parse_json_array(cleaned, default=[])

        valid = []
        for q in questions:
            if isinstance(q, dict) and q.get("question") and isinstance(q.get("options"), list):
                valid.append({
                    "question": q["question"],
                    "options": [str(o) for o in q["options"][:4]]
                })

        if valid:
            return valid[:2]

        return _fallback_anamnesis()

    except Exception as e:
        logger.error(f"get_anamnesis_questions error: {e}", exc_info=True)
        return _fallback_anamnesis()


def _fallback_anamnesis() -> list:
    return [
        {
            "question": "Есть хронические заболевания?",
            "options": ["Есть", "Нет", "Не знаю"]
        },
        {
            "question": "Принимаете лекарства?",
            "options": ["Да", "Нет"]
        }
    ]


def get_final_recommendation(all_data: dict, user_profile: dict) -> dict:
    """
    Шаг 5: Получает финальную рекомендацию через services/medical_router.py.
    all_data: {symptoms, followup_answers, duration, anamnesis_answers}
    Учитывает возраст и пол из user_profile.
    НИКОГДА не рекомендует Терапевта первым.
    Возвращает: 1 главный специалист + 1-2 смежных с процентами.
    """
    symptoms = all_data.get("symptoms", "")
    duration = all_data.get("duration", "не указана")
    followup_answers = all_data.get("followup_answers", [])
    anamnesis_answers = all_data.get("anamnesis_answers", [])

    additional = []
    for qa in followup_answers:
        answer = qa.get("answer", "")
        if answer and answer not in ("Ничего из этого",):
            additional.append(answer)
    for qa in anamnesis_answers:
        answer = qa.get("answer", "")
        if answer and answer not in ("Нет", "Не знаю", "Не измерял"):
            q_text = qa.get("question", "")
            additional.append(f"{q_text}: {answer}" if q_text else answer)

    try:
        result = medical_router.recommend_doctor(symptoms, duration, additional, user_profile)

        specialists = result.get("specialists", [])
        # Убираем Терапевта с первого места если есть узкие специалисты
        if len(specialists) > 1 and specialists[0].get("name") == "Терапевт":
            therapist = specialists.pop(0)
            specialists.append(therapist)
            result["specialists"] = specialists

        # Оставляем 1 главный + до 2 смежных
        result["specialists"] = result["specialists"][:3]
        return result

    except Exception as e:
        logger.error(f"get_final_recommendation error: {e}", exc_info=True)
        return {
            "specialists": [
                {"name": "Терапевт", "match_percent": 70, "reason": "Рекомендуется для первичного осмотра."}
            ],
            "urgency": "medium",
            "urgency_reason": "Рекомендуется обратиться к врачу.",
        }
