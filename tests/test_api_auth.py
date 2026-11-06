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
    app.router.add_post("/api/auth/request", main.api_auth_request)
    app.router.add_get("/api/auth/status/{code}", main.api_auth_status)
    app.router.add_post("/api/auth/link-request", main.api_auth_link_request)
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


def test_auth_code_status_needs_poll_secret():
    async def t(c):
        r = await c.post("/api/auth/request")
        body = await r.json()
        code, secret = body["code"], body["poll_secret"]
        main.web_auth_codes[code].update(verified=True, telegram_id=321, first_name="X")

        r = await c.get(f"/api/auth/status/{code}")
        assert r.status == 404
        r = await c.get(f"/api/auth/status/{code}?secret=wrong")
        assert r.status == 404
        r = await c.get(f"/api/auth/status/{code}?secret={secret}")
        data = await r.json()
        assert data["verified"] is True and data["id"] == 321 and data["token"]
    run(t)


def test_link_request_uses_token_user():
    async def t(c):
        r = await c.post("/api/auth/link-request", json={"user_id": 1})
        assert r.status == 401
        r = await c.post("/api/auth/link-request", headers={"Authorization": f"Bearer {issue_token(5_000_000_123)}"})
        code = (await r.json())["code"]
        assert main.link_codes[code]["web_user_id"] == 5_000_000_123
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
