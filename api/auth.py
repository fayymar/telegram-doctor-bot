"""HTTP API входа, выхода, согласия и удаления аккаунта."""
from datetime import datetime, timezone

from aiohttp import web

from api.common import (
    _is_rate_limited,
    _rate_limit_response,
    _unauthorized,
    auth_required,
    consent_required,
    json_response,
)
from bot.instance import bot
from bot.shared import redeem_site_code
from database.connection import run_query, supabase_client
from security.auth import (
    SCOPE_METRICS,
    bearer_token,
    decode_token,
    derive_web_user_id,
    issue_token,
    verify_login_widget,
    verify_webapp_init_data,
)
from services.consent import (
    CONSENT_VERSION,
    delete_all_user_data,
    has_consent,
    record_consent,
)
from services.sessions import revoke_all_tokens, revoke_token
from utils.logger import setup_logger

logger = setup_logger(__name__)


async def _redeem_code_from_request(request: web.Request) -> tuple[dict | None, web.Response | None]:
    """Общая часть входа и привязки по коду из бота: лимиты + погашение кода."""
    if _is_rate_limited(request, "code", limit=10, window=60):
        return None, _rate_limit_response()
    try:
        body = await request.json()
    except Exception:
        return None, json_response({"error": "invalid json"}, status=400)
    entry = await redeem_site_code(str(body.get("code", "")) if isinstance(body, dict) else "")
    if not entry:
        return None, json_response({"error": "invalid_code", "message": "Код неверный или истёк"}, status=400)
    return entry, None


def _session_payload(user_id: int, **user_fields) -> dict:
    """Единый формат ответа при успешном входе: токен + данные пользователя."""
    return {
        "token": issue_token(user_id),
        "id": user_id,
        "auth_date": int(datetime.now(timezone.utc).timestamp()),
        **user_fields,
    }


async def api_auth_telegram_webapp(request: web.Request) -> web.Response:
    """
    POST /api/auth/telegram-webapp {"init_data": Telegram.WebApp.initData}
    Вход из Telegram Mini App. Подпись initData проверяется по BOT_TOKEN.
    """
    if _is_rate_limited(request, "auth", limit=20, window=60):
        return _rate_limit_response()
    try:
        body = await request.json()
    except Exception:
        return json_response({"error": "invalid json"}, status=400)
    user = verify_webapp_init_data(str(body.get("init_data", "")))
    if not user:
        return _unauthorized()
    return json_response(_session_payload(
        int(user["id"]),
        first_name=user.get("first_name"),
        last_name=user.get("last_name"),
        username=user.get("username"),
        photo_url=user.get("photo_url"),
        provider="telegram",
    ))


async def api_auth_telegram_widget(request: web.Request) -> web.Response:
    """
    POST /api/auth/telegram-widget {id, first_name, ..., auth_date, hash}
    Вход на сайте через Telegram Login Widget. Подпись проверяется по BOT_TOKEN.
    """
    if _is_rate_limited(request, "auth", limit=20, window=60):
        return _rate_limit_response()
    try:
        body = await request.json()
    except Exception:
        return json_response({"error": "invalid json"}, status=400)
    user = verify_login_widget(body if isinstance(body, dict) else {})
    if not user:
        return _unauthorized()
    return json_response(_session_payload(
        int(user["id"]),
        first_name=user.get("first_name"),
        last_name=user.get("last_name"),
        username=user.get("username"),
        photo_url=user.get("photo_url"),
        provider="telegram",
    ))


