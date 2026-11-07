import asyncio
from types import SimpleNamespace

from services import consent


def _fake_db(monkeypatch, profiles):
    """Минимальная подмена Supabase: profiles — строки user_profiles для поиска привязок."""
    deleted = []
    updated = []

    class Q:
        def __init__(self, table):
            self.table, self.op, self.filters = table, "select", {}
        def select(self, *a):
            return self
        def delete(self):
            self.op = "delete"
            return self
        def update(self, values):
            self.op = "update"
            self.values = values
            return self
        def eq(self, col, val):
            self.filters["eq"] = (col, val)
            return self
        def in_(self, col, vals):
            self.filters["in"] = (col, list(vals))
            return self
        def or_(self, expr):
            self.filters["or"] = expr
            return self
        def execute(self):
            if self.op == "update":
                updated.append((self.table, self.values, self.filters["eq"]))
                return SimpleNamespace(data=[])
            if self.op == "delete":
                deleted.append((self.table, self.filters["in"][1]))
                return SimpleNamespace(data=[])
            if "eq" in self.filters:
                uid = self.filters["eq"][1]
                return SimpleNamespace(data=[p for p in profiles if p["user_id"] == uid])
            uid = self.filters["or"].split(",")[0].split(".eq.")[1]
            return SimpleNamespace(data=[p for p in profiles
                                         if str(p.get("linked_telegram_id")) == uid or str(p.get("linked_web_id")) == uid])

    monkeypatch.setattr(consent, "supabase_client", SimpleNamespace(table=lambda t: Q(t)))

    async def fake_run_query(func, *a, **kw):
        return func()
    monkeypatch.setattr(consent, "run_query", fake_run_query)
    _fake_db.updated = updated
    return deleted


def test_delete_all_user_data_covers_every_table(monkeypatch):
    deleted = _fake_db(monkeypatch, [{"user_id": 5}])
    consent._consent_cache[5] = consent.CONSENT_VERSION
    asyncio.run(consent.delete_all_user_data(5))
    assert {t for t, _ in deleted} == {"messages", "consultations", "medications", "health_diary",
                                       "health_metrics", "consents", "user_profiles"}
    # consents — первой и ещё раз в конце (на случай параллельно вставленного согласия)
    assert deleted[0][0] == "consents" and deleted[-1][0] == "consents"
    assert deleted[-2][0] == "user_profiles"
    assert all(ids == [5] for _, ids in deleted)
    assert 5 not in consent._consent_cache


def test_delete_does_not_touch_linked_account(monkeypatch):
    # веб-аккаунт 900 привязан к Telegram 7: удаление 7 стирает только 7 и разрывает
    # привязку у 900 (код привязки не доказывает, что это один человек)
    profiles = [
        {"user_id": 900, "linked_telegram_id": "7"},
        {"user_id": 7, "linked_web_id": "900"},
    ]
    deleted = _fake_db(monkeypatch, profiles)
    asyncio.run(consent.delete_all_user_data(7))
    assert all(ids == [7] for _, ids in deleted), deleted
    unlinked = {(vals and list(vals)[0], eq) for _, vals, eq in _fake_db.updated}
    assert ("linked_telegram_id", ("linked_telegram_id", "7")) in unlinked
    assert ("linked_web_id", ("linked_web_id", "7")) in unlinked


def test_middleware_lets_free_commands_through():
    from aiogram.types import Chat, Message, User
    from datetime import datetime

    from bot.middlewares import ConsentMiddleware

    def msg(text):
        return Message(message_id=1, date=datetime.now(), chat=Chat(id=1, type="private"),
                       from_user=User(id=1, is_bot=False, first_name="a"), text=text)

    assert ConsentMiddleware._is_free(msg("/start"))
    assert ConsentMiddleware._is_free(msg("/deletedata"))
    assert ConsentMiddleware._is_free(msg("/start@medgg_bot login"))
    assert not ConsentMiddleware._is_free(msg("🩺 Новая консультация"))
    assert not ConsentMiddleware._is_free(msg("болит голова"))


def test_bot_removed_from_group_does_not_delete_data(monkeypatch):
    from bot.handlers import basic

    calls = []

    async def fake_delete(user_id):
        calls.append(user_id)
    monkeypatch.setattr(consent, "delete_all_user_data", fake_delete)

    def update(chat_type):
        return SimpleNamespace(
            chat=SimpleNamespace(type=chat_type),
            from_user=SimpleNamespace(id=42),
            new_chat_member=SimpleNamespace(status="kicked"),
        )

    asyncio.run(basic.on_user_blocked_bot(update("group")))
    asyncio.run(basic.on_user_blocked_bot(update("supergroup")))
    assert calls == []
    asyncio.run(basic.on_user_blocked_bot(update("private")))
    assert calls == [42]


