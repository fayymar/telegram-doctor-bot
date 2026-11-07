"""Незавершённые диалоги переживают перезапуск сервера (services/persistent_state.py)."""
import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from aiogram.fsm.storage.base import StorageKey

from api.common import consultation_sessions, consultation_store
from bot import shared
from services import persistent_state
from services.persistent_state import PersistentMemoryStorage


class _FakeTable:
    def __init__(self, db, name):
        self.db, self.name = db, name
        self.op, self.filters, self.payload, self.lo, self.hi = "select", [], None, 0, None

    def select(self, *a):
        return self

    def gt(self, col, val):
        self.filters.append((col, ">", val))
        return self

    def lt(self, col, val):
        self.filters.append((col, "<", val))
        return self

    def eq(self, col, val):
        self.filters.append((col, "=", val))
        return self

    def in_(self, col, vals):
        self.filters.append((col, "in", [str(v) for v in vals]))
        return self

    def order(self, *a):
        return self

    def range(self, lo, hi):
        self.lo, self.hi = lo, hi
        return self

    def upsert(self, row, on_conflict):
        self.op, self.payload, self.key = "upsert", row, on_conflict
        return self

    def delete(self):
        self.op = "delete"
        return self

    def _match(self, row):
        for col, op, val in self.filters:
            v = row.get(col)
            if op == "=" and str(v) != str(val):
                return False
            if op == ">" and not (str(v) > str(val)):
                return False
            if op == "<" and not (str(v) < str(val)):
                return False
            if op == "in" and str(v) not in val:
                return False
        return True

    def execute(self):
        rows = self.db.setdefault(self.name, [])
        if self.op == "upsert":
            rows[:] = [r for r in rows if r[self.key] != self.payload[self.key]] + [dict(self.payload)]
            self.db["_writes"].append((self.name, "upsert", self.payload[self.key]))
            return SimpleNamespace(data=[self.payload])
        if self.op == "delete":
            gone = [r for r in rows if self._match(r)]
            rows[:] = [r for r in rows if not self._match(r)]
            self.db["_writes"].append((self.name, "delete", len(gone)))
            return SimpleNamespace(data=gone)
        hit = [r for r in rows if self._match(r)]
        hi = len(hit) if self.hi is None else self.hi + 1
        return SimpleNamespace(data=hit[self.lo:hi])


@pytest.fixture
def db(monkeypatch):
    from services.consent import CONSENT_VERSION
    # согласие есть у всех тестовых пользователей, кроме 666
    data = {"_writes": [], "consents": [{"user_id": u, "version": CONSENT_VERSION}
                                         for u in (1, 5, 7, 42, 55, 77, 78, 80)]}
    monkeypatch.setattr(persistent_state, "supabase_client",
                        SimpleNamespace(table=lambda name: _FakeTable(data, name)))

    async def run_query(func, *a, **kw):
        return func(*a, **kw)
    monkeypatch.setattr(persistent_state, "run_query", run_query)
    consultation_sessions.clear()
    shared.site_codes.clear()
    yield data
    consultation_sessions.clear()
    shared.site_codes.clear()


def _restart():
    """Перезапуск сервера: память пуста, база на месте."""
    consultation_sessions.clear()
    shared.site_codes.clear()
    for store in persistent_state._stores:
        store._writer.persisted.clear()


def test_logged_in_consultation_survives_restart(db):
    async def go():
        consultation_sessions["s1"] = {
            "_created_at": datetime.now(timezone.utc), "user_id": 42,
            "symptoms": "болит горло", "answers": [], "duration": None,
        }
        consultation_store.save("s1")
        consultation_sessions["s1"]["duration"] = "2 дня"
        consultation_store.save("s1")
        await persistent_state.wait_all()
        _restart()
        await consultation_store.load()
    asyncio.run(go())
    s = consultation_sessions["s1"]
    assert s["user_id"] == 42 and s["symptoms"] == "болит горло" and s["duration"] == "2 дня"
    assert isinstance(s["_created_at"], datetime)


def test_guest_consultation_is_never_written(db):
    # политика конфиденциальности: гостевая консультация есть только в памяти
    async def go():
        consultation_sessions["g1"] = {"_created_at": datetime.now(timezone.utc), "user_id": None,
                                       "symptoms": "температура"}
        consultation_store.save("g1")
        consultation_sessions.pop("g1")
        consultation_store.save("g1")
        await persistent_state.wait_all()
    asyncio.run(go())
    assert db["_writes"] == [] and not db.get("consultation_sessions")


