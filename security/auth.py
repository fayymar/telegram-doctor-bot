"""
Аутентификация для HTTP API.

Схема:
  1. Клиент доказывает личность одним из способов:
     - Telegram Mini App  → подписанная строка initData (HMAC от BOT_TOKEN)
     - Telegram Login Widget на сайте → подписанные поля виджета
     - Google/email через Supabase Auth → access_token, который мы проверяем у Supabase
     - 6-значный код, подтверждённый в боте
  2. Бэкенд выдаёт собственный подписанный токен сессии.
  3. Все запросы к данным пользователя идут с заголовком
     `Authorization: Bearer <token>`; user_id берётся ТОЛЬКО из токена.

Токен — это base64url(JSON payload) + "." + base64url(HMAC-SHA256 подписи).
Без внешних зависимостей, чтобы не раздувать сборку на Render free tier.
"""

import base64
import hashlib
import hmac
import json
import os
import time
from urllib.parse import parse_qsl

from config import BOT_TOKEN

# Секрет для подписи токенов. Если SESSION_SECRET не задан — выводим его из
# BOT_TOKEN (детерминированно), чтобы не требовать новую переменную окружения.
# Смена BOT_TOKEN или SESSION_SECRET разлогинит всех пользователей.
_SECRET = (
    os.getenv("SESSION_SECRET")
    or hmac.new(BOT_TOKEN.encode(), b"symed-session-v1", hashlib.sha256).hexdigest()
).encode()

SESSION_TTL = 30 * 24 * 3600  # 30 дней
TELEGRAM_AUTH_MAX_AGE = 24 * 3600  # подпись Telegram старше суток не принимаем

SCOPE_SESSION = "session"  # полный доступ к данным пользователя
SCOPE_METRICS = "metrics"  # только отправка показателей (iPhone Shortcut / часы)


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _sign(data: bytes) -> str:
    return _b64e(hmac.new(_SECRET, data, hashlib.sha256).digest())


def issue_token(user_id: int, scope: str = SCOPE_SESSION, ttl: int | None = SESSION_TTL) -> str:
    """Создаёт подписанный токен. ttl=None — бессрочный (для токена метрик)."""
    payload = {"uid": int(user_id), "scp": scope, "iat": int(time.time())}
    if ttl is not None:
        payload["exp"] = int(time.time()) + ttl
    body = _b64e(json.dumps(payload, separators=(",", ":")).encode())
    return f"{body}.{_sign(body.encode())}"


def verify_token(token: str, allowed_scopes: tuple[str, ...] = (SCOPE_SESSION,)) -> int | None:
    """Возвращает user_id, если токен валиден и его scope разрешён, иначе None."""
    if not token or token.count(".") != 1:
        return None
    body, sig = token.split(".")
    if not hmac.compare_digest(sig, _sign(body.encode())):
        return None
    try:
        payload = json.loads(_b64d(body))
        uid = int(payload["uid"])
        scope = payload["scp"]
    except (ValueError, KeyError, TypeError):
        return None
    if scope not in allowed_scopes:
        return None
    exp = payload.get("exp")
    if exp is not None and time.time() > exp:
        return None
    return uid


def _fresh(auth_date, max_age: int) -> bool:
    try:
        return 0 <= time.time() - int(auth_date) <= max_age
    except (TypeError, ValueError):
        return False


def verify_webapp_init_data(init_data: str, max_age: int = TELEGRAM_AUTH_MAX_AGE) -> dict | None:
    """
    Проверяет Telegram.WebApp.initData (Mini App).
    https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    Возвращает dict пользователя Telegram или None.
    """
    if not init_data or not isinstance(init_data, str):
        return None
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        return None
    check_string = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received_hash):
        return None
    if not _fresh(pairs.get("auth_date"), max_age):
        return None
    try:
        user = json.loads(pairs.get("user", ""))
        int(user["id"])
    except (ValueError, KeyError, TypeError):
        return None
    return user


def verify_login_widget(data: dict, max_age: int = TELEGRAM_AUTH_MAX_AGE) -> dict | None:
    """
    Проверяет данные Telegram Login Widget.
    https://core.telegram.org/widgets/login#checking-authorization
    Возвращает поля пользователя (без hash) или None.
    """
    if not isinstance(data, dict):
        return None
    fields = {k: v for k, v in data.items() if v is not None}
    received_hash = str(fields.pop("hash", ""))
    if not received_hash:
        return None
    check_string = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret_key = hashlib.sha256(BOT_TOKEN.encode()).digest()
    expected = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received_hash):
        return None
    if not _fresh(fields.get("auth_date"), max_age):
        return None
    try:
        int(fields["id"])
    except (KeyError, TypeError, ValueError):
        return None
    return fields


def derive_web_user_id(supabase_uid: str) -> int:
    """
    Стабильный числовой user_id для веб-пользователя из UUID Supabase Auth.
    Диапазон 5_000_000_000–9_999_999_999, чтобы не пересекаться с Telegram ID.
    ДОЛЖЕН совпадать с deriveUserId() во фронтенде symed-web (src/lib/auth.ts).
    """
    h = int(hashlib.sha256(supabase_uid.encode()).hexdigest()[:12], 16)
    return 5_000_000_000 + (h % 4_999_999_999)


def bearer_token(headers) -> str | None:
    """Достаёт токен из заголовка Authorization: Bearer <token>."""
    value = headers.get("Authorization", "")
    if value.lower().startswith("bearer "):
        return value[7:].strip() or None
    return None
