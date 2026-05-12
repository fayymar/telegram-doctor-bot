from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional

from services.ai_service import AIService
from services.symptom_parser import parse_symptoms
from services.red_flags import detect_red_flags
from utils.logger import setup_logger
from utils.json_parser import safe_parse_json_array

logger = setup_logger(__name__)

ai_service = AIService()


# ── Medical profile helpers ───────────────────────────────────────────────────

def format_medical_context(profile: dict) -> str:
    """Форматирует анамнез пациента в текст для системного промпта AI."""
    if not profile:
        return ""
    lines = []
    chronic = profile.get("chronic_diseases") or []
    if isinstance(chronic, list) and chronic:
        lines.append(f"Хронические заболевания: {', '.join(chronic)}")
    hereditary = profile.get("hereditary") or []
    if isinstance(hereditary, list) and hereditary:
        lines.append(f"Наследственность (у родственников): {', '.join(hereditary)}")
    drug_allergies = (profile.get("drug_allergies") or "").strip()
    if drug_allergies:
        lines.append(f"Аллергии на лекарства: {drug_allergies}")
    smoking = profile.get("smoking") or ""
    smoking_map = {"yes": "курит", "no": "не курит", "quit": "бросил(а) курить"}
    if smoking in smoking_map:
        lines.append(f"Курение: {smoking_map[smoking]}")
    return "\n".join(lines)


def _build_medical_preamble(profile: dict) -> str:
    """Возвращает блок с медицинским профилем для вставки перед системным промптом."""
    ctx = format_medical_context(profile)
    if not ctx:
        return ""
    return (
        "МЕДИЦИНСКИЙ ПРОФИЛЬ ПАЦИЕНТА:\n"
        f"{ctx}\n\n"
        "ВАЖНО: Учитывай эти данные при анализе:\n"
        "- Хронические заболевания могут быть причиной или отягощать симптомы\n"
        "- При наследственности учитывай повышенные риски\n"
        "- Аллергии на лекарства — НИКОГДА не рекомендуй эти препараты\n"
        "- Возраст и пол влияют на вероятность заболеваний\n\n"
    )


# ── Health metrics helpers ────────────────────────────────────────────────────

def get_recent_health_metrics(user_id: int, supabase_client, hours: int = 24) -> dict:
    """
    Возвращает последнюю запись каждого типа метрики за последние N часов.
    is_fresh = True если запись моложе 6 часов.
    """
    result: dict = {
        "heartrate": None,
        "blood_pressure": None,
        "spo2": None,
        "steps": None,
        "has_any_data": False,
    }
    try:
        cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        fresh_cutoff = (datetime.utcnow() - timedelta(hours=6)).isoformat()

        resp = (
            supabase_client.table("health_metrics")
            .select("metric_type, value, recorded_at")
            .eq("user_id", user_id)
            .in_("metric_type", [
                "heartrate", "blood_pressure_systolic",
                "blood_pressure_diastolic", "spo2", "steps",
            ])
            .gte("recorded_at", cutoff)
            .order("recorded_at", desc=True)
            .execute()
        )

        rows = resp.data or []
        seen: dict = {}
        for row in rows:
            mt = row["metric_type"]
            if mt not in seen:
                seen[mt] = row

        def _fresh(recorded_at: str) -> bool:
            return recorded_at >= fresh_cutoff

        if "heartrate" in seen:
            r = seen["heartrate"]
            result["heartrate"] = {
                "value": r["value"],
                "recorded_at": r["recorded_at"],
                "is_fresh": _fresh(r["recorded_at"]),
            }
            result["has_any_data"] = True

        sys_row = seen.get("blood_pressure_systolic")
        dia_row = seen.get("blood_pressure_diastolic")
        if sys_row:
            recorded_at = sys_row["recorded_at"]
            result["blood_pressure"] = {
                "systolic": sys_row["value"],
                "diastolic": dia_row["value"] if dia_row else None,
                "recorded_at": recorded_at,
                "is_fresh": _fresh(recorded_at),
            }
            result["has_any_data"] = True

        if "spo2" in seen:
            r = seen["spo2"]
            result["spo2"] = {
                "value": r["value"],
                "recorded_at": r["recorded_at"],
                "is_fresh": _fresh(r["recorded_at"]),
            }
            result["has_any_data"] = True

        if "steps" in seen:
            r = seen["steps"]
            result["steps"] = {
                "value": r["value"],
                "recorded_at": r["recorded_at"],
                "is_fresh": _fresh(r["recorded_at"]),
            }
            result["has_any_data"] = True

    except Exception as e:
        logger.error(f"get_recent_health_metrics error user_id={user_id}: {e}", exc_info=True)

    return result


