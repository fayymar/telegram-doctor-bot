"""Проверяем, что API не отдаёт и не меняет чужие данные."""
import asyncio
from types import SimpleNamespace

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

import main
from security.auth import SCOPE_METRICS, issue_token


def _app():
    app = web.Application(middlewares=[main.cors_middleware])
    app.router.add_get("/api/profile/{user_id}", main.api_profile_get)
    app.router.add_post("/api/health/metrics", main.api_health_metrics_post)
    app.router.add_post("/api/auth/code", main.api_auth_code)
    app.router.add_post("/api/auth/link", main.api_auth_link)
    app.router.add_post("/api/consultation/answer", main.api_consultation_answer)
    return app


@pytest.fixture(autouse=True)
def fake_db(monkeypatch):
    async def fake_run_query(func, *a, **kw):
        return SimpleNamespace(data=[{"full_name": "Test"}])
    monkeypatch.setattr(main, "run_query", fake_run_query)
    main._rate_counters.clear()


def run(coro_fn):
    async def go():
        async with TestClient(TestServer(_app())) as client:
            await coro_fn(client)
    asyncio.run(go())


def test_profile_requires_token():
    async def t(c):
        r = await c.get("/api/profile/100")
        assert r.status == 401
    run(t)


def test_profile_other_user_forbidden():
    async def t(c):
        r = await c.get("/api/profile/100", headers={"Authorization": f"Bearer {issue_token(200)}"})
        assert r.status == 403
    run(t)


def test_profile_own_ok():
    async def t(c):
        r = await c.get("/api/profile/100", headers={"Authorization": f"Bearer {issue_token(100)}"})
        assert r.status == 200
        assert (await r.json())["exists"] is True
    run(t)


def test_metrics_token_cannot_read_profile():
    async def t(c):
        tok = issue_token(100, scope=SCOPE_METRICS, ttl=None)
        r = await c.get("/api/profile/100", headers={"Authorization": f"Bearer {tok}"})
        assert r.status == 401
    run(t)


def test_metrics_post_requires_token_and_ignores_body_user_id(monkeypatch):
    saved = {}

    async def fake_run_query(func, *a, **kw):
        saved["called"] = True
        return SimpleNamespace(data=[])
    monkeypatch.setattr(main, "run_query", fake_run_query)

    async def t(c):
        r = await c.post("/api/health/metrics", json={"user_id": 100, "steps": 5000})
        assert r.status == 401
        tok = issue_token(100, scope=SCOPE_METRICS, ttl=None)
        r = await c.post("/api/health/metrics", json={"token": tok, "user_id": 999, "steps": 5000})
        assert r.status == 200
    run(t)


def _tg_user(uid=321):
    return SimpleNamespace(id=uid, first_name="X", last_name=None, username="x")


def test_site_code_login_is_one_time():
    from bot.shared import issue_site_code
    code = issue_site_code(_tg_user())

    async def t(c):
        r = await c.post("/api/auth/code", json={"code": "00000000" if code != "00000000" else "11111111"})
        assert r.status == 400
        r = await c.post("/api/auth/code", json={"code": code})
        data = await r.json()
        assert r.status == 200 and data["id"] == 321 and data["token"]
        r = await c.post("/api/auth/code", json={"code": code})
        assert r.status == 400  # повторно не работает
    run(t)


def test_new_code_invalidates_previous_one_for_same_user():
    from bot.shared import issue_site_code, site_codes
    first = issue_site_code(_tg_user(555))
    second = issue_site_code(_tg_user(555))
    assert first not in site_codes and second in site_codes


def test_code_endpoint_rate_limited():
    async def t(c):
        statuses = [(await c.post("/api/auth/code", json={"code": "12345678"})).status for _ in range(12)]
        assert 429 in statuses
    run(t)


def test_link_requires_session_and_uses_token_user(monkeypatch):
    from bot.shared import issue_site_code
    writes = []

    async def fake_run_query(func, *a, **kw):
        writes.append(func)
        return SimpleNamespace(data=[])
    monkeypatch.setattr(main, "run_query", fake_run_query)

    async def fake_send(*a, **kw):
        return None
    monkeypatch.setattr(main.bot, "send_message", fake_send)

    code = issue_site_code(_tg_user(777))

    async def t(c):
        r = await c.post("/api/auth/link", json={"code": code})
        assert r.status == 401
        web_id = 100_000_000_123
        r = await c.post("/api/auth/link", json={"code": code},
                         headers={"Authorization": f"Bearer {issue_token(web_id)}"})
        data = await r.json()
        assert r.status == 200 and data["telegram_id"] == 777
    run(t)


def test_consultation_session_owned_by_user():
    main.consultation_sessions["s1"] = {"user_id": 100, "questions": [], "answers": []}

    async def t(c):
        r = await c.post("/api/consultation/answer", json={"session_id": "s1", "answers": []})
        assert r.status == 404
        r = await c.post(
            "/api/consultation/answer",
            json={"session_id": "s1", "answers": []},
            headers={"Authorization": f"Bearer {issue_token(100)}"},
        )
        assert r.status == 200
    run(t)


def test_client_ip_prefers_cloudflare_header():
    from aiohttp.test_utils import make_mocked_request
    req = make_mocked_request("GET", "/", headers={
        "CF-Connecting-IP": "1.2.3.4", "X-Forwarded-For": "6.6.6.6, 10.0.0.1"})
    assert main._client_ip(req) == "1.2.3.4"
    # X-Forwarded-For клиент может подделать — не используем его
    req = make_mocked_request("GET", "/", headers={"X-Forwarded-For": "6.6.6.6, 9.9.9.9"})
    assert main._client_ip(req) not in ("6.6.6.6", "9.9.9.9")
    req = make_mocked_request("GET", "/", headers={"CF-Connecting-IP": "not-an-ip"})
    assert main._client_ip(req) != "not-an-ip"