def test_finished_consultation_is_removed_from_db(db):
    async def go():
        consultation_sessions["s2"] = {"_created_at": datetime.now(timezone.utc), "user_id": 7}
        consultation_store.save("s2")
        await persistent_state.wait_all()
        consultation_sessions.pop("s2")
        consultation_store.save("s2")
        await persistent_state.wait_all()
    asyncio.run(go())
    assert db["consultation_sessions"] == []


def test_site_code_survives_restart_and_stays_one_time(db):
    user = SimpleNamespace(id=77, first_name="Ann", last_name="", username="ann")

    async def go():
        code = shared.issue_site_code(user)
        await persistent_state.wait_all()
        _restart()
        await shared.site_code_store.load()
        first = await shared.redeem_site_code(code)
        second = await shared.redeem_site_code(code)
        await persistent_state.wait_all()
        return first, second
    first, second = asyncio.run(go())
    assert first["telegram_id"] == 77 and first["username"] == "ann"
    assert second is None
    assert db["site_codes"] == []  # погашенный код удалён и из базы


def test_bot_dialog_step_survives_restart(db):
    key = StorageKey(bot_id=1, chat_id=55, user_id=55)

    async def go():
        fsm = PersistentMemoryStorage()
        await fsm.set_state(key, "Consultation:waiting_for_duration")
        await fsm.set_data(key, {"symptoms": "кашель", "followup_answers": ["да", "нет"]})
        await fsm.wait()
        persistent_state._stores.remove(fsm)
        restarted = PersistentMemoryStorage()
        try:
            await restarted.load()
            return await restarted.get_state(key), await restarted.get_data(key)
        finally:
            persistent_state._stores.remove(restarted)
    state, data = asyncio.run(go())
    assert state == "Consultation:waiting_for_duration"
    assert data == {"symptoms": "кашель", "followup_answers": ["да", "нет"]}


def test_cleared_dialog_is_removed_from_db(db):
    key = StorageKey(bot_id=1, chat_id=56, user_id=56)

    async def go():
        fsm = PersistentMemoryStorage()
        try:
            await fsm.set_state(key, "Profile:waiting_for_name")
            await fsm.wait()
            await fsm.set_state(key, None)
            await fsm.set_data(key, {})
            await fsm.wait()
        finally:
            persistent_state._stores.remove(fsm)
    asyncio.run(go())
    assert db["fsm_states"] == []


