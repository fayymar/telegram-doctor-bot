"""HTTP API данных пользователя: профиль, лекарства, дневник."""
from aiohttp import web

from api.common import (
    auth_required,
    consent_required,
    json_response,
)
from database.connection import run_query, supabase_client
from utils.logger import setup_logger

logger = setup_logger(__name__)


_PROFILE_FIELDS = [
    "full_name", "phone", "birthdate", "gender", "height", "weight",
    "chronic_diseases", "drug_allergies", "smoking", "hereditary", "physical_activity",
]


@auth_required
async def api_profile_get(request: web.Request) -> web.Response:
    """GET /api/profile/{user_id} — читает из таблицы user_profiles по user_id"""
    user_id = request["user_id"]

    try:
        resp = await run_query(
            lambda: supabase_client.table("user_profiles")
            .select(", ".join(_PROFILE_FIELDS))
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            return json_response({"exists": False, "profile": None})

        row = rows[0]
        profile = {f: row.get(f) for f in _PROFILE_FIELDS}
        return json_response({"exists": True, "profile": profile})
    except Exception as e:
        logger.error(f"Profile GET error for user {user_id}: {e}", exc_info=True)
        return json_response({"error": "Internal server error"}, status=500)


@auth_required
@consent_required
async def api_profile_post(request: web.Request) -> web.Response:
    """POST /api/profile/{user_id} — upsert в таблицу user_profiles по user_id"""
    user_id = request["user_id"]

    try:
        body = await request.json()
    except Exception:
        return json_response({"error": "Invalid JSON"}, status=400)
    if not isinstance(body, dict):
        return json_response({"error": "Invalid JSON"}, status=400)

    # Берём только допустимые поля профиля
    update_data = {k: v for k, v in body.items() if k in _PROFILE_FIELDS}
    if not update_data:
        return json_response({"error": "No valid profile fields provided"}, status=400)

    update_data["user_id"] = user_id
    logger.info(f"Profile POST: user_id={user_id}, fields={sorted(update_data)}")

    try:
        await run_query(lambda: supabase_client.table("user_profiles").upsert(update_data, on_conflict="user_id").execute())
        return json_response({"status": "ok"})
    except Exception as e:
        logger.error(f"Profile POST error for user {user_id}: {e}", exc_info=True)
        return json_response({"error": "Internal server error"}, status=500)


async def _check_anamnesis_fields():
    """Проверяет наличие полей анамнеза в user_profiles (миграции выполняются вручную)."""
    try:
        await run_query(lambda: supabase_client.table("user_profiles").select(
            "chronic_diseases, drug_allergies, smoking, hereditary"
        ).limit(1).execute())
        logger.info("✅ Anamnesis fields present in user_profiles")
    except Exception as e:
        logger.error(
            f"MISSING FIELDS in user_profiles: {e}. "
            "Run migrations/008_add_anamnesis_fields.sql in Supabase SQL Editor."
        )


@auth_required
@consent_required
async def api_medications_post(request: web.Request) -> web.Response:
    """POST /api/medications/{user_id} — добавить лекарство"""
    user_id = request["user_id"]
    try:
        body = await request.json()
    except Exception:
        return json_response({'error': 'invalid JSON'}, status=400)
    try:
        row = {
            'user_id': user_id,
            'medication_name': body.get('name') or body.get('medication_name', ''),
            'dosage': body.get('dosage', ''),
            'frequency': body.get('frequency', ''),
            'times': body.get('times', []),
            'start_date': body.get('start_date') or None,
            'end_date': body.get('end_date') or None,
            'notes': body.get('notes', ''),
            'is_active': True,
        }
        resp = await run_query(
            lambda: supabase_client.table('medications').insert(row).execute()
        )
        inserted = (resp.data or [{}])[0]
        return json_response({'ok': True, 'id': inserted.get('id')})
    except Exception as e:
        logger.error(f'Medications POST error for {user_id}: {e}', exc_info=True)
        return json_response({'error': 'Internal server error'}, status=500)


@auth_required
@consent_required
async def api_diary_post(request: web.Request) -> web.Response:
    """POST /api/diary/{user_id} — добавить запись дневника"""
    user_id = request["user_id"]
    try:
        body = await request.json()
    except Exception:
        return json_response({'error': 'invalid JSON'}, status=400)
    try:
        from datetime import date, datetime
        today = date.today().isoformat()
        now_time = datetime.now().strftime('%H:%M:%S')
        row = {
            'user_id': user_id,
            'entry_date': body.get('entry_date', today),
            'entry_time': body.get('entry_time', now_time),
        }
        for field in ('temperature', 'blood_pressure_sys', 'blood_pressure_dia', 'pulse', 'weight'):
            if field in body and body[field] is not None:
                row[field] = body[field]
        for field in ('mood', 'symptoms', 'notes'):
            if body.get(field):
                row[field] = body[field]
        resp = await run_query(
            lambda: supabase_client.table('health_diary').insert(row).execute()
        )
        inserted = (resp.data or [{}])[0]
        return json_response({'ok': True, 'id': inserted.get('id')})
    except Exception as e:
        logger.error(f'Diary POST error for {user_id}: {e}', exc_info=True)
        return json_response({'error': 'Internal server error'}, status=500)


@auth_required
async def api_medications_get(request: web.Request) -> web.Response:
    """GET /api/medications/{user_id} — список активных лекарств пользователя"""
    user_id = request["user_id"]
    try:
        resp = await run_query(
            lambda: supabase_client.table('medications')
            .select('id, medication_name, dosage, frequency, times, start_date, end_date, notes')
            .eq('user_id', user_id)
            .eq('is_active', True)
            .order('created_at', desc=True)
            .execute()
        )
        return json_response({'records': resp.data or [], 'has_data': bool(resp.data)})
    except Exception as e:
        logger.error(f'Medications GET error for {user_id}: {e}', exc_info=True)
        return json_response({'records': [], 'has_data': False})


@auth_required
async def api_diary_get(request: web.Request) -> web.Response:
    """GET /api/diary/{user_id} — записи дневника здоровья"""
    user_id = request["user_id"]
    try:
        resp = await run_query(
            lambda: supabase_client.table('health_diary')
            .select('id, entry_date, entry_time, created_at, temperature, blood_pressure_sys, blood_pressure_dia, pulse, weight, mood, symptoms, notes')
            .eq('user_id', user_id)
            .order('entry_date', desc=True)
            .order('entry_time', desc=True)
            .limit(30)
            .execute()
        )
        rows = resp.data or []
        entries = []
        for row in rows:
            # Normalize created_at for web display
            created_at = row.get('created_at') or f"{row.get('entry_date', '')}T{row.get('entry_time', '00:00:00')}"
            entries.append({**row, 'created_at': created_at})
        return json_response({'records': entries, 'has_data': bool(entries)})
    except Exception as e:
        logger.error(f'Diary GET error for {user_id}: {e}', exc_info=True)
        return json_response({'records': [], 'has_data': False})
