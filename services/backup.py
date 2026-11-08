"""
Ежедневная зашифрованная резервная копия базы в Cloudflare R2 (хранилище в ЕС).

Как это работает:
- раз в сутки бот выгружает все постоянные таблицы (через тот же доступ к
  Supabase, что и для работы) и список входов Supabase Auth, сжимает и шифрует;
- шифрование — открытым ключом (X25519 + AES-256-GCM): на сервере лежит только
  ключ для ЗАШИФРОВКИ. Ключ для расшифровки хранится у владельца проекта, на
  сервере и в Cloudflare его нет — украденную копию прочитать нельзя;
- файл кладётся в бакет R2 (S3-совместимый API, подпись AWS SigV4);
- копии старше BACKUP_KEEP_DAYS дней удаляются.

Временные таблицы (незавершённые диалоги, коды входа) не копируются: они живут
минуты-часы и при восстановлении не нужны.

Нужные переменные окружения (без них копирование просто выключено):
  R2_ENDPOINT          https://<account_id>.eu.r2.cloudflarestorage.com
  R2_ACCESS_KEY_ID     ключ API R2 (только этот бакет, чтение и запись)
  R2_SECRET_ACCESS_KEY
  R2_BUCKET            имя бакета
  BACKUP_PUBLIC_KEY    открытый ключ шифрования (scripts/backup_tool.py keygen)
  BACKUP_KEEP_DAYS     сколько дней хранить копии (по умолчанию 30)

Расшифровка: python scripts/backup_tool.py decrypt <файл> <закрытый_ключ>
"""
import asyncio
import gzip
import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, quote, urlsplit
from xml.etree import ElementTree

import aiohttp

from database.connection import run_query, supabase_client
from services.backup_crypto import encrypt, is_valid_public_key
from utils.logger import setup_logger

logger = setup_logger(__name__)

# Таблица -> колонка первичного ключа (для постраничного чтения без пропусков)
BACKUP_TABLES = {
    "user_profiles": "user_id",
    "consents": "id",
    "consultations": "id",
    "messages": "id",
    "medications": "id",
    "health_diary": "id",
    "health_metrics": "id",
    "revoked_tokens": "jti",
    "token_cutoffs": "user_id",
}
PREFIX = "backups/"
_PAGE = 1000
_CHECK_INTERVAL = 3600       # раз в час смотрим, не пора ли сделать копию
_MIN_GAP = timedelta(hours=23)


# ── Подпись запросов к R2 (AWS SigV4) ────────────────────────────────────────

def _quote(value: str, safe: str = "-_.~") -> str:
    return quote(value, safe=safe)


def sign_request(method: str, url: str, payload_hash: str, access_key: str, secret_key: str,
                 now: datetime, region: str = "auto") -> dict:
    """Заголовки с подписью AWS SigV4 для S3-совместимого API (R2)."""
    parts = urlsplit(url)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    datestamp = now.strftime("%Y%m%d")
    headers = {"host": parts.netloc, "x-amz-content-sha256": payload_hash, "x-amz-date": amz_date}
    query = "&".join(f"{_quote(k)}={_quote(v)}" for k, v in sorted(parse_qsl(parts.query, keep_blank_values=True)))
    signed = ";".join(sorted(headers))
    canonical = "\n".join([
        method, parts.path or "/", query,
        "".join(f"{k}:{headers[k]}\n" for k in sorted(headers)),
        signed, payload_hash,
    ])
    scope = f"{datestamp}/{region}/s3/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()])
    key = ("AWS4" + secret_key).encode()
    for part in (datestamp, region, "s3", "aws4_request"):
        key = hmac.new(key, part.encode(), hashlib.sha256).digest()
    signature = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
    return {
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amz_date,
        "Authorization": f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, "
                         f"SignedHeaders={signed}, Signature={signature}",
    }


class R2:
    def __init__(self, endpoint: str, bucket: str, access_key: str, secret_key: str):
        self.base = endpoint.rstrip("/") + "/" + _quote(bucket)
        self.access_key = access_key
        self.secret_key = secret_key

    async def _request(self, method: str, path: str = "", query: str = "", body: bytes = b"") -> bytes:
        url = self.base + ("/" + _quote(path, safe="/-_.~") if path else "") + (f"?{query}" if query else "")
        headers = sign_request(method, url, hashlib.sha256(body).hexdigest(), self.access_key,
                               self.secret_key, datetime.now(timezone.utc))
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as session:
            async with session.request(method, url, data=body or None, headers=headers,
                                       allow_redirects=False) as resp:
                content = await resp.read()
                if resp.status >= 300:
                    # тело ответа R2 не содержит секретов, но и в лог его не пишем целиком
                    raise RuntimeError(f"R2 {method} failed: HTTP {resp.status}")
                return content

    async def put(self, key: str, body: bytes) -> None:
        await self._request("PUT", key, body=body)

    async def delete(self, key: str) -> None:
        await self._request("DELETE", key)

    async def list(self, prefix: str) -> list[str]:
        keys: list[str] = []
        token = None
        while True:
            params = {"list-type": "2", "prefix": prefix}
            if token:
                params["continuation-token"] = token
            query = "&".join(f"{_quote(k)}={_quote(v)}" for k, v in sorted(params.items()))
            root = ElementTree.fromstring(await self._request("GET", query=query))
            ns = {"s3": root.tag.split("}")[0].strip("{")} if root.tag.startswith("{") else {}
            find = (lambda el, tag: el.find(f"s3:{tag}", ns)) if ns else (lambda el, tag: el.find(tag))
            findall = (lambda el, tag: el.findall(f"s3:{tag}", ns)) if ns else (lambda el, tag: el.findall(tag))
            keys.extend(find(c, "Key").text for c in findall(root, "Contents"))
            truncated = find(root, "IsTruncated")
            nxt = find(root, "NextContinuationToken")
            if truncated is None or truncated.text != "true" or nxt is None:
                return keys
            token = nxt.text