def _time_ago(recorded_at: str) -> str:
    """Возвращает человекочитаемое время назад."""
    try:
        dt = datetime.fromisoformat(recorded_at.replace("Z", "").split("+")[0])
        diff = datetime.utcnow() - dt
        minutes = int(diff.total_seconds() / 60)
        if minutes < 60:
            return f"{minutes} мин назад"
        hours = minutes // 60
        if hours < 24:
            return f"{hours} ч назад"
        return f"{hours // 24} дн назад"
    except Exception:
        return "недавно"


def _format_metrics_for_prompt(metrics: dict) -> str:
    """Форматирует метрики для вставки в system prompt."""
    if not metrics or not metrics.get("has_any_data"):
        return ""

    lines = ["Доступные показатели здоровья пациента:"]

    hr = metrics.get("heartrate")
    if hr:
        fresh = "✅ свежие" if hr["is_fresh"] else "⚠️ устаревшие"
        lines.append(f"- Пульс: {hr['value']:.0f} уд/мин ({_time_ago(hr['recorded_at'])}) {fresh}")

    bp = metrics.get("blood_pressure")
    if bp:
        fresh = "✅ свежие" if bp["is_fresh"] else "⚠️ устаревшие"
        if bp.get("diastolic") is not None:
            lines.append(f"- Давление: {bp['systolic']:.0f}/{bp['diastolic']:.0f} мм рт.ст. ({_time_ago(bp['recorded_at'])}) {fresh}")
        else:
            lines.append(f"- Давление (сист.): {bp['systolic']:.0f} мм рт.ст. ({_time_ago(bp['recorded_at'])}) {fresh}")

    spo2 = metrics.get("spo2")
    if spo2:
        fresh = "✅ свежие" if spo2["is_fresh"] else "⚠️ устаревшие"
        lines.append(f"- SpO2: {spo2['value']:.0f}% ({_time_ago(spo2['recorded_at'])}) {fresh}")

    steps = metrics.get("steps")
    if steps:
        lines.append(f"- Шаги: {int(steps['value'])} сегодня")

    lines.append(
        "\nУчитывай эти показатели при анализе симптомов. "
        "Если для точной диагностики нужны свежие измерения — включи в JSON-ответ поле "
        "'needs_fresh_metrics' со списком из: heartrate, blood_pressure, spo2."
    )
    return "\n".join(lines)


def check_red_flags(symptoms_text: str, health_metrics: Optional[dict] = None) -> dict:
    """
    Шаг 1: Проверяет наличие красных флагов (экстренных симптомов).
    Использует services/red_flags.py + опциональные показатели здоровья.
    Возвращает {"red_flag": bool, "needs_fresh_metrics": [...]}.
    """
    needs_fresh: list = []
    try:
        parsed = parse_symptoms(symptoms_text)
        result = detect_red_flags(parsed, None)
        red_flag = result.get("urgency") == "emergency"

        # Проверяем метрики — могут добавить красный флаг
        if health_metrics and health_metrics.get("has_any_data"):
            hr = health_metrics.get("heartrate")
            if hr and (hr["value"] > 120 or hr["value"] < 50):
                red_flag = True

            spo2 = health_metrics.get("spo2")
            if spo2 and spo2["value"] < 90:
                red_flag = True

        return {"red_flag": red_flag, "needs_fresh_metrics": needs_fresh}
    except Exception as e:
        logger.error(f"check_red_flags error: {e}", exc_info=True)
        return {"red_flag": False, "needs_fresh_metrics": []}


