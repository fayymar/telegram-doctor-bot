"""HTTP API консультации: старт, ответы, длительность, результат, оценка, история."""
import json
import uuid
from datetime import datetime, timezone

from aiohttp import web

from api.common import (
    _MAX_CONSULTATION_SESSIONS,
    _consent_required_response,
    _consent_withdrawn,
    _get_owned_session,
    _is_rate_limited,
    _rate_limit_response,
    _token_user_id,
    _unauthorized,
    auth_required,
    consultation_sessions,
    consultation_store,
    json_response,
)
from database.connection import run_query, supabase_client
from services.consent import CONSENT_VERSION, has_consent, record_consent
from services.consultation_agent import (
    check_red_flags,
    get_anamnesis_questions,
    get_final_recommendation,
    get_patient_history,
    get_recent_health_metrics,
    parse_and_generate_questions,
)
from utils.logger import setup_logger

logger = setup_logger(__name__)


async def api_consultation_start(request: web.Request) -> web.Response:
    """
    POST /api/consultation/start
    Гость — без токена. Авторизованный пользователь — с Authorization: Bearer,
    тогда учитываются его профиль, история и показатели. user_id из тела
    запроса НЕ принимается: только из токена.
    """
    if _is_rate_limited(request, "ai", limit=10, window=60):
        return _rate_limit_response()
    try:
        body = await request.json()
    except Exception:
        return json_response({"error": "Invalid JSON body"}, status=400)

    user_id = _token_user_id(request)
    symptoms = str(body.get("symptoms", "")).strip()

    if not symptoms:
        return json_response({"error": "Missing required field: symptoms"}, status=400)
    if len(symptoms) > 2000:
        return json_response({"error": "Symptoms text is too long (max 2000 chars)"}, status=400)

    # Согласие на обработку данных о здоровье: у вошедшего пользователя — из базы,
    # у гостя — подтверждение текущей версии текста в самом запросе (галочка).
    guest_consent = False
    if user_id:
        if not await has_consent(user_id):
            return _consent_required_response()
    elif body.get("consent_version") == CONSENT_VERSION:
        guest_consent = True
    else:
        return _consent_required_response()

    session_id = str(uuid.uuid4())
    # Согласие гостя записываем ДО отправки симптомов в AI: без сохранённой
    # записи о согласии консультацию не начинаем
    if guest_consent:
        source = body.get("consent_source") if body.get("consent_source") in ("web", "miniapp") else "web"
        try:
            await record_consent(None, source, session_id=session_id)
        except Exception as e:
            logger.error(f"Guest consent save failed: {type(e).__name__}")
            return json_response({"error": "Service temporarily unavailable"}, status=503)

    # Получаем профиль пользователя из Supabase (только если есть user_id)
    user_profile = {}
    patient_history = []
    health_metrics = {"has_any_data": False}
    if user_id:
        try:
            resp = await run_query(lambda: supabase_client.table("user_profiles").select("*").eq("user_id", user_id).limit(1).execute())
            user_profile = (resp.data[0] if resp.data else {})
        except Exception:
            user_profile = {}
        patient_history = await run_query(get_patient_history, user_id, supabase_client)
        health_metrics = await run_query(get_recent_health_metrics, user_id, supabase_client, hours=24)

    # Шаг 1: Красные флаги (с учётом метрик)
    try:
        red_flag_result = check_red_flags(symptoms, health_metrics=health_metrics)
    except Exception as e:
        logger.error(f"check_red_flags failed: {e}", exc_info=True)
        return json_response({"error": "AI service temporarily unavailable"}, status=503)
    red_flag = red_flag_result.get("red_flag", False)
    needs_fresh_metrics = red_flag_result.get("needs_fresh_metrics", [])

    # Шаг 2: Генерация уточняющих вопросов
    try:
        questions = await parse_and_generate_questions(symptoms, user_profile, patient_history)
    except Exception as e:
        logger.error(f"parse_and_generate_questions failed: {e}", exc_info=True)
        return json_response({"error": "AI service temporarily unavailable"}, status=503)

    if questions is None:
        # AI determined the input isn't a medical symptom description
        logger.info("Non-medical input rejected")
        return json_response({
            "error": "not_medical",
            "message": "Похоже, это не описание симптомов. Опишите, что вас беспокоит (например: болит голова, температура, кашель).",
        }, status=422)

    # Пока шли запросы к AI (несколько секунд), аккаунт могли удалить или выйти
    # на всех устройствах: тогда токен уже отозван, и сессию не создаём — иначе
    # данные о здоровье удалённого аккаунта остались бы в памяти и в базе
    if user_id and _token_user_id(request) != user_id:
        return _unauthorized()

    # Ограничиваем число сессий в памяти: при переполнении удаляем самые старые
    if len(consultation_sessions) >= _MAX_CONSULTATION_SESSIONS:
        oldest = sorted(consultation_sessions, key=lambda k: consultation_sessions[k].get("_created_at"))
        for sid in oldest[: len(consultation_sessions) - _MAX_CONSULTATION_SESSIONS + 1]:
            consultation_sessions.pop(sid, None)
            consultation_store.save(sid)
    consultation_sessions[session_id] = {
        "_created_at": datetime.now(timezone.utc),
        "user_id": user_id,
        "symptoms": symptoms,
        "user_profile": user_profile,
        "questions": questions,
        "answers": [],
        "duration": None,
        "anamnesis_questions": [],
        "anamnesis_answers": [],
        "health_metrics": health_metrics,
        "red_flag": red_flag,
    }
    consultation_store.save(session_id)

    return json_response({
        "session_id": session_id,
        "questions": questions,
        "red_flag": red_flag,
        "needs_fresh_metrics": needs_fresh_metrics,
    })