# ── Выгрузка ─────────────────────────────────────────────────────────────────

async def _dump_table(table: str, pk: str) -> list[dict]:
    rows: list[dict] = []
    start = 0
    while True:
        page = await run_query(
            lambda s=start: supabase_client.table(table).select("*").order(pk).range(s, s + _PAGE - 1).execute()
        )
        data = page.data or []
        if not data:
            return rows
        rows.extend(data)
        start += len(data)


async def _dump_auth_users() -> list[dict]:
    """Входы Supabase Auth: id, почта, способ входа — чтобы восстановить привязку
    аккаунтов. Паролей API не отдаёт (и не должно)."""
    users: list[dict] = []
    page = 1
    while True:
        batch = await run_query(supabase_client.auth.admin.list_users, page=page, per_page=_PAGE)
        if not batch:
            return users
        if page > 1000:  # защита от бесконечного цикла, если API игнорирует page
            raise RuntimeError("auth users pagination did not terminate")
        for u in batch:
            users.append({
                "id": str(u.id),
                "email": getattr(u, "email", None),
                "phone": getattr(u, "phone", None),
                "created_at": str(getattr(u, "created_at", "") or ""),
                "providers": (getattr(u, "app_metadata", None) or {}).get("providers"),
            })
        if len(batch) < _PAGE:
            return users
        page += 1


async def build_backup() -> bytes:
    data = {"created_at": datetime.now(timezone.utc).isoformat(), "format": 1, "tables": {}}
    for table, pk in BACKUP_TABLES.items():
        data["tables"][table] = await _dump_table(table, pk)
    data["auth_users"] = await _dump_auth_users()
    return gzip.compress(json.dumps(data, ensure_ascii=False, default=str).encode())


def _config() -> dict | None:
    cfg = {
        "endpoint": os.getenv("R2_ENDPOINT", "").strip(),
        "bucket": os.getenv("R2_BUCKET", "").strip(),
        "access_key": os.getenv("R2_ACCESS_KEY_ID", "").strip(),
        "secret_key": os.getenv("R2_SECRET_ACCESS_KEY", "").strip(),
        "public_key": os.getenv("BACKUP_PUBLIC_KEY", "").strip(),
    }
    if not all(cfg.values()):
        return None
    if not cfg["endpoint"].startswith("https://"):
        logger.error("R2_ENDPOINT must start with https://")
        return None
    try:
        cfg["keep_days"] = max(1, int(os.getenv("BACKUP_KEEP_DAYS", "30") or 30))
    except ValueError:
        cfg["keep_days"] = 30
    if not is_valid_public_key(cfg["public_key"]):
        logger.error("BACKUP_PUBLIC_KEY is not a valid key")
        return None
    return cfg


def _key_time(key: str) -> datetime | None:
    """backups/2026-11-08T03-00-00Z.json.gz.enc -> время создания."""
    name = key[len(PREFIX):].split(".")[0]
    try:
        return datetime.strptime(name, "%Y-%m-%dT%H-%M-%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


async def run_backup(cfg: dict, r2: R2 | None = None) -> str:
    """Делает одну копию и удаляет устаревшие. Возвращает имя файла."""
    r2 = r2 or R2(cfg["endpoint"], cfg["bucket"], cfg["access_key"], cfg["secret_key"])
    now = datetime.now(timezone.utc)
    key = f"{PREFIX}{now.strftime('%Y-%m-%dT%H-%M-%SZ')}.json.gz.enc"
    blob = encrypt(await build_backup(), cfg["public_key"])
    await r2.put(key, blob)
    logger.info(f"Backup uploaded: {key} ({len(blob)} bytes)")
    cutoff = now - timedelta(days=cfg["keep_days"])
    for old in await r2.list(PREFIX):
        created = _key_time(old)
        if created and created < cutoff:
            await r2.delete(old)
            logger.info(f"Old backup deleted: {old}")
    return key


async def _last_backup_time(r2: R2) -> datetime | None:
    # Имена «из будущего» не считаем: иначе один такой файл остановил бы копирование
    limit = datetime.now(timezone.utc) + timedelta(minutes=10)
    times = [t for t in (_key_time(k) for k in await r2.list(PREFIX)) if t and t <= limit]
    return max(times) if times else None


async def backup_loop() -> None:
    """Раз в час проверяет, была ли копия за последние сутки; если нет — делает.
    Время последней копии берётся из самого хранилища, поэтому перезапуски и
    «засыпание» сервера на бесплатном Render копирование не сбивают."""
    cfg = _config()
    if not cfg:
        logger.warning("Backups disabled: R2_* / BACKUP_PUBLIC_KEY are not set")
        return
    r2 = R2(cfg["endpoint"], cfg["bucket"], cfg["access_key"], cfg["secret_key"])
    await asyncio.sleep(60)  # не мешаем запуску бота
    while True:
        try:
            last = await _last_backup_time(r2)
            if last is None or datetime.now(timezone.utc) - last > _MIN_GAP:
                await run_backup(cfg, r2)
        except Exception as e:
            logger.error(f"Backup failed: {type(e).__name__}: {str(e)[:200]}")
        await asyncio.sleep(_CHECK_INTERVAL)
