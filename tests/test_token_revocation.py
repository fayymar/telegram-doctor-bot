import asyncio

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

import main
from security import revocation
from security.auth import SCOPE_METRICS, decode_token, issue_token, verify_token
from services import sessions


def test_new_tokens_carry_jti_and_ms_timestamp():
    payload = decode_token(issue_token(5))
    assert payload["jti"] and isinstance(payload["iatm"], int)


def test_revoke_single_token_keeps_other_devices():
    t1, t2 = issue_token(5), issue_token(5)
    asyncio.run(sessions.revoke_token(decode_token(t1)))
    assert verify_token(t1) is None
    assert verify_token(t2) == 5


def test_revoke_all_kills_existing_but_not_new_tokens():
    old = issue_token(5)
    metrics = issue_token(5, scope=SCOPE_METRICS, ttl=None)
    other = issue_token(6)
    asyncio.run(sessions.revoke_all_tokens([5]))
    assert verify_token(old) is None
    assert verify_token(metrics, (SCOPE_METRICS,)) is None
    assert verify_token(other) == 6
    fresh = issue_token(5)
    assert verify_token(fresh) == 5


def test_legacy_token_without_jti_is_revoked_by_cutoff():
    # старый формат: только iat (сек), без jti/iatm
    import json, time
    from security import auth
    body = auth._b64e(json.dumps({"uid": 9, "scp": "session", "iat": int(time.time()) - 5}).encode())
    legacy = f"{body}.{auth._sign(body.encode())}"
    assert verify_token(legacy) == 9
    asyncio.run(sessions.revoke_token(decode_token(legacy)))  # нет jti -> выход везде
    assert verify_token(legacy) is None


class _FakeTable:
    """Таблица Supabase для load_revocations: select/gt/order/range/execute."""

    def __init__(self, rows):
        self.rows, self.lo, self.hi = rows, 0, None

    def select(self, *a):
        return self

    def gt(self, *a):
        return self

    def order(self, *a):
        return self

    def range(self, lo, hi):
        self.lo, self.hi = lo, hi
        return self

    def execute(self):
        # как PostgREST: не больше 1000 строк за запрос, даже без range
        hi = len(self.rows) if self.hi is None else self.hi + 1
        return type("R", (), {"data": self.rows[self.lo:min(hi, self.lo + 1000)]})()


def _fake_revocation_db(monkeypatch, cutoffs=(), tokens=()):
    from types import SimpleNamespace
    tables = {"token_cutoffs": list(cutoffs), "revoked_tokens": list(tokens)}
    monkeypatch.setattr(sessions, "supabase_client", SimpleNamespace(table=lambda t: _FakeTable(tables[t])))

    async def fake_run_query(func, *a, **kw):
        return func()
    monkeypatch.setattr(sessions, "run_query", fake_run_query)


def test_revocations_survive_restart(monkeypatch):
    # после перезапуска состояние в памяти пустое и берётся из базы
    tok = issue_token(5)
    cutoff = revocation.now_ms()
    revocation._reset_for_tests()
    _fake_revocation_db(monkeypatch, cutoffs=[{"user_id": 5, "not_before_ms": cutoff}])
    assert verify_token(tok) == 5
    asyncio.run(sessions.load_revocations())
    assert verify_token(tok) is None


def test_revocations_load_beyond_row_limit(monkeypatch):
    # Supabase отдаёт максимум 1000 строк за запрос — загрузка идёт постранично
    toks = [issue_token(5) for _ in range(3)]
    payloads = [decode_token(t) for t in toks]
    exp = "2099-01-01T00:00:00+00:00"
    rows = [{"jti": f"filler{i}", "expires_at": exp} for i in range(2 * sessions._LOAD_PAGE)]
    rows += [{"jti": p["jti"], "expires_at": exp} for p in payloads]
    revocation._reset_for_tests()
    _fake_revocation_db(monkeypatch, tokens=rows)
    asyncio.run(sessions.load_revocations())
    assert all(verify_token(t) is None for t in toks)


import pytest


def _app():
    app = web.Application()
    app.router.add_post("/api/auth/logout", main.api_auth_logout)
    app.router.add_post("/api/auth/logout-all", main.api_auth_logout_all)
    app.router.add_get("/api/auth/me", main.api_auth_me)
    return app


def _run(fn):
    async def go():
        client = TestClient(TestServer(_app()))
        await client.start_server()
        try:
            await fn(client)
        finally:
            await client.close()
    asyncio.run(go())