async def api_auth_social(request: web.Request) -> web.Response:
    """
    POST /api/auth/social {"access_token": <Supabase session.access_token>}
    Вход через Google/email (Supabase Auth). Токен проверяется у Supabase —
    email/ID из тела запроса больше НЕ принимаются на веру.
    """
    if _is_rate_limited(request, "auth", limit=20, window=60):
        return _rate_limit_response()
    try:
        body = await request.json()
    except Exception:
        return json_response({"error": "invalid json"}, status=400)

    access_token = str(body.get("access_token", "")).strip()
    if not access_token:
        return json_response({"error": "access_token required"}, status=400)

    try:
        auth_resp = await run_query(supabase_client.auth.get_user, access_token)
        sb_user = auth_resp.user if auth_resp else None
    except Exception as e:
        logger.warning(f"Social auth: Supabase token rejected: {type(e).__name__}")
        sb_user = None
    if not sb_user:
        return _unauthorized()

    meta = sb_user.user_metadata or {}
    email = (sb_user.email or "").lower()
    name = str(meta.get("full_name") or meta.get("name") or email.split("@")[0]).strip()
    avatar = meta.get("avatar_url") or meta.get("picture")
    provider = (sb_user.app_metadata or {}).get("provider", "email")
    user_id = derive_web_user_id(sb_user.id)

    first_name = name.split()[0] if name else email.split("@")[0]
    last_name = " ".join(name.split()[1:]) or None

    try:
        existing = await run_query(
            lambda: supabase_client.table("user_profiles")
                .select("user_id").eq("user_id", user_id).limit(1).execute()
        )
        is_new = not existing.data
        if is_new:
            await run_query(
                lambda: supabase_client.table("user_profiles").insert({
                    "user_id": user_id,
                    "full_name": name or first_name,
                    "auth_uid": str(sb_user.id),
                }).execute()
            )
            logger.info(f"Social auth: created user_id={user_id} via {provider}")
        else:
            # Аккаунты, созданные до появления auth_uid: дописываем его, чтобы
            # «Удалить аккаунт» мог удалить и вход Supabase
            await run_query(
                lambda: supabase_client.table("user_profiles")
                    .update({"auth_uid": str(sb_user.id)})
                    .eq("user_id", user_id).is_("auth_uid", "null").execute()
            )
    except Exception as e:
        logger.error(f"Social auth error: {e}", exc_info=True)
        return json_response({"error": "Internal server error"}, status=500)

    return json_response(_session_payload(
        user_id,
        first_name=first_name,
        last_name=last_name,
        username=None,
        photo_url=avatar,
        provider=provider,
        email=email,
        is_new=is_new,
    ))


async def api_auth_code(request: web.Request) -> web.Response:
    """
    POST /api/auth/code {"code": "K7RM-4QXA"} — вход на сайт по коду, который
    бот прислал пользователю в его чат (/login). Код одноразовый, 5 минут.
    """
    entry, error = await _redeem_code_from_request(request)
    if error is not None:
        return error
    logger.info(f"Site code login for telegram user {entry['telegram_id']}")
    return json_response(_session_payload(
        int(entry["telegram_id"]),
        first_name=entry["first_name"],
        last_name=entry["last_name"],
        username=entry["username"],
        photo_url=None,
        provider="telegram",
    ))


_LINK_MERGE_FIELDS = [
    "birthdate", "gender", "height", "weight", "phone",
    "chronic_diseases", "drug_allergies", "smoking", "hereditary", "physical_activity",
]


@auth_required
@consent_required
async def api_auth_link(request: web.Request) -> web.Response:
    """
    POST /api/auth/link {"code": "K7RM-4QXA"} — привязать Telegram к ТЕКУЩЕМУ
    веб-аккаунту кодом из бота. Пустые поля веб-профиля заполняются из
    Telegram-профиля того же человека (код получил владелец Telegram).
    """
    web_id = request["user_id"]
    entry, error = await _redeem_code_from_request(request)
    if error is not None:
        return error
    tg_id = int(entry["telegram_id"])
    if tg_id == web_id:
        return json_response({"error": "Этот аккаунт уже является Telegram-аккаунтом"}, status=400)

    try:
        tg_resp = await run_query(lambda: supabase_client.table("user_profiles").select("*").eq("user_id", tg_id).limit(1).execute())
        web_resp = await run_query(lambda: supabase_client.table("user_profiles").select("*").eq("user_id", web_id).limit(1).execute())
        tg_profile = tg_resp.data[0] if tg_resp.data else {}
        web_profile = web_resp.data[0] if web_resp.data else {}

        update_web = {"linked_telegram_id": str(tg_id)}
        for field in _LINK_MERGE_FIELDS + ["full_name"]:
            if tg_profile.get(field) and not web_profile.get(field):
                update_web[field] = tg_profile[field]

        await run_query(lambda: supabase_client.table("user_profiles").upsert(
            {"user_id": web_id, **update_web}, on_conflict="user_id").execute())
        await run_query(lambda: supabase_client.table("user_profiles").upsert(
            {"user_id": tg_id, "linked_web_id": str(web_id)}, on_conflict="user_id").execute())
    except Exception as e:
        logger.error(f"Account link error: {e}", exc_info=True)
        return json_response({"error": "Internal server error"}, status=500)

    logger.info(f"Accounts linked: tg={tg_id} <-> web={web_id}")
    try:
        await bot.send_message(tg_id, "✅ Ваш Telegram привязан к аккаунту на сайте Symed.")
    except Exception as e:
        logger.warning(f"Link notification failed for {tg_id}: {e}")
    return json_response({"linked": True, "telegram_id": tg_id})


