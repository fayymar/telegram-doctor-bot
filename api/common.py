"""Общее для HTTP API: ответы, CORS, лимиты запросов, авторизация, согласие, сессии консультаций."""
import asyncio
import functools
import ipaddress
import json
import time as _time
from collections import defaultdict
from datetime import datetime, timezone

from aiohttp import web

from security.auth import (
    SCOPE_METRICS,
    SCOPE_SESSION,
    bearer_token,
    verify_token,
)
from services.consent import CONSENT_VERSION, has_consent
from services.persistent_state import DictStore, _parse_dt
from utils.logger import setup_logger

logger = setup_logger(__name__)


# Незавершённые консультации: рабочая копия в памяти, копия в базе — чтобы
# консультация пережила перезапуск сервера (services/persistent_state.py).
# После любого изменения сессии вызывайте consultation_store.save(session_id).
consultation_sessions: dict = {}
_MAX_CONSULTATION_SESSIONS = 2000
CONSULTATION_SESSION_TTL = 7200  # незавершённая консультация живёт 2 часа


def _session_to_row(session_id: str, session: dict) -> dict | None:
    # Гостевые консультации в базу не пишем: по политике конфиденциальности
    # их данные есть только в памяти сервера
    if session.get("user_id") is None:
        return None
    data = {k: v for k, v in session.items() if k != "_created_at"}
    created = session.get("_created_at")
    return {
        "session_id": session_id,
        "user_id": session["user_id"],
        "data": data,
        "created_at": created.isoformat() if created else None,
    }


def _session_from_row(row: dict) -> tuple[str, dict]:
    session = dict(row.get("data") or {})
    session["user_id"] = row.get("user_id")
    session["_created_at"] = _parse_dt(row.get("created_at")) or datetime.now(timezone.utc)
    return str(row["session_id"]), session


consultation_store = DictStore(
    consultation_sessions,
    "consultation_sessions",
    "session_id",
    to_row=_session_to_row,
    from_row=_session_from_row,
    owner=lambda s: s.get("user_id"),
    keep_seconds=CONSULTATION_SESSION_TTL,
    max_items=_MAX_CONSULTATION_SESSIONS,
)


# Ссылки на фоновые задачи: без них asyncio может собрать задачу сборщиком мусора
_background_tasks: set = set()


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


_rate_counters: dict = defaultdict(list)  # (bucket, ip) → [timestamps]


def _client_ip(request: web.Request) -> str:
    """
    IP клиента для rate limit. На Render перед приложением стоит Cloudflare,
    который всегда перезаписывает CF-Connecting-IP реальным адресом клиента.
    Другим заголовкам не доверяем: True-Client-IP Cloudflare выставляет только
    на Enterprise-тарифе (иначе пропускает значение клиента), а X-Forwarded-For
    клиент может дописать сам, и его последнее значение — адрес прокси.
    """
    value = request.headers.get("CF-Connecting-IP", "").strip()
    if value:
        try:
            return str(ipaddress.ip_address(value))
        except ValueError:
            pass
    return request.remote or "unknown"


def _is_rate_limited(request: web.Request, bucket: str = "default", limit: int = 60, window: int = 60) -> bool:
    """Простой rate limit по IP в памяти. True — запрос надо отклонить."""
    key = (bucket, _client_ip(request))
    now = _time.time()
    window_start = now - window
    _rate_counters[key] = [t for t in _rate_counters[key] if t > window_start]
    # Чистим устаревшие ключи, чтобы память не росла бесконечно
    if len(_rate_counters) > 10_000:
        stale = [k for k, v in _rate_counters.items() if not v or v[-1] < now - 3600]
        for k in stale:
            del _rate_counters[k]
    if len(_rate_counters[key]) >= limit:
        return True
    _rate_counters[key].append(now)
    return False


def _rate_limit_response() -> web.Response:
    return json_response({"error": "Too many requests. Please slow down."}, status=429)


ALLOWED_ORIGINS = {
    "https://symed-web.vercel.app",
    "https://symed.uz",
    "https://www.symed.uz",
    "https://sympto-med-app.vercel.app",
    "https://telegram-doctor-bot.onrender.com",
}


def _get_cors_headers(request: web.Request) -> dict:
    origin = request.headers.get("Origin", "")
    allowed = origin if origin in ALLOWED_ORIGINS else "https://sympto-med-app.vercel.app"
    return {
        "Access-Control-Allow-Origin": allowed,
        "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
        "Vary": "Origin",
    }