def test_record_consent_is_idempotent_per_version(monkeypatch):
    inserts = []

    class Q:
        def __init__(self, table):
            self.table = table
        def select(self, *a):
            return self
        def eq(self, *a):
            return self
        def limit(self, *a):
            return self
        def insert(self, row):
            inserts.append(row)
            return self
        def execute(self):
            return SimpleNamespace(data=[{"version": consent.CONSENT_VERSION}] if inserts else [])

    monkeypatch.setattr(consent, "supabase_client", SimpleNamespace(table=lambda t: Q(t)))

    async def fake_run_query(func, *a, **kw):
        return func()
    monkeypatch.setattr(consent, "run_query", fake_run_query)

    consent._consent_cache.pop(77, None)
    for _ in range(3):
        asyncio.run(consent.record_consent(77, "web"))
    assert len(inserts) == 1


def test_consent_cache_cleared_after_rows_deleted(monkeypatch):
    # параллельный запрос закэшировал согласие посреди удаления
    deleted = _fake_db(monkeypatch, [{"user_id": 5}])
    real_run = consent.run_query

    async def racing_run_query(func, *a, **kw):
        result = await real_run(func, *a, **kw)
        consent._consent_cache[5] = consent.CONSENT_VERSION
        return result
    monkeypatch.setattr(consent, "run_query", racing_run_query)
    asyncio.run(consent.delete_all_user_data(5))
    assert deleted and 5 not in consent._consent_cache


def test_has_consent_started_before_deletion_does_not_cache(monkeypatch):
    # has_consent прочитал строку до удаления, а ответ пришёл после него
    async def slow_run_query(func, *a, **kw):
        consent._deletions += 1  # удаление произошло, пока шёл запрос
        return SimpleNamespace(data=[{"version": consent.CONSENT_VERSION}])
    monkeypatch.setattr(consent, "run_query", slow_run_query)

    class Q:
        def __getattr__(self, name):
            return lambda *a, **kw: self
    monkeypatch.setattr(consent, "supabase_client", SimpleNamespace(table=lambda t: Q()))
    consent._consent_cache.pop(6, None)
    assert asyncio.run(consent.has_consent(6)) is True
    assert 6 not in consent._consent_cache


def test_record_consent_during_deletion_does_not_cache(monkeypatch):
    class Q:
        def __getattr__(self, name):
            return lambda *a, **kw: self
    monkeypatch.setattr(consent, "supabase_client", SimpleNamespace(table=lambda t: Q()))
    calls = {"n": 0}

    async def run_query(func, *a, **kw):
        calls["n"] += 1
        if calls["n"] == 2:  # вставка согласия; удаление данных проходит в это же время
            consent._deletions += 1
        return SimpleNamespace(data=[])
    monkeypatch.setattr(consent, "run_query", run_query)
    consent._consent_cache.pop(8, None)
    asyncio.run(consent.record_consent(8, "web"))
    assert 8 not in consent._consent_cache


def _fake_db_with_auth(monkeypatch, profiles, auth_users):
    """Supabase с профилями и списком пользователей Auth; собирает удалённые входы."""
    deleted_auth = []

    class Q:
        def __init__(self, table):
            self.table, self.op, self.f = table, "select", {}
        def select(self, *a):
            return self
        def delete(self):
            self.op = "delete"
            return self
        def update(self, values):
            self.op = "update"
            return self
        def eq(self, col, val):
            self.f["eq"] = val
            return self
        def in_(self, col, vals):
            self.f["in"] = list(vals)
            return self
        def or_(self, expr):
            self.f["or"] = expr
            return self
        def execute(self):
            if self.op in ("delete", "update"):
                return SimpleNamespace(data=[])
            if "in" in self.f:
                return SimpleNamespace(data=[p for p in profiles if p["user_id"] in self.f["in"]])
            if "eq" in self.f:
                return SimpleNamespace(data=[p for p in profiles if p["user_id"] == self.f["eq"]])
            return SimpleNamespace(data=[])

    admin = SimpleNamespace(
        list_users=lambda page=None, per_page=None: [SimpleNamespace(id=u) for u in auth_users] if page == 1 else [],
        delete_user=lambda uid: deleted_auth.append(uid),
    )
    monkeypatch.setattr(consent, "supabase_client",
                        SimpleNamespace(table=lambda t: Q(t), auth=SimpleNamespace(admin=admin)))

    async def fake_run_query(func, *a, **kw):
        return func(*a, **kw)
    monkeypatch.setattr(consent, "run_query", fake_run_query)
    return deleted_auth