def test_logout_endpoint_revokes_only_this_token():
    t1, t2 = issue_token(5), issue_token(5)

    async def t(c):
        r = await c.post("/api/auth/logout", headers={"Authorization": f"Bearer {t1}"})
        assert r.status == 200
        r = await c.get("/api/auth/me", headers={"Authorization": f"Bearer {t1}"})
        assert r.status == 401
        r = await c.get("/api/auth/me", headers={"Authorization": f"Bearer {t2}"})
        assert r.status == 200
    _run(t)


def test_logout_all_endpoint():
    t1, t2 = issue_token(5), issue_token(5)

    async def t(c):
        r = await c.post("/api/auth/logout-all", headers={"Authorization": f"Bearer {t1}"})
        assert r.status == 200
        for tok in (t1, t2):
            r = await c.get("/api/auth/me", headers={"Authorization": f"Bearer {tok}"})
            assert r.status == 401
    _run(t)


def test_account_deletion_revokes_tokens(monkeypatch):
    from services import consent
    from types import SimpleNamespace

    class Q:
        def __getattr__(self, name):
            return lambda *a, **kw: self
        def execute(self):
            return SimpleNamespace(data=[])
    monkeypatch.setattr(consent, "supabase_client", SimpleNamespace(table=lambda t: Q()))

    async def fake_run_query(func, *a, **kw):
        return func(*a, **kw)
    monkeypatch.setattr(consent, "run_query", fake_run_query)
    tok = issue_token(7)
    asyncio.run(consent.delete_all_user_data(7))
    assert verify_token(tok) is None


def test_tokens_issued_before_start_rejected_until_revocations_loaded():
    import time
    old = issue_token(5)
    time.sleep(0.005)
    revocation._reset_for_tests(loaded=False)  # «перезапуск», база ещё не прочитана
    assert verify_token(old) is None
    fresh = issue_token(5)  # выдан после старта — принимается
    assert verify_token(fresh) == 5
    asyncio.run(sessions.load_revocations())
    assert verify_token(old) == 5  # отзывов нет — старый токен снова действует


def test_failed_persist_is_retried(monkeypatch):
    calls = {"fail": True, "writes": 0}

    async def flaky_run_query(func, *a, **kw):
        if calls["fail"]:
            raise RuntimeError("db down")
        calls["writes"] += 1
        return type("R", (), {"data": []})()
    monkeypatch.setattr(sessions, "run_query", flaky_run_query)

    tok = issue_token(5)
    try:
        asyncio.run(sessions.revoke_token(decode_token(tok)))
    except RuntimeError:
        pass
    assert verify_token(tok) is None          # отозван сразу, в памяти
    assert sessions._pending_tokens           # ждёт записи в базу
    calls["fail"] = False
    asyncio.run(sessions._flush_pending())    # фоновый повтор
    assert not sessions._pending_tokens and calls["writes"] == 1


def test_logout_all_reports_failure(monkeypatch):
    async def failing(*a, **kw):
        raise RuntimeError("db down")
    monkeypatch.setattr(sessions, "run_query", failing)
    t1 = issue_token(5)

    async def t(c):
        r = await c.post("/api/auth/logout-all", headers={"Authorization": f"Bearer {t1}"})
        assert r.status == 503
        r = await c.get("/api/auth/me", headers={"Authorization": f"Bearer {t1}"})
        assert r.status == 401  # на этом сервере токен уже не действует
    _run(t)


def test_concurrent_logout_all_keeps_latest_cutoff(monkeypatch):
    # две «выйти везде» подряд, первая запись в базу медленная: итог в базе должен
    # быть от последнего вызова, а не откатиться к первому
    captured = []

    class Q:
        def upsert(self, rows, **kw):
            captured.append(rows)
            return self

        def execute(self):
            return None
    monkeypatch.setattr(sessions, "supabase_client", type("C", (), {"table": staticmethod(lambda t: Q())})())

    calls = {"n": 0}

    async def run_query(func, *a, **kw):
        calls["n"] += 1
        await asyncio.sleep(0.05 if calls["n"] == 1 else 0)  # первая запись медленная
        func()
        return type("R", (), {"data": []})()
    monkeypatch.setattr(sessions, "run_query", run_query)

    async def scenario():
        first = asyncio.create_task(sessions.revoke_all_tokens([5]))
        await asyncio.sleep(0.01)
        await sessions.revoke_all_tokens([5])
        await first
    asyncio.run(scenario())
    final = [r for batch in captured for r in batch if r["user_id"] == 5][-1]["not_before_ms"]
    assert final == revocation._cutoff_ms[5]