@auth_required
async def api_auth_logout(request: web.Request) -> web.Response:
    """POST /api/auth/logout — отзывает токен этого запроса («Выйти» на этом устройстве)."""
    payload = decode_token(bearer_token(request.headers) or "")
    if payload:
        try:
            await revoke_token(payload)
        except Exception as e:
            # В памяти токен уже отозван; сохранение в базу повторится в фоне
            logger.error(f"Logout persist failed: {type(e).__name__}")
            return json_response({"error": "Service temporarily unavailable"}, status=503)
    return json_response({"ok": True})


@auth_required
async def api_auth_logout_all(request: web.Request) -> web.Response:
    """POST /api/auth/logout-all — отзывает все токены пользователя (все устройства)."""
    ids = [request["user_id"]]
    try:
        await revoke_all_tokens(ids)
    except Exception as e:
        # На этом сервере токены уже не действуют; сохранение в базу повторится в фоне,
        # но сообщаем об ошибке, чтобы пользователь мог повторить
        logger.error(f"Logout-all persist failed: {type(e).__name__}")
        return json_response({"error": "Service temporarily unavailable"}, status=503)
    return json_response({"ok": True})


@auth_required
async def api_auth_me(request: web.Request) -> web.Response:
    """GET /api/auth/me — проверка токена; возвращает user_id владельца."""
    return json_response({"id": request["user_id"]})


@auth_required
async def api_auth_metrics_token(request: web.Request) -> web.Response:
    """
    GET /api/auth/metrics-token — токен ТОЛЬКО для отправки показателей
    (iPhone Shortcut / Apple Watch), действует 180 дней. Им нельзя читать данные.
    """
    token = issue_token(request["user_id"], scope=SCOPE_METRICS, ttl=180 * 24 * 3600)
    return json_response({"token": token, "expires_in": 180 * 24 * 3600})


@auth_required
async def api_consent_get(request: web.Request) -> web.Response:
    """GET /api/consent — дал ли пользователь согласие на текущую версию текста."""
    try:
        accepted = await has_consent(request["user_id"])
    except Exception as e:
        logger.error(f"Consent GET failed: {type(e).__name__}")
        return json_response({"error": "Internal server error"}, status=500)
    return json_response({"accepted": accepted, "version": CONSENT_VERSION})


@auth_required
async def api_consent_post(request: web.Request) -> web.Response:
    """POST /api/consent {"version", "source": "web"|"miniapp"} — фиксирует согласие."""
    if _is_rate_limited(request, "consent", limit=10, window=60):
        return _rate_limit_response()
    try:
        body = await request.json()
    except Exception:
        return json_response({"error": "Invalid JSON"}, status=400)
    if not isinstance(body, dict) or body.get("version") != CONSENT_VERSION:
        return json_response({"error": "outdated_consent_version", "version": CONSENT_VERSION}, status=409)
    source = body.get("source") if body.get("source") in ("web", "miniapp") else "web"
    try:
        await record_consent(request["user_id"], source)
    except Exception as e:
        logger.error(f"Consent POST failed: {type(e).__name__}")
        return json_response({"error": "Internal server error"}, status=500)
    return json_response({"accepted": True, "version": CONSENT_VERSION})


@auth_required
async def api_account_delete(request: web.Request) -> web.Response:
    """DELETE /api/account — удаляет все данные пользователя и отзывает согласие."""
    user_id = request["user_id"]
    try:
        await delete_all_user_data(user_id)
    except Exception as e:
        logger.error(f"Account delete failed: {type(e).__name__}")
        return json_response({"error": "Internal server error"}, status=500)
    return json_response({"deleted": True})