def test_delete_removes_supabase_login_by_stored_uid(monkeypatch):
    from security.auth import derive_web_user_id
    uid = "11111111-2222-3333-4444-555555555555"
    web_id = derive_web_user_id(uid)
    deleted_auth = _fake_db_with_auth(monkeypatch, [{"user_id": web_id, "auth_uid": uid}], auth_users=[])
    asyncio.run(consent.delete_all_user_data(web_id))
    assert deleted_auth == [uid]


def test_delete_finds_supabase_login_without_stored_uid(monkeypatch):
    from security.auth import derive_web_user_id
    uid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    other = "99999999-8888-7777-6666-555555555555"
    web_id = derive_web_user_id(uid)
    deleted_auth = _fake_db_with_auth(monkeypatch, [{"user_id": web_id}], auth_users=[other, uid])
    asyncio.run(consent.delete_all_user_data(web_id))
    assert deleted_auth == [uid]  # чужой вход не тронут


def test_forged_auth_uid_is_ignored(monkeypatch):
    # в профиле записан чужой UUID (не соответствующий номеру аккаунта) — его не удаляем
    from security.auth import derive_web_user_id
    uid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    victim = "99999999-8888-7777-6666-555555555555"
    web_id = derive_web_user_id(uid)
    deleted_auth = _fake_db_with_auth(monkeypatch, [{"user_id": web_id, "auth_uid": victim}], auth_users=[uid, victim])
    asyncio.run(consent.delete_all_user_data(web_id))
    assert deleted_auth == [uid]


def test_telegram_account_has_no_supabase_login(monkeypatch):
    deleted_auth = _fake_db_with_auth(monkeypatch, [{"user_id": 7}], auth_users=["x"])
    asyncio.run(consent.delete_all_user_data(7))
    assert deleted_auth == []


def test_failed_purge_keeps_supabase_login(monkeypatch):
    # если часть данных не удалилась, вход не удаляем — иначе остаток не найти
    from security.auth import derive_web_user_id
    uid = "11111111-2222-3333-4444-555555555555"
    web_id = derive_web_user_id(uid)
    deleted_auth = _fake_db_with_auth(monkeypatch, [{"user_id": web_id, "auth_uid": uid}], auth_users=[])
    # заставим удаление из user_profiles упасть
    orig_table = consent.supabase_client.table

    def table(name):
        q = orig_table(name)
        if name == "user_profiles":
            orig_delete = q.delete

            def delete():
                orig_delete()
                q.execute = lambda: (_ for _ in ()).throw(RuntimeError("db"))
                return q
            q.delete = delete
        return q
    consent.supabase_client.table = table
    import pytest
    with pytest.raises(RuntimeError):
        asyncio.run(consent.delete_all_user_data(web_id))
    assert deleted_auth == []


def test_auth_lookup_failure_deletes_nothing(monkeypatch):
    # не удалось найти вход Supabase — ничего не удаляем и не отзываем,
    # иначе потеряем auth_uid из профиля, а вход останется
    import pytest
    from services import sessions
    deleted = _fake_db(monkeypatch, [{"user_id": 5}])
    revoked = []

    async def fake_revoke(ids):
        revoked.extend(ids)
    monkeypatch.setattr(sessions, "revoke_all_tokens", fake_revoke)

    async def failing_lookup(ids):
        raise RuntimeError("auth down")
    monkeypatch.setattr(consent, "_auth_uids_for", failing_lookup)
    with pytest.raises(RuntimeError):
        asyncio.run(consent.delete_all_user_data(5))
    assert deleted == [] and _fake_db.updated == [] and revoked == []


def test_partial_failure_keeps_profile_with_auth_uid(monkeypatch):
    # одна таблица не удалилась — профиль (с auth_uid) и вход остаются для повтора
    import pytest
    deleted = _fake_db(monkeypatch, [{"user_id": 5}])
    orig_table = consent.supabase_client.table

    def table(name):
        q = orig_table(name)
        if name == "messages":
            q.execute = lambda: (_ for _ in ()).throw(RuntimeError("db"))
        return q
    consent.supabase_client.table = table
    with pytest.raises(RuntimeError):
        asyncio.run(consent.delete_all_user_data(5))
    assert "user_profiles" not in {t for t, _ in deleted}
    assert "health_diary" in {t for t, _ in deleted}