def parse_and_generate_questions(symptoms_text: str, user_profile: dict, patient_history: str = "") -> list:
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

    # rag_context = find_relevant_diseases(symptoms_text)

    history_block = ""
    if patient_history:
        history_block = f"""
История предыдущих консультаций пациента:
{patient_history}

Учитывай эту историю при формировании вопросов:
- Не спрашивай о хронических болезнях если они уже известны из истории
- Обрати внимание на повторяющиеся симптомы
- Если симптомы похожи на прошлые — уточни изменилось ли что-то
"""

    # rag_block = ""
    # if rag_context:
    #     rag_block = f"""
    # {rag_context}
    #
    # Используй эти диагнозы как ориентир при формировании вопросов.
    # Задавай вопросы которые помогут ОТЛИЧИТЬ эти заболевания друг от друга.
    # """

    medical_preamble = _build_medical_preamble(user_profile)
    system_prompt = (
        f"{medical_preamble}"
        f"Ты — медицинский ассистент. Сгенерируй {num_questions} уточняющих вопроса для пациента "
        f"(пол: {gender}, возраст: {age} лет, кластер: {primary_cluster}). "
        f"Не спрашивай про давность симптомов.\n"
        f"Генерируй ТОЛЬКО вопросы строго релевантные указанным симптомам. "
        f"Если симптом — головная боль, спрашивай про характер боли, локализацию, "
        f"сопутствующие симптомы головы/шеи. НЕ спрашивай про не связанные системы органов."
        f"{history_block}\n"
        f"Ответь ТОЛЬКО валидным JSON массивом без markdown, без ```json, без пояснений. "
        f'Пример: [{{"question": "Где болит?", "options": ["Голова", "Живот", "Ничего из этого"]}}]'
    )

    user_message = f"Симптомы пациента: {symptoms_text}"

    try:
        raw = ai_service._call_ai(system_prompt, user_message, temperature=0.3, max_tokens=800)
        logger.info(f"parse_and_generate_questions raw response: {raw}")
        cleaned = raw.strip()
        if not cleaned.startswith('['):
            import re
            match = re.search(r'\[.*\]', cleaned, re.DOTALL)
            cleaned = match.group(0) if match else '[]'
        logger.info(f"After extract_json_block: {repr(cleaned)}")
        questions = safe_parse_json_array(cleaned, default=[])
        logger.info(f"After safe_parse_json_array: {questions}")

        valid = []
        for q in questions:
            if isinstance(q, dict) and q.get("question") and isinstance(q.get("options"), list) and len(q["options"]) >= 2:
                options = [str(o) for o in q["options"]]
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


def get_patient_history(user_id: int, supabase_client) -> str:
    """
    Возвращает краткое резюме последних 5 консультаций пользователя в виде строки.
    """
    try:
        resp = supabase_client.table("consultations").select(
            "symptoms, recommended_doctor, created_at"
        ).eq("user_id", user_id).order("created_at", desc=True).limit(5).execute()

        if not resp.data:
            return ""

        lines = []
        for row in resp.data:
            date_str = row.get("created_at", "")[:10] if row.get("created_at") else "неизвестно"
            doctor = row.get("recommended_doctor", "неизвестно")
            symptoms_raw = row.get("symptoms", "")
            symptoms_text = ""
            try:
                import json as _json
                parsed = _json.loads(symptoms_raw)
                history = parsed.get("history", [])
                if history:
                    symptoms_text = history[0].get("answer", "")
            except Exception:
                symptoms_text = symptoms_raw[:100] if symptoms_raw else ""
            lines.append(f"- {date_str}: симптомы — {symptoms_text}, рекомендован — {doctor}")

        return "\n".join(lines)
    except Exception as e:
        logger.error(f"get_patient_history error: {e}", exc_info=True)
        return ""


