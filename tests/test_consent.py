import asyncio
from types import SimpleNamespace

from services import consent


def test_delete_all_user_data_covers_every_table(monkeypatch):
    touched = []

    class Q:
        def __init__(self, table):
            self.table = table
        def delete(self):
            return self
        def eq(self, *a):
            return self
        def execute(self):
            touched.append(self.table)
            return SimpleNamespace(data=[])

    monkeypatch.setattr(consent, "supabase_client", SimpleNamespace(table=lambda t: Q(t)))

    async def fake_run_query(func, *a, **kw):
        return func()
    monkeypatch.setattr(consent, "run_query", fake_run_query)

    consent._consent_cache[5] = consent.CONSENT_VERSION
    asyncio.run(consent.delete_all_user_data(5))
    assert set(touched) == {"messages", "consultations", "medications", "health_diary",
                            "health_metrics", "consents", "user_profiles"}
    assert touched[-1] == "user_profiles"
    assert 5 not in consent._consent_cache


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