def json_response(data: dict, status: int = 200) -> web.Response:
    # CORS headers are added by cors_middleware — do not set static headers here
    return web.Response(
        text=json.dumps(data, ensure_ascii=False),
        status=status,
        content_type="application/json",
    )


def _unauthorized() -> web.Response:
    return json_response({"error": "unauthorized"}, status=401)


def _forbidden() -> web.Response:
    return json_response({"error": "forbidden"}, status=403)


def _token_user_id(request: web.Request, scopes: tuple[str, ...] = (SCOPE_SESSION,)) -> int | None:
    token = bearer_token(request.headers)
    return verify_token(token, scopes) if token else None


def auth_required(handler):
    """
    Требует валидный токен сессии. Кладёт user_id в request["user_id"].
    Если в URL есть {user_id} — он обязан совпадать с владельцем токена,
    иначе 403 (нельзя читать/менять чужие данные, подставив чужой ID).
    """
    @functools.wraps(handler)
    async def wrapper(request: web.Request) -> web.Response:
        uid = _token_user_id(request)
        if uid is None:
            return _unauthorized()
        path_uid = request.match_info.get("user_id")
        if path_uid is not None:
            try:
                if int(path_uid) != uid:
                    return _forbidden()
            except ValueError:
                return json_response({"error": "invalid user_id"}, status=400)
        request["user_id"] = uid
        return await handler(request)
    return wrapper


async def _consent_withdrawn(session: dict) -> bool:
    """
    Согласие вошедшего пользователя проверено при старте консультации. Если он
    отозвал его (удалил данные) посреди консультации — не продолжаем обработку
    и не сохраняем результат.
    """
    user_id = session.get("user_id")
    return bool(user_id) and not await has_consent(user_id)


def _consent_required_response() -> web.Response:
    return json_response({"error": "consent_required", "consent_version": CONSENT_VERSION}, status=403)


def consent_required(handler):
    """
    Применяется под @auth_required: без согласия на обработку данных о здоровье
    (текущей версии) запись данных запрещена — ответ 403 consent_required.
    """
    @functools.wraps(handler)
    async def wrapper(request: web.Request) -> web.Response:
        try:
            if not await has_consent(request["user_id"]):
                return _consent_required_response()
        except Exception as e:
            logger.error(f"Consent check failed: {type(e).__name__}")
            return json_response({"error": "Internal server error"}, status=500)
        return await handler(request)
    return wrapper


async def _metrics_user_id(request: web.Request, body: dict) -> int | None:
    """
    Для эндпоинтов приёма показателей (iPhone Shortcut / Apple Watch):
    принимает токен сессии ИЛИ специальный токен метрик — из заголовка
    Authorization или из поля "token" в теле (в Shortcuts так проще настроить).
    """
    token = bearer_token(request.headers) or (body.get("token") if isinstance(body, dict) else None)
    if not token:
        return None
    return verify_token(str(token), (SCOPE_SESSION, SCOPE_METRICS))


@web.middleware
async def cors_middleware(request: web.Request, handler):
    cors_headers = _get_cors_headers(request)
    if request.method == "OPTIONS":
        return web.Response(status=204, headers=cors_headers)
    if request.path.startswith("/api/") and _is_rate_limited(request, "api", limit=120, window=60):
        response = _rate_limit_response()
        for key, value in cors_headers.items():
            response.headers[key] = value
        return response
    try:
        response = await handler(request)
    except web.HTTPException as e:
        # aiohttp's own HTTP errors (404, etc.) — still attach CORS headers
        for key, value in cors_headers.items():
            e.headers[key] = value
        raise
    except Exception as e:
        logger.error(f"Unhandled exception in {request.path}: {e}", exc_info=True)
        response = web.Response(
            text=json.dumps({"error": "Internal server error"}, ensure_ascii=False),
            status=500,
            content_type="application/json",
        )
    for key, value in cors_headers.items():
        response.headers[key] = value
    return response


# HTTP сервер для Render (Health check)
async def health_check(request):
    """Endpoint для проверки здоровья сервиса"""
    return web.Response(text="OK", status=200)


def _get_owned_session(request: web.Request, session_id) -> dict | None:
    """
    Возвращает сессию консультации, если она принадлежит текущему пользователю.
    Гостевые сессии (без user_id) доступны по одному session_id (это UUID4).
    """
    if not session_id:
        return None
    session = consultation_sessions.get(str(session_id))
    if not session:
        return None
    owner = session.get("user_id")
    if owner is not None and _token_user_id(request) != owner:
        return None
    return session
