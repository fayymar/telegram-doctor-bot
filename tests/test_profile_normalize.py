"""Профиль с сайта и из Mini App сохраняется в том же виде, что и из бота."""
import asyncio
from datetime import date, timedelta

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from api.profile import _InvalidField, api_profile_post, normalize_profile
from security.auth import issue_token
from tests.helpers import patch_api


def test_site_comma_strings_become_lists():
    """Сайт присылал болезни строкой — база (text[]) падала с malformed array literal."""
    data = normalize_profile({
        "chronic_diseases": "Диабет, Гипертония",
        "hereditary": "Нет",
        "drug_allergies": "Пенициллин, Аспирин",
        "smoking": "no",
        "physical_activity": "moderate",
        "birthdate": "",
        "gender": "",
        "height": "",
        "weight": "",
    })
    assert data["chronic_diseases"] == ["Диабет", "Гипертония"]
    assert data["hereditary"] == []
    assert data["drug_allergies"] == "Пенициллин, Аспирин"
    assert data["birthdate"] is None and data["gender"] is None
    assert data["height"] is None and data["weight"] is None
    assert data["smoking"] == "no" and data["physical_activity"] == "moderate"


def test_old_miniapp_payload_is_converted():
    """Старый Mini App: подписи кнопок, значки и аллергии отдельными полями."""
    data = normalize_profile({
        "chronic_diseases": ["🩺 Гипертония (высокое давление)", "🩸 Диабет 2 типа"],
        "hereditary": ["🧠 Инсульт"],
        "allergies": ["💊 Пенициллин / антибиотики"],
        "allergies_other": "латекс",
        "smoking": "Бросил(а)",
        "physical_activity": "Умеренная",
    })
    assert data["chronic_diseases"] == ["Гипертония (высокое давление)", "Диабет 2 типа"]
    assert data["hereditary"] == ["Инсульт"]
    assert data["drug_allergies"] == "Пенициллин / антибиотики, латекс"
    assert data["smoking"] == "quit"
    assert data["physical_activity"] == "moderate"


def test_bot_style_values_pass_through():
    data = normalize_profile({
        "full_name": "  Иван Иванов ", "phone": "+998901234567", "birthdate": "1990-05-01T00:00:00",
        "gender": "female", "height": "175", "weight": "70,5", "smoking": "🚬 Курю",
    })
    assert data == {
        "full_name": "Иван Иванов", "phone": "+998901234567", "birthdate": "1990-05-01",
        "gender": "female", "height": 175, "weight": 70.5, "smoking": "yes",
    }


def test_unknown_fields_dropped_and_untouched_fields_absent():
    data = normalize_profile({"smoking": "no", "user_id": 5, "auth_uid": "x", "linked_web_id": "1"})
    assert data == {"smoking": "no"}


@pytest.mark.parametrize("body,field", [
    ({"smoking": "иногда"}, "smoking"),
    ({"gender": "other"}, "gender"),
    ({"birthdate": "01.02.1990"}, "birthdate"),
    ({"birthdate": (date.today() + timedelta(days=2)).isoformat()}, "birthdate"),
    ({"height": 1000}, "height"),
    ({"weight": "abc"}, "weight"),
    ({"chronic_diseases": [1, 2]}, "chronic_diseases"),
    ({"chronic_diseases": {"a": 1}}, "chronic_diseases"),
    ({"full_name": {"a": 1}}, "full_name"),
])
def test_invalid_values_rejected(body, field):
    with pytest.raises(_InvalidField) as e:
        normalize_profile(body)
    assert e.value.field == field


def test_list_limits():
    data = normalize_profile({"chronic_diseases": [f"Болезнь {i}" for i in range(100)] + ["Болезнь 1"]})
    assert len(data["chronic_diseases"]) == 30
    assert len(normalize_profile({"hereditary": ["x" * 1000]})["hereditary"][0]) == 200


def _post(monkeypatch, body):
    saved = []

    async def fake_run_query(func, *a, **kw):
        saved.append(func)
        return type("R", (), {"data": []})()

    async def consent(user_id):
        return True

    patch_api(monkeypatch, "run_query", fake_run_query)
    patch_api(monkeypatch, "has_consent", consent)

    upserts = []

    class Table:
        def upsert(self, data, on_conflict=None):
            upserts.append(data)
            return self

        def execute(self):
            return type("R", (), {"data": []})()

    import api.profile as profile_module
    monkeypatch.setattr(profile_module, "supabase_client", type("C", (), {"table": lambda self, n: Table()})())

    async def go():
        app = web.Application()
        app.router.add_post("/api/profile/{user_id}", api_profile_post)
        async with TestClient(TestServer(app)) as c:
            r = await c.post("/api/profile/100", json=body,
                             headers={"Authorization": f"Bearer {issue_token(100)}"})
            for f in saved:
                f()
            return r.status, await r.json()

    status, data = asyncio.run(go())
    return status, data, upserts


def test_profile_post_saves_normalized(monkeypatch):
    status, _, upserts = _post(monkeypatch, {"chronic_diseases": "Астма", "smoking": "Не курю"})
    assert status == 200
    assert upserts == [{"chronic_diseases": ["Астма"], "smoking": "no", "user_id": 100}]


def test_profile_post_invalid_field_400(monkeypatch):
    status, data, upserts = _post(monkeypatch, {"smoking": "иногда"})
    assert status == 400 and data == {"error": "invalid_field", "field": "smoking"}
    assert upserts == []
