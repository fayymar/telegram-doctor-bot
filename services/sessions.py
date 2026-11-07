"""
Отзыв токенов сессии с сохранением в базе (таблицы revoked_tokens и
token_cutoffs, см. migration_add_token_revocation.sql).

Сначала отзыв применяется в памяти (security/revocation.py) — он действует
сразу, даже если запись в базу не удалась; база нужна, чтобы отзыв пережил
перезапуск сервера.
"""
import asyncio
from datetime import datetime, timezone

from database.connection import run_query, supabase_client
from security import revocation
from utils.logger import setup_logger

logger = setup_logger(__name__)

# Бессрочный токен (токен метрик) действует всегда, поэтому и запись о его отзыве
# не должна истекать: иначе после чистки старых записей токен снова заработал бы.
# Берём заведомо далёкую дату (01.01.9999), которую чистка никогда не достигнет
_NO_EXP_FOREVER = 253370764800.0
REVOCATION_REFRESH_INTERVAL = 600
REVOCATION_RETRY_INTERVAL = 30  # пока список не загружен — пробуем чаще


# Записи об отзыве, которые не удалось сохранить в базу: повторяем в фоне,
# чтобы отзыв пережил перезапуск сервера
_pending_tokens: dict[str, float] = {}
_pending_cutoffs: dict[int, int] = {}
# Записи в базу идут строго по очереди: иначе более старый момент «выйти везде»
# мог бы записаться после нового и откатить его
_flush_lock = asyncio.Lock()


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


async def revoke_token(payload: dict) -> None:
    """Отзывает один токен («Выйти» на этом устройстве)."""
    jti = payload.get("jti")
    if not jti:
        # У старых токенов нет jti — отозвать отдельно нельзя, выходим везде
        await revoke_all_tokens([int(payload["uid"])])
        return
    exp = float(payload.get("exp") or _NO_EXP_FOREVER)
    revocation.remember_revoked_token(jti, exp)
    _pending_tokens[jti] = exp
    await _flush_pending()


async def revoke_all_tokens(user_ids: list[int]) -> None:
    """Делает недействительными все выданные до этого момента токены пользователей."""
    cutoff = revocation.now_ms()
    for uid in user_ids:
        revocation.remember_cutoff(int(uid), cutoff)
        _pending_cutoffs[int(uid)] = max(cutoff, _pending_cutoffs.get(int(uid), -1))
    await _flush_pending()


async def _flush_pending() -> None:
    """Сохраняет в базу накопленные отзывы. При ошибке они остаются в очереди
    (повтор — в revocation_sync_loop), а исключение пробрасывается."""
    async with _flush_lock:
        await _flush_pending_locked()


async def _flush_pending_locked() -> None:
    if _pending_tokens:
        batch = dict(_pending_tokens)
        rows = [{"jti": j, "expires_at": _iso(e)} for j, e in batch.items()]
        await run_query(lambda: supabase_client.table("revoked_tokens").upsert(rows, on_conflict="jti").execute())
        for j in batch:
            _pending_tokens.pop(j, None)
    if _pending_cutoffs:
        batch = dict(_pending_cutoffs)
        # в базу никогда не пишем меньше, чем уже известно процессу
        rows = [{"user_id": u, "not_before_ms": max(c, revocation.current_cutoff(u))} for u, c in batch.items()]
        await run_query(lambda: supabase_client.table("token_cutoffs").upsert(rows, on_conflict="user_id").execute())
        for u, c in batch.items():
            if _pending_cutoffs.get(u) == c:
                _pending_cutoffs.pop(u, None)


_LOAD_PAGE = 1000  # Supabase по умолчанию отдаёт не больше 1000 строк за запрос


async def _load_all(build_query) -> list[dict]:
    """Читает все строки постранично: без этого отзывы сверх лимита строк
    молча терялись бы при перезапуске. Читаем до пустой страницы, а не до
    неполной: лимит строк в проекте может быть настроен меньше _LOAD_PAGE."""
    rows: list[dict] = []
    start = 0
    while True:
        page = await run_query(lambda s=start: build_query().range(s, s + _LOAD_PAGE - 1).execute())
        data = page.data or []
        if not data:
            return rows
        rows.extend(data)
        start += len(data)


async def load_revocations() -> None:
    """Загружает отзывы из базы в память (объединяя с уже известными)."""
    now_iso = _iso(revocation.now_ms() / 1000)
    cutoffs = await _load_all(
        lambda: supabase_client.table("token_cutoffs").select("user_id, not_before_ms").order("user_id")
    )
    for row in cutoffs:
        revocation.remember_cutoff(int(row["user_id"]), int(row["not_before_ms"]))
    tokens = await _load_all(
        lambda: supabase_client.table("revoked_tokens").select("jti, expires_at").gt("expires_at", now_iso).order("jti")
    )
    for row in tokens:
        exp = datetime.fromisoformat(str(row["expires_at"]).replace("Z", "+00:00")).timestamp()
        revocation.remember_revoked_token(row["jti"], exp)
    revocation.mark_loaded()


async def revocation_sync_loop() -> None:
    """Загружает отзывы при старте и периодически; чистит истёкшие записи."""
    while True:
        try:
            await _flush_pending()
            await load_revocations()
            revocation.purge_expired()
            now_iso = _iso(revocation.now_ms() / 1000)
            await run_query(
                lambda: supabase_client.table("revoked_tokens").delete().lt("expires_at", now_iso).execute()
            )
        except Exception as e:
            logger.error(f"Token revocation sync failed: {type(e).__name__}")
        healthy = revocation.is_loaded() and not _pending_tokens and not _pending_cutoffs
        await asyncio.sleep(REVOCATION_REFRESH_INTERVAL if healthy else REVOCATION_RETRY_INTERVAL)