async def api_consultation_answer(request: web.Request) -> web.Response:
    """POST /api/consultation/answer"""
    try:
        body = await request.json()
    except Exception:
        return json_response({"error": "Invalid JSON"}, status=400)

    session_id = body.get("session_id")
    if not session_id:
        return json_response({"error": "session_id is required"}, status=400)

    session = _get_owned_session(request, session_id)
    if not session:
        return json_response({"error": "Session not found"}, status=404)
    if await _consent_withdrawn(session):
        return _consent_required_response()

    try:
        answers = body.get("answers", [])
        if not isinstance(answers, list):
            return json_response({"error": "'answers' must be a list"}, status=400)
        questions = session["questions"]
        # Ответов не может быть больше, чем задано вопросов: иначе большой
        # список из запроса целиком остался бы в памяти до истечения сессии
        answers = answers[:max(len(questions), 1)]

        # Сохраняем каждый ответ, сопоставляя с вопросом по индексу
        paired = []
        for i, ans in enumerate(answers):
            q_text = questions[i]["question"] if i < len(questions) else ""
            paired.append({"question": q_text, "answer": str(ans)[:500]})
        session["answers"] = paired
        consultation_store.save(session_id)

        return json_response({"next_step": "duration"})
    except Exception as e:
        logger.error(f"Consultation answer error: {e}", exc_info=True)
        return json_response({"error": "Internal server error"}, status=500)


async def api_consultation_duration(request: web.Request) -> web.Response:
    """POST /api/consultation/duration"""
    try:
        body = await request.json()
    except Exception:
        return json_response({"error": "Invalid JSON"}, status=400)

    session_id = body.get("session_id")
    duration = str(body.get("duration", ""))[:200]

    if not session_id:
        return json_response({"error": "session_id is required"}, status=400)

    session = _get_owned_session(request, session_id)
    if not session:
        return json_response({"error": "Session not found"}, status=404)
    if await _consent_withdrawn(session):
        return _consent_required_response()
    if _is_rate_limited(request, "ai", limit=10, window=60):
        return _rate_limit_response()

    try:
        session["duration"] = duration
        consultation_store.save(session_id)

        # Генерация анамнестических вопросов
        anamnesis_questions = await get_anamnesis_questions(session["symptoms"])
        session["anamnesis_questions"] = anamnesis_questions
        consultation_store.save(session_id)

        # Нормализуем ключ: question → text для Mini App
        normalized = [
            {"text": q.get("question", q.get("text", "")), "options": q.get("options", [])}
            for q in anamnesis_questions
        ]

        return json_response({"anamnesis_questions": normalized, "needs_fresh_metrics": []})
    except Exception as e:
        logger.error(f"Consultation duration error: {e}", exc_info=True)
        return json_response({"error": "Internal server error"}, status=500)