def get_final_recommendation(
    all_data: dict,
    user_profile: dict,
    patient_history: str = "",
    health_metrics: Optional[dict] = None,
) -> dict:
    """
    Шаг 5: Получает финальную рекомендацию через прямой вызов AI.
    all_data: {symptoms, followup_answers, duration, anamnesis_answers}
    Учитывает возраст, пол из user_profile и показатели здоровья.
    НИКОГДА не рекомендует Терапевта первым.
    Возвращает: specialists, urgency, recommendation, needs_fresh_metrics.
    """
    symptoms = all_data.get("symptoms", "")
    duration = all_data.get("duration", "не указана")
    followup_answers = all_data.get("followup_answers", [])
    anamnesis_answers = all_data.get("anamnesis_answers", [])

    age = user_profile.get("age", "не указан")
    gender_raw = user_profile.get("gender", "")
    gender = "мужчина" if gender_raw == "male" else ("женщина" if gender_raw == "female" else "не указан")

    followup_text = "; ".join(
        qa.get("answer", "") for qa in followup_answers
        if qa.get("answer") and qa.get("answer") not in ("Ничего из этого",)
    )
    anamnesis_text = "; ".join(
        f"{qa.get('question', '')}: {qa.get('answer', '')}"
        for qa in anamnesis_answers
        if qa.get("answer") and qa.get("answer") not in ("Нет", "Не знаю", "Не измерял")
    )

    metrics_block = _format_metrics_for_prompt(health_metrics) if health_metrics else ""

    medical_preamble = _build_medical_preamble(user_profile)
    system_prompt = (
        f"{medical_preamble}"
        "Ты опытный врач-диагност. На основе собранных данных определи наиболее вероятного специалиста.\n\n"
        f"Симптомы: {symptoms}\n"
        f"Ответы пациента: {followup_text}\n"
        f"Давность: {duration}\n"
        f"Анамнез: {anamnesis_text}\n"
        f"Профиль: пол {gender}, возраст {age}\n"
    )
    if metrics_block:
        system_prompt += f"\n{metrics_block}\n"

    system_prompt += (
        '\nВерни ТОЛЬКО JSON без markdown:\n'
        '{\n'
        '  "specialists": [\n'
        '    {"name": "Эндокринолог", "percent": 75, "reason": "Причина"},\n'
        '    {"name": "Нефролог", "percent": 25, "reason": "Причина"}\n'
        '  ],\n'
        '  "urgency": "medium",\n'
        '  "urgency_reason": "Пояснение для пациента",\n'
        '  "needs_fresh_metrics": []\n'
        '}\n\n'
        "Правила:\n"
        "- Максимум 3 специалиста\n"
        "- Проценты в сумме = 100\n"
        "- НЕ рекомендуй Терапевта\n"
        "- needs_fresh_metrics: список из heartrate/blood_pressure/spo2 если нужны свежие данные\n"
        "- Думай как врач — жажда+мочеиспускание+слабость+похудение = диабет = Эндокринолог"
    )

    try:
        raw = ai_service._call_ai(system_prompt, "Определи специалистов.", temperature=0.1, max_tokens=700)
        cleaned = ai_service._extract_json_block(raw)
        from utils.json_parser import safe_parse_json_object
        parsed = safe_parse_json_object(cleaned, default={})

        specialists_raw = parsed.get("specialists", [])

        # Конвертируем "percent" → "match_percent" для совместимости с consultation.py
        specialists = []
        for s in specialists_raw:
            if not isinstance(s, dict) or not s.get("name"):
                continue
            specialists.append({
                "name": str(s["name"]).strip(),
                "match_percent": int(s.get("percent", s.get("match_percent", 50))),
                "reason": str(s.get("reason", "")).strip(),
            })

        # Принудительно удаляем Терапевта из списка
        specialists = [s for s in specialists if s.get("name") != "Терапевт"]

        if not specialists:
            specialists = [{"name": "Терапевт", "match_percent": 100, "reason": "Симптомы требуют первичной общей консультации для направления к узкому специалисту"}]

        specialists = specialists[:3]

        # Пересчитываем проценты пропорционально, чтобы сумма = 100%
        total = sum(s.get("match_percent", 0) for s in specialists)
        if total > 0:
            for s in specialists:
                s["match_percent"] = round(s.get("match_percent", 0) * 100 / total)
            diff = 100 - sum(s["match_percent"] for s in specialists)
            specialists[0]["match_percent"] += diff

        urgency = parsed.get("urgency", "medium")
        if urgency not in ("emergency", "high", "medium", "low"):
            urgency = "medium"

        urgency_reason = parsed.get("urgency_reason", "Рекомендуется обратиться к врачу.")

        # Формируем читаемый текст рекомендации
        top = specialists[0] if specialists else None
        recommendation_text = urgency_reason
        if top:
            recommendation_text = (
                f"{urgency_reason}\n\n"
                f"Рекомендуемый специалист: {top['name']}. {top.get('reason', '')}"
            ).strip()

        # needs_fresh_metrics от AI
        needs_fresh = parsed.get("needs_fresh_metrics", [])
        if not isinstance(needs_fresh, list):
            needs_fresh = []
        # Оставляем только допустимые значения
        allowed = {"heartrate", "blood_pressure", "spo2"}
        needs_fresh = [m for m in needs_fresh if m in allowed]

        # Сообщение для пользователя если AI запросил свежие метрики
        needs_fresh_message = ""
        if needs_fresh:
            metric_names = {
                "heartrate": "Пульс",
                "blood_pressure": "Давление",
                "spo2": "SpO2",
            }
            names = ", ".join(metric_names.get(m, m) for m in needs_fresh)
            needs_fresh_message = (
                f"💡 Для более точного анализа рекомендуем измерить: {names}. "
                "Откройте раздел Здоровье в приложении и нажмите «Отправить показатели сейчас»."
            )

        return {
            "specialists": specialists,
            "urgency": urgency,
            "urgency_reason": urgency_reason,
            "recommendation": recommendation_text,
            "needs_fresh_metrics": needs_fresh,
            "needs_fresh_metrics_message": needs_fresh_message,
        }

    except Exception as e:
        logger.error(f"get_final_recommendation error: {e}", exc_info=True)
        return {
            "specialists": [
                {"name": "Терапевт", "match_percent": 70, "reason": "Рекомендуется для первичного осмотра."}
            ],
            "urgency": "medium",
            "urgency_reason": "Рекомендуется обратиться к врачу.",
            "recommendation": "Рекомендуется обратиться к врачу.",
            "needs_fresh_metrics": [],
            "needs_fresh_metrics_message": "",
        }
