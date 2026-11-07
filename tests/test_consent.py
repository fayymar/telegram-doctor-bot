import asyncio
from types import SimpleNamespace

from services import consent


def _fake_db(monkeypatch, profiles):
    """Минимальная подмена Supabase: profiles — строки user_profiles для поиска привязок."""
    deleted = []

    class Q:
        def __init__(self, table):
            self.table, self.op, self.filters = table, "select", {}
        def select(self, *a):
            return self
        def delete(self):
            self.op = "delete"
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
    return deleted


def test_delete_all_user_data_covers_every_table(monkeypatch):
    deleted = _fake_db(monkeypatch, [{"user_id": 5}])
    consent._consent_cache[5] = consent.CONSENT_VERSION
    asyncio.run(consent.delete_all_user_data(5))
    assert {t for t, _ in deleted} == {"messages", "consultations", "medications", "health_diary",
                                       "health_metrics", "consents", "user_profiles"}
    assert deleted[-1][0] == "user_profiles"
    assert all(ids == [5] for _, ids in deleted)
    assert 5 not in consent._consent_cache


def test_delete_all_user_data_includes_linked_accounts(monkeypatch):
    # веб-аккаунт 900 привязан к Telegram 7; посторонний 8 не затрагивается
    profiles = [
        {"user_id": 900, "linked_telegram_id": "7"},
        {"user_id": 7, "linked_web_id": "900"},
        {"user_id": 8},
    ]
    for start in (900, 7):  # и с сайта, и из бота
        deleted = _fake_db(monkeypatch, profiles)
        asyncio.run(consent.delete_all_user_data(start))
        assert all(ids == [7, 900] for _, ids in deleted), deleted


def test_blocking_bot_deletes_only_telegram_account(monkeypatch):
    deleted = _fake_db(monkeypatch, [{"user_id": 7, "linked_web_id": "900"}, {"user_id": 900, "linked_telegram_id": "7"}])
    asyncio.run(consent.delete_all_user_data(7, include_linked=False))
    assert all(ids == [7] for _, ids in deleted)


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

    async def fake_delete(user_id, include_linked=True):
        calls.append((user_id, include_linked))
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
    assert calls == [(42, False)]


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