async def api_consultation_result(request: web.Request) -> web.Response:
    """POST /api/consultation/result"""
    try:
        body = await request.json()
    except Exception:
        return json_response({"error": "Invalid JSON"}, status=400)

    session_id = body.get("session_id")
    if not session_id:
        return json_response({"error": "session_id is required"}, status=400)

    session = _get_owned_session(request, session_id)
    if not session:
        return json_response({"error": "Session not found"}, status=404)
    if await _consent_withdrawn(session):
        return _consent_required_response()
    if _is_rate_limited(request, "ai", limit=10, window=60):
        return _rate_limit_response()

    try:
        # Анамнестические ответы могут быть переданы в теле запроса (плоский список строк или список dict)
        raw_anamnesis = body.get("anamnesis_answers", session.get("anamnesis_answers", []))
        if not isinstance(raw_anamnesis, list):
            raw_anamnesis = []
        raw_anamnesis = raw_anamnesis[:10]
        # Нормализуем: если пришли строки — сопоставляем с вопросами из сессии
        if raw_anamnesis and isinstance(raw_anamnesis[0], str):
            qs = session.get("anamnesis_questions", [])
            anamnesis_answers = [
                {"question": (qs[i].get("text") or qs[i].get("question", "")) if i < len(qs) else "",
                 "answer": str(ans)}
                for i, ans in enumerate(raw_anamnesis)
            ]
        else:
            anamnesis_answers = raw_anamnesis
        session["anamnesis_answers"] = anamnesis_answers
        consultation_store.save(session_id)

        all_data = {
            "symptoms": session["symptoms"],
            "followup_answers": [a for a in session["answers"] if a],
            "duration": session["duration"] or "не указана",
            "anamnesis_answers": anamnesis_answers,
        }

        user_profile = session.get("user_profile") or {}

        recommendation = await get_final_recommendation(
            all_data,
            user_profile,
            health_metrics=session.get("health_metrics"),
            red_flag=bool(session.get("red_flag")),
        )

        # Пока шёл запрос к AI, аккаунт могли удалить (токен отозван): тогда
        # итог не сохраняем — иначе запись о здоровье появилась бы уже после удаления
        if session.get("user_id") and _token_user_id(request) != session["user_id"]:
            consultation_sessions.pop(str(session_id), None)
            consultation_store.save(session_id)
            return _unauthorized()

        # Сохраняем в Supabase (только для авторизованных пользователей)
        specialists_raw = recommendation.get("specialists", [])
        consultation_id = None
        if session.get("user_id"):
            try:
                recommended_doctor = specialists_raw[0]["name"] if specialists_raw else "Терапевт"
                saved = await run_query(lambda: supabase_client.table("consultations").insert({
                    "user_id": session["user_id"],
                    "symptoms": json.dumps({"text": session["symptoms"], "history": [a for a in session["answers"] if a]}, ensure_ascii=False),
                    "questions_answers": json.dumps(all_data, ensure_ascii=False),
                    "recommended_doctor": recommended_doctor,
                    "urgency_level": recommendation.get("urgency", "medium"),
                }).execute())
                consultation_id = (saved.data or [{}])[0].get("id")
            except Exception as e:
                logger.error(f"Failed to save consultation to Supabase: {e}", exc_info=True)

        # Нормализуем specialists: match_percent → percentage для Mini App
        specialists_out = [
            {
                "name": s.get("name", ""),
                "percentage": s.get("match_percent", s.get("percentage", 0)),
                "reason": s.get("reason", ""),
            }
            for s in specialists_raw
        ]

        # Clean up session from memory after successful result
        consultation_sessions.pop(session_id, None)
        consultation_store.save(session_id)
        logger.info(f"Session {session_id} cleaned up after result")

        return json_response({
            "consultation_id": consultation_id,
            "recommendation": recommendation.get("recommendation", recommendation.get("urgency_reason", "")),
            "specialists": specialists_out,
            "urgency": recommendation.get("urgency", "medium"),
            "needs_fresh_metrics": recommendation.get("needs_fresh_metrics", []),
            "needs_fresh_metrics_message": recommendation.get("needs_fresh_metrics_message", ""),
        })

    except Exception as e:
        logger.error(f"Consultation result error: {e}", exc_info=True)
        return json_response({"error": "Internal server error"}, status=500)


