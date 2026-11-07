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

# Для бессрочных токенов (старые токены метрик) запись об отзыве храним год
_NO_EXP_KEEP = 365 * 24 * 3600
REVOCATION_REFRESH_INTERVAL = 600
REVOCATION_RETRY_INTERVAL = 30  # пока список не загружен — пробуем чаще


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


async def revoke_token(payload: dict) -> None:
    """Отзывает один токен («Выйти» на этом устройстве)."""
    jti = payload.get("jti")
    if not jti:
        # У старых токенов нет jti — отозвать отдельно нельзя, выходим везде
        await revoke_all_tokens([int(payload["uid"])])
        return
    exp = float(payload.get("exp") or (revocation.now_ms() / 1000 + _NO_EXP_KEEP))
    revocation.remember_revoked_token(jti, exp)
    await run_query(
        lambda: supabase_client.table("revoked_tokens")
        .upsert({"jti": jti, "expires_at": _iso(exp)}, on_conflict="jti")
        .execute()
    )


async def revoke_all_tokens(user_ids: list[int]) -> None:
    """Делает недействительными все выданные до этого момента токены пользователей."""
    cutoff = revocation.now_ms()
    for uid in user_ids:
        revocation.remember_cutoff(int(uid), cutoff)
    rows = [{"user_id": int(uid), "not_before_ms": cutoff} for uid in user_ids]
    if rows:
        await run_query(
            lambda: supabase_client.table("token_cutoffs").upsert(rows, on_conflict="user_id").execute()
        )


async def load_revocations() -> None:
    """Загружает отзывы из базы в память (объединяя с уже известными)."""
    now_iso = _iso(revocation.now_ms() / 1000)
    cutoffs = await run_query(lambda: supabase_client.table("token_cutoffs").select("user_id, not_before_ms").execute())
    for row in cutoffs.data or []:
        revocation.remember_cutoff(int(row["user_id"]), int(row["not_before_ms"]))
    tokens = await run_query(
        lambda: supabase_client.table("revoked_tokens").select("jti, expires_at").gt("expires_at", now_iso).execute()
    )
    for row in tokens.data or []:
        exp = datetime.fromisoformat(str(row["expires_at"]).replace("Z", "+00:00")).timestamp()
        revocation.remember_revoked_token(row["jti"], exp)
    revocation.mark_loaded()


async def revocation_sync_loop() -> None:
    """Загружает отзывы при старте и периодически; чистит истёкшие записи."""
    while True:
        try:
            await load_revocations()
            revocation.purge_expired()
            now_iso = _iso(revocation.now_ms() / 1000)
            await run_query(
                lambda: supabase_client.table("revoked_tokens").delete().lt("expires_at", now_iso).execute()
            )
        except Exception as e:
            logger.error(f"Token revocation sync failed: {type(e).__name__}")
        await asyncio.sleep(REVOCATION_REFRESH_INTERVAL if revocation.is_loaded() else REVOCATION_RETRY_INTERVAL)
