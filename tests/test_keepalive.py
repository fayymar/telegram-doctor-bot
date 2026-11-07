import asyncio
from types import SimpleNamespace

import main


def test_ping_database_ok(monkeypatch):
    calls = []

    async def fake_run_query(func, *a, **kw):
        calls.append(func)
        return SimpleNamespace(data=[])
    monkeypatch.setattr(main, "run_query", fake_run_query)
    assert asyncio.run(main._ping_database()) is True
    assert len(calls) == 1


def test_ping_database_failure_does_not_raise(monkeypatch):
    async def failing(func, *a, **kw):
        raise RuntimeError("supabase down")
    monkeypatch.setattr(main, "run_query", failing)
    assert asyncio.run(main._ping_database()) is False