def test_latest_state_wins_when_writes_overlap(db, monkeypatch):
    # первая запись в базу медленная; пока она идёт, состояние меняется дважды —
    # в базе должно оказаться последнее, а не первое
    real = persistent_state.run_query
    calls = {"n": 0}

    async def slow_first(func, *a, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            await asyncio.sleep(0.05)
        return await real(func, *a, **kw)
    monkeypatch.setattr(persistent_state, "run_query", slow_first)
    key = StorageKey(bot_id=1, chat_id=57, user_id=57)

    async def go():
        fsm = PersistentMemoryStorage()
        try:
            await fsm.set_data(key, {"step": 1})
            await asyncio.sleep(0.01)
            await fsm.set_data(key, {"step": 2})
            await fsm.set_data(key, {"step": 3})
            await fsm.wait()
        finally:
            persistent_state._stores.remove(fsm)
    asyncio.run(go())
    assert [r["data"] for r in db["fsm_states"]] == [{"step": 3}]


def test_rows_older_than_a_day_are_not_restored(db):
    old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    db["consultation_sessions"] = [{"session_id": "old", "user_id": 1, "data": {}, "created_at": old}]

    async def go():
        await persistent_state.load_all()
    asyncio.run(go())
    assert "old" not in consultation_sessions
    assert db["consultation_sessions"] == []  # и удалена из базы


def test_failed_db_write_does_not_break_the_dialog(db, monkeypatch):
    monkeypatch.setattr(persistent_state, "_RETRY_DELAY", 0)

    async def down(func, *a, **kw):
        raise RuntimeError("db down")
    monkeypatch.setattr(persistent_state, "run_query", down)
    key = StorageKey(bot_id=1, chat_id=58, user_id=58)

    async def go():
        fsm = PersistentMemoryStorage()
        try:
            await fsm.set_data(key, {"step": 1})
            await fsm.wait()
            return await fsm.get_data(key)
        finally:
            persistent_state._stores.remove(fsm)
    assert asyncio.run(go()) == {"step": 1}


def test_restore_keeps_memory_limit_and_ttl(db, monkeypatch):
    # при запуске не больше лимита сессий в памяти (самые свежие) и только моложе 2 часов
    monkeypatch.setattr(consultation_store, "max_items", 2)
    now = datetime.now(timezone.utc)
    db["consultation_sessions"] = [
        {"session_id": f"s{i}", "user_id": 1, "data": {},
         "created_at": (now - timedelta(minutes=10 * i)).isoformat()}
        for i in range(4)
    ] + [{"session_id": "stale", "user_id": 1, "data": {},
          "created_at": (now - timedelta(hours=3)).isoformat()}]

    async def go():
        await consultation_store.load()
    asyncio.run(go())
    assert set(consultation_sessions) == {"s0", "s1"}


def test_redeemed_code_cannot_come_back_after_restart(db):
    # код погашен; сразу «перезапуск» — в базе его быть не должно уже в момент входа
    user = SimpleNamespace(id=78, first_name="", last_name="", username="")

    async def go():
        code = shared.issue_site_code(user)  # фоновая запись ещё не дошла до базы
        assert await shared.redeem_site_code(code)
        _restart()  # без ожидания фоновых записей
        await shared.site_code_store.load()
        return await shared.redeem_site_code(code)
    assert asyncio.run(go()) is None
    assert db["site_codes"] == []


def test_code_is_refused_if_db_delete_fails(db, monkeypatch):
    # не удалось погасить код в базе — не пускаем (иначе его можно повторить)
    user = SimpleNamespace(id=79, first_name="", last_name="", username="")
    monkeypatch.setattr(persistent_state, "_RETRY_DELAY", 0)

    async def go():
        code = shared.issue_site_code(user)
        await persistent_state.wait_all()

        async def down(func, *a, **kw):
            raise RuntimeError("db down")
        monkeypatch.setattr(persistent_state, "run_query", down)
        return await shared.redeem_site_code(code)
    assert asyncio.run(go()) is None


def test_no_db_write_for_user_right_after_account_deletion(db):
    # обработчик, начатый до удаления, дописывает данные уже после него —
    # в базу они попасть не должны
    key = StorageKey(bot_id=1, chat_id=90, user_id=90)

    async def go():
        fsm = PersistentMemoryStorage()
        try:
            await persistent_state.forget_user(90)
            await fsm.set_data(key, {"symptoms": "после удаления"})
            consultation_sessions["late"] = {"_created_at": datetime.now(timezone.utc), "user_id": 90}
            consultation_store.save("late")
            await persistent_state.wait_all()
        finally:
            persistent_state._stores.remove(fsm)
    asyncio.run(go())
    assert not db.get("fsm_states") and not db.get("consultation_sessions")


def test_oversized_session_stays_in_memory_only(db):
    async def go():
        consultation_sessions["big"] = {"_created_at": datetime.now(timezone.utc), "user_id": 5,
                                        "user_profile": {"notes": "x" * 200_000}}
        consultation_store.save("big")
        await persistent_state.wait_all()
    asyncio.run(go())
    assert not db.get("consultation_sessions")
    assert "big" in consultation_sessions


def test_dialogs_saved_again_after_new_consent(db, monkeypatch):
    # после удаления запись в базу выключена, пока человек снова не согласится
    from services import consent
    key = StorageKey(bot_id=1, chat_id=91, user_id=91)

    async def fake_has(uid):
        return False

    async def fake_rq(func, *a, **kw):
        return SimpleNamespace(data=[])
    monkeypatch.setattr(consent, "has_consent", fake_has)
    monkeypatch.setattr(consent, "run_query", fake_rq)

    async def go():
        fsm = PersistentMemoryStorage()
        try:
            await persistent_state.forget_user(91)
            await fsm.set_data(key, {"step": "до согласия"})
            await fsm.wait()
            assert not db.get("fsm_states")
            await consent.record_consent(91, "bot")
            # сразу после согласия — ещё пауза (старые запросы могли не закончиться)
            await fsm.set_data(key, {"step": "сразу после согласия"})
            await fsm.wait()
            assert not db.get("fsm_states")
            monkeypatch.setattr(persistent_state, "DELETE_GUARD_SECONDS", -1)
            await fsm.set_data(key, {"step": "после согласия"})
            await fsm.wait()
        finally:
            persistent_state._stores.remove(fsm)
    asyncio.run(go())
    assert [r["data"] for r in db["fsm_states"]] == [{"step": "после согласия"}]


def test_rotated_code_does_not_come_back_after_restart(db):
    # новый код отменяет старый; если удаление старого не дошло до базы,
    # после перезапуска должен действовать только последний
    now = datetime.now(timezone.utc)
    db["site_codes"] = [
        {"code": "OLDOLD22", "user_id": 80, "data": {}, "created_at": (now - timedelta(seconds=60)).isoformat()},
        {"code": "NEWNEW33", "user_id": 80, "data": {}, "created_at": (now - timedelta(seconds=10)).isoformat()},
    ]

    async def go():
        await shared.site_code_store.load()
        old = await shared.redeem_site_code("OLDOLD22")
        await persistent_state.wait_all()
        return old
    assert asyncio.run(go()) is None
    assert set(shared.site_codes) == {"NEWNEW33"}
    assert [r["code"] for r in db["site_codes"]] == ["NEWNEW33"]


def test_oversized_dialog_step_stays_in_memory_only(db):
    key = StorageKey(bot_id=1, chat_id=92, user_id=92)

    async def go():
        fsm = PersistentMemoryStorage()
        try:
            await fsm.set_data(key, {"user_profile": {"notes": "x" * 200_000}})
            await fsm.wait()
            return await fsm.get_data(key)
        finally:
            persistent_state._stores.remove(fsm)
    data = asyncio.run(go())
    assert not db.get("fsm_states") and len(data["user_profile"]["notes"]) == 200_000


def test_consent_given_during_deletion_does_not_reenable_saving(db, monkeypatch):
    # согласие пришло, пока шло удаление: удаление его же и стирает,
    # поэтому запрет записи в базу должен остаться
    from services import consent
    monkeypatch.setattr(persistent_state, "DELETE_GUARD_SECONDS", -1)

    async def no_consent(uid):
        return False
    monkeypatch.setattr(consent, "has_consent", no_consent)

    async def rq(func, *a, **kw):
        return SimpleNamespace(data=[])
    monkeypatch.setattr(consent, "run_query", rq)

    async def auth_uids(ids):
        return {}
    monkeypatch.setattr(consent, "_auth_uids_for", auth_uids)

    async def revoke(ids):
        pass
    from services import sessions
    monkeypatch.setattr(sessions, "revoke_all_tokens", revoke)

    real_inner = consent._delete_all_user_data_inner

    async def inner_with_consent(user_id, ids, auth):
        await consent.record_consent(user_id, "web")  # параллельный POST /api/consent
        return await real_inner(user_id, ids, auth)
    monkeypatch.setattr(consent, "_delete_all_user_data_inner", inner_with_consent)

    asyncio.run(consent.delete_all_user_data(93))
    assert persistent_state._is_deleted(93)


def test_rows_of_users_without_consent_are_not_restored(db):
    # строка, попавшая в базу после удаления аккаунта (согласия уже нет), при
    # запуске не восстанавливается и удаляется
    now = datetime.now(timezone.utc).isoformat()
    db["consultation_sessions"] = [
        {"session_id": "ok", "user_id": 42, "data": {}, "created_at": now},
        {"session_id": "gone", "user_id": 666, "data": {"symptoms": "x"}, "created_at": now},
    ]
    db["fsm_states"] = [
        {"key": '[1, 55, 55, null, null, "default"]', "user_id": 55, "state": "S", "data": {}, "updated_at": now},
        {"key": '[1, 666, 666, null, null, "default"]', "user_id": 666, "state": "S",
         "data": {"symptoms": "x"}, "updated_at": now},
    ]

    async def go():
        fsm = PersistentMemoryStorage()
        try:
            await persistent_state.load_all()
            await persistent_state.wait_all()
            return await fsm.get_state(StorageKey(1, 666, 666)), await fsm.get_state(StorageKey(1, 55, 55))
        finally:
            persistent_state._stores.remove(fsm)
    gone_state, ok_state = asyncio.run(go())
    assert set(consultation_sessions) == {"ok"}
    assert [r["session_id"] for r in db["consultation_sessions"]] == ["ok"]
    assert gone_state is None and ok_state == "S"
    assert [r["user_id"] for r in db["fsm_states"]] == [55]