@auth_required
async def api_consultation_feedback(request: web.Request) -> web.Response:
    """POST /api/consultation/feedback — оценка СВОЕЙ консультации (good/bad)"""
    try:
        body = await request.json()
    except Exception:
        return json_response({"error": "Invalid JSON"}, status=400)

    consultation_id = body.get("consultation_id")
    rating = body.get("rating")  # "good" | "bad"

    if not consultation_id or rating not in ("good", "bad"):
        return json_response({"error": "consultation_id and rating (good|bad) required"}, status=400)

    user_id = request["user_id"]
    try:
        resp = await run_query(
            lambda: supabase_client.table("consultations")
            .update({"rating": rating})
            .eq("id", consultation_id)
            .eq("user_id", user_id)
            .execute()
        )
        if not resp.data:
            return json_response({"error": "Consultation not found"}, status=404)
        return json_response({"status": "ok"})
    except Exception as e:
        logger.error(f"Feedback error: {e}", exc_info=True)
        return json_response({"error": "Internal server error"}, status=500)


@auth_required
async def api_consultations_get(request: web.Request) -> web.Response:
    """GET /api/consultations/{user_id} — история консультаций для Mini App."""
    user_id = request["user_id"]
    try:
        resp = await run_query(
            lambda: supabase_client.table('consultations')
            .select('id, symptoms, recommended_doctor, urgency_level, created_at')
            .eq('user_id', user_id)
            .order('created_at', desc=True)
            .limit(20)
            .execute()
        )
        rows = resp.data or []
        records = []
        for r in rows:
            symptoms_raw = r.get('symptoms', '')
            try:
                symptoms_parsed = json.loads(symptoms_raw) if symptoms_raw else {}
                if 'text' in symptoms_parsed:
                    symptoms_text = symptoms_parsed['text']
                elif symptoms_parsed.get('history'):
                    first = next(
                        (h for h in symptoms_parsed['history'] if not h.get('question')),
                        symptoms_parsed['history'][0]
                    )
                    symptoms_text = first.get('answer', symptoms_raw)
                elif isinstance(symptoms_parsed, list) and symptoms_parsed:
                    first = next(
                        (h for h in symptoms_parsed if not h.get('question')),
                        symptoms_parsed[0]
                    )
                    symptoms_text = first.get('answer', symptoms_raw)
                else:
                    symptoms_text = symptoms_raw
            except Exception:
                symptoms_text = symptoms_raw
            records.append({
                'id': r.get('id'),
                'symptoms': symptoms_text,
                'recommended_doctor': r.get('recommended_doctor', ''),
                'urgency_level': r.get('urgency_level', 'medium'),
                'created_at': r.get('created_at', ''),
            })
        return json_response({'records': records, 'has_data': bool(records)})
    except Exception as e:
        logger.error(f'Consultations GET error for {user_id}: {e}', exc_info=True)
        return json_response({'records': [], 'has_data': False})
