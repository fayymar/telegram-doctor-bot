"""HTTP API данных пользователя: профиль, лекарства, дневник."""
import re
from datetime import date

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


# Курение и активность хранятся кодами (их понимают бот и ИИ-консультант).
# Сайт и Mini App раньше присылали подписи кнопок — переводим их в коды.
_SMOKING_CODES = {"no", "yes", "quit"}
_SMOKING_LABELS = {
    "не курю": "no", "не курит": "no", "нет": "no",
    "курю": "yes", "курит": "yes", "да": "yes",
    "бросил(а)": "quit", "бросил": "quit", "бросила": "quit",
}
_ACTIVITY_CODES = {"sedentary", "light", "moderate", "active", "athlete"}
_ACTIVITY_LABELS = {
    "сидячий": "sedentary", "низкая": "light", "лёгкий": "light", "легкий": "light",
    "умеренная": "moderate", "умеренный": "moderate",
    "высокая": "active", "активный": "active", "спортсмен": "athlete",
}
_GENDER_LABELS = {"male": "male", "female": "female", "мужской": "male", "женский": "female"}
_NONE_ITEMS = {"нет", "ничего", "не знаю"}
_MAX_LIST_ITEMS = 30
_MAX_ITEM_LEN = 200
_MAX_TEXT_LEN = 1000


class _InvalidField(ValueError):
    def __init__(self, field: str):
        super().__init__(field)
        self.field = field


def _label(value) -> str:
    """«🚭 Не курю» -> «не курю»: без значков в начале, в нижнем регистре."""
    return re.sub(r"^[^\w(]+", "", str(value)).strip().lower()


def _empty(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _text(value, field: str, limit: int) -> str | None:
    if _empty(value):
        return None
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        raise _InvalidField(field)
    return str(value).strip()[:limit]


def _string_list(value, field: str) -> list[str]:
    """Список строк из списка или из строки «Диабет, Гипертония» (так присылал сайт)."""
    if _empty(value):
        return []
    if isinstance(value, str):
        value = re.split(r"[,;\n]", value)
    if not isinstance(value, list):
        raise _InvalidField(field)
    items: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise _InvalidField(field)
        item = re.sub(r"^[^\w(]+", "", item).strip()[:_MAX_ITEM_LEN]  # без значков в начале
        if item and item.lower() not in _NONE_ITEMS and item not in items:
            items.append(item)
    return items[:_MAX_LIST_ITEMS]


def _code(value, field: str, codes: set[str], labels: dict[str, str]) -> str | None:
    if _empty(value):
        return None
    if not isinstance(value, str):
        raise _InvalidField(field)
    if value in codes:
        return value
    code = labels.get(_label(value))
    if code is None:
        raise _InvalidField(field)
    return code


def _number(value, field: str, low: float, high: float, integer: bool):
    if _empty(value):
        return None
    try:
        number = float(str(value).replace(",", "."))
    except ValueError:
        raise _InvalidField(field) from None
    if not low <= number <= high:
        raise _InvalidField(field)
    return int(round(number)) if integer else round(number, 1)


def _birthdate(value) -> str | None:
    if _empty(value):
        return None
    if not isinstance(value, str):
        raise _InvalidField("birthdate")
    try:
        parsed = date.fromisoformat(value.strip()[:10])
    except ValueError:
        raise _InvalidField("birthdate") from None
    if not date(1900, 1, 1) <= parsed <= date.today():
        raise _InvalidField("birthdate")
    return parsed.isoformat()


def normalize_profile(body: dict) -> dict:
    """
    Приводит профиль к виду, в котором его сохраняет бот: списки болезней —
    списками, курение и активность — кодами, пустые значения — null.
    Неизвестные поля отбрасываются, недопустимые значения — _InvalidField.
    """
    data: dict = {}
    if "full_name" in body:
        data["full_name"] = _text(body["full_name"], "full_name", 200)
    if "phone" in body:
        data["phone"] = _text(body["phone"], "phone", 40)
    if "birthdate" in body:
        data["birthdate"] = _birthdate(body["birthdate"])
    if "gender" in body:
        data["gender"] = _code(body["gender"], "gender", {"male", "female"}, _GENDER_LABELS)
    if "height" in body:
        data["height"] = _number(body["height"], "height", 30, 260, integer=True)
    if "weight" in body:
        data["weight"] = _number(body["weight"], "weight", 2, 400, integer=False)
    for field in ("chronic_diseases", "hereditary"):
        if field in body:
            data[field] = _string_list(body[field], field)
    if "smoking" in body:
        data["smoking"] = _code(body["smoking"], "smoking", _SMOKING_CODES, _SMOKING_LABELS)
    if "physical_activity" in body:
        data["physical_activity"] = _code(body["physical_activity"], "physical_activity",
                                          _ACTIVITY_CODES, _ACTIVITY_LABELS)
    # Аллергии: бот хранит строкой «A, B». Старый Mini App присылал список
    # allergies и отдельное поле allergies_other.
    if "drug_allergies" in body:
        raw = body["drug_allergies"]
        items = _string_list(raw, "drug_allergies") if isinstance(raw, list) else None
        data["drug_allergies"] = ", ".join(items) if items is not None else (
            _text(raw, "drug_allergies", _MAX_TEXT_LEN) or "")
    elif "allergies" in body or "allergies_other" in body:
        items = _string_list(body.get("allergies"), "allergies")
        other = _text(body.get("allergies_other"), "allergies_other", _MAX_TEXT_LEN)
        if other:
            items.append(other)
        data["drug_allergies"] = ", ".join(items)[:_MAX_TEXT_LEN]
    return data


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

    try:
        update_data = normalize_profile(body)
    except _InvalidField as e:
        return json_response({"error": "invalid_field", "field": e.field}, status=400)
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
