"""Фиктивное окружение: тесты не ходят в Telegram, Anthropic и Supabase."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("BOT_TOKEN", "123456789:AAFakeTokenForTestsOnly_xxxxxxxxxxxxx")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
# supabase-py 2.10 принимает только JWT-ключи; это фиктивный JWT с role=service_role
os.environ.setdefault(
    "SUPABASE_KEY",
    "eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.c2lnbmF0dXJl",
)
os.environ.pop("SESSION_SECRET", None)
