"""
Незавершённые диалоги в базе, чтобы они переживали перезапуск сервера.

Бот на бесплатном Render засыпает и перезапускается при каждом обновлении, а
всё, что лежит только в памяти, при этом теряется: начатая консультация на
сайте, код входа на сайт, шаг анкеты или консультации в боте. Здесь эти данные
дублируются в базу:

- в памяти остаётся рабочая копия — чтение быстрое, как раньше;
- каждое изменение пишется в базу в фоне, строго по очереди для каждой записи
  (последнее состояние всегда побеждает), поэтому ответы не замедляются;
- при запуске всё незавершённое подгружается обратно; в базе запись живёт не
  дольше, чем в памяти (консультация — 2 часа, код входа — 5 минут, шаг
  диалога бота — тайм-аут FSM), устаревшие удаляются;
- при удалении аккаунта записи пользователя стираются вместе с остальными
  данными (services/consent.py).

Гостевые консультации на сайте (без входа) в базу НЕ пишутся: политика
конфиденциальности обещает, что их данные есть только в памяти сервера.
"""
import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from database.connection import run_query, supabase_client
from utils.logger import setup_logger

logger = setup_logger(__name__)

# Сколько хранить незавершённое, если хранилище не задало своё: в базе запись
# живёт не дольше, чем в памяти, — лишние данные о здоровье не копятся
KEEP_SECONDS = 24 * 3600
_WRITE_RETRIES = 3
_RETRY_DELAY = 5
_LOAD_PAGE = 1000

# Шаг диалога — единицы КБ. Слишком большой (например, с огромными полями
# профиля) в базу не пишем: он остаётся только в памяти, как раньше
_MAX_PERSISTED_FSM_BYTES = 64 * 1024
# Сколько шагов диалогов поднимать при старте (самые свежие)
_MAX_RESTORED_FSM_STATES = 10_000

# Все хранилища: чтобы разом загрузить, почистить и забыть пользователя
_stores: list = []

# Пользователи, удалившие аккаунт: в базу не пишется ничего из их диалогов,
# пока они заново не дадут согласие И не пройдёт DELETE_GUARD_SECONDS после
# удаления. Обработчик, начатый до удаления (запрос к AI идёт секундами), мог
# бы, закончив, записать данные о здоровье уже удалённого аккаунта — в том
# числе если человек сразу же снова согласился. В памяти работа идёт как обычно.
DELETE_GUARD_SECONDS = 300
_deleted_users: dict[int, dict] = {}  # user_id -> {"at": monotonic, "reconsented": bool}


def mark_user_deleted(user_id: int) -> None:
    """Запрет записи в базу для пользователя (удаление аккаунта)."""
    _deleted_users[int(user_id)] = {"at": time.monotonic(), "reconsented": False}


def clear_user_deleted(user_id: int) -> None:
    """Пользователь снова дал согласие — после паузы диалоги снова сохраняются."""
    entry = _deleted_users.get(int(user_id))
    if entry is not None:
        entry["reconsented"] = True


def _is_deleted(user_id) -> bool:
    if user_id is None:
        return False
    entry = _deleted_users.get(int(user_id))
    if entry is None:
        return False
    if entry["reconsented"] and time.monotonic() - entry["at"] > DELETE_GUARD_SECONDS:
        _deleted_users.pop(int(user_id), None)
        return False
    return True


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _parse_dt(value) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _jsonable(obj: Any) -> Any:
    """Приводит данные к виду, который можно сохранить в jsonb."""
    return json.loads(json.dumps(obj, ensure_ascii=False, default=str))


async def _load_rows(table: str, id_col: str, since: datetime, time_col: str) -> list[dict]:
    """Читает свежие строки таблицы постранично (Supabase отдаёт ≤1000 за раз)."""
    rows: list[dict] = []
    start = 0
    while True:
        page = await run_query(
            lambda s=start: supabase_client.table(table).select("*")
            .gt(time_col, _iso(since)).order(id_col)
            .range(s, s + _LOAD_PAGE - 1).execute()
        )
        data = page.data or []
        if not data:
            return rows
        rows.extend(data)
        start += len(data)


async def _consented_users(user_ids) -> set[int]:
    """Кто из пользователей сейчас дал согласие (текущая версия текста)."""
    from services.consent import CONSENT_VERSION
    ids = sorted({int(u) for u in user_ids if u is not None})
    found: set[int] = set()
    for i in range(0, len(ids), 200):
        chunk = ids[i:i + 200]
        resp = await run_query(
            lambda c=chunk: supabase_client.table("consents").select("user_id")
            .in_("user_id", c).eq("version", CONSENT_VERSION).execute()
        )
        found.update(int(r["user_id"]) for r in (resp.data or []) if r.get("user_id") is not None)
    return found


async def _persist_allowed(user_id) -> bool:
    """
    Можно ли писать данные этого пользователя в базу. Запрет после удаления
    аккаунта (_deleted_users) живёт только в памяти процесса: при двух
    процессах (выкладка на Render) и после перезапуска его не видно. Поэтому
    сверяемся и с базой — удаление аккаунта стирает согласие первым, и без
    действующего согласия данные не пишутся. Ошибку запроса пробрасываем.
    """
    if user_id is None:
        return True
    if _is_deleted(user_id):
        return False
    return int(user_id) in await _consented_users([user_id])


class _Writer:
    """
    Пишет в базу текущее состояние записи. Для каждой записи одновременно идёт
    не больше одной записи в базу; если запись успела измениться, пока шла
    предыдущая, пишется ещё раз — так в базе всегда последнее состояние.
    """

    def __init__(self, table: str, id_col: str, snapshot: Callable[[str], dict | None],
                 require_consent: bool = False):
        self.table = table
        self.id_col = id_col
        self.require_consent = require_consent
        self._snapshot = snapshot  # id -> строка для базы или None (удалить)
        self._dirty: set[str] = set()
        self._tasks: dict[str, asyncio.Task] = {}
        self.persisted: set[str] = set()  # id, которые (вероятно) есть в базе

    def schedule(self, rid: str) -> None:
        self._dirty.add(rid)
        if rid in self._tasks:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return  # вне event loop (тесты синхронного кода) — писать некуда
        self._tasks[rid] = loop.create_task(self._run(rid))

    async def _run(self, rid: str) -> None:
        try:
            while rid in self._dirty:
                self._dirty.discard(rid)
                row = self._snapshot(rid)
                if row is None and rid not in self.persisted:
                    continue  # в базе этой записи нет и не должно быть
                for attempt in range(_WRITE_RETRIES):
                    try:
                        if (row is not None and self.require_consent
                                and not await _persist_allowed(row.get("user_id"))):
                            row = None  # согласия нет — данных в базе быть не должно
                        if row is None and rid not in self.persisted:
                            break
                        if row is None:
                            await run_query(
                                lambda: supabase_client.table(self.table).delete()
                                .eq(self.id_col, rid).execute()
                            )
                            self.persisted.discard(rid)
                        else:
                            await run_query(
                                lambda: supabase_client.table(self.table)
                                .upsert(row, on_conflict=self.id_col).execute()
                            )
                            self.persisted.add(rid)
                        break
                    except Exception as e:
                        logger.warning(
                            f"Persist {self.table} failed (attempt {attempt + 1}): {type(e).__name__}"
                        )
                        if attempt + 1 < _WRITE_RETRIES:
                            await asyncio.sleep(_RETRY_DELAY)
                            # за время ожидания запись могла измениться
                            row = self._snapshot(rid)
        finally:
            self._tasks.pop(rid, None)

    async def wait(self, rids=None) -> None:
        """Дожидается фоновых записей (всех или только указанных id)."""
        while True:
            tasks = [t for r, t in list(self._tasks.items()) if rids is None or r in rids]
            if not tasks:
                return
            await asyncio.gather(*tasks, return_exceptions=True)


class DictStore:
    """
    Словарь в памяти (сессии консультаций, коды входа) с копией в базе.
    После каждого изменения записи вызывайте save(id) — в том числе после
    удаления из словаря: тогда запись удалится и из базы.
    """

    def __init__(
        self,
        items: dict,
        table: str,
        id_col: str,
        to_row: Callable[[str, dict], dict | None],
        from_row: Callable[[dict], tuple[str, dict]],
        owner: Callable[[dict], int | None],
        time_col: str = "created_at",
        keep_seconds: int = KEEP_SECONDS,
        max_items: int | None = None,
        one_per_owner: bool = False,
        require_consent: bool = False,
    ):
        self.items = items
        self.table = table
        self.id_col = id_col
        self.time_col = time_col
        self.keep_seconds = keep_seconds
        self.max_items = max_items
        # у владельца может быть только одна запись (новый код входа отменяет
        # старый): при загрузке остаётся самая новая, остальные удаляются
        self.one_per_owner = one_per_owner
        # восстанавливать только записи пользователей с действующим согласием:
        # строка, попавшая в базу уже после удаления аккаунта (например, другим
        # процессом во время выкладки), не вернётся, а удалится
        self.require_consent = require_consent
        self._to_row = to_row
        self._from_row = from_row
        self._owner = owner
        self._writer = _Writer(table, id_col, self._snapshot, require_consent=require_consent)
        _stores.append(self)

    def _snapshot(self, rid: str) -> dict | None:
        item = self.items.get(rid)
        if item is None or _is_deleted(self._owner(item)):
            return None
        row = self._to_row(rid, item)
        return _jsonable(row) if row is not None else None

    def save(self, rid) -> None:
        self._writer.schedule(str(rid))

    async def load(self) -> int:
        since = _now() - timedelta(seconds=self.keep_seconds)
        rows = await _load_rows(self.table, self.id_col, since, self.time_col)
        rows = sorted(rows, key=lambda r: str(r.get(self.time_col) or ""))  # старые — первыми
        stale: list[str] = []
        if self.one_per_owner:
            newest: dict = {}
            for row in rows:
                rid, item = self._from_row(row)
                owner = self._owner(item)
                if owner in newest:
                    stale.append(newest[owner][0])
                newest[owner] = (rid, row)
            rows = [row for _, row in newest.values()]
        if self.max_items is not None and len(rows) > self.max_items:
            # как и в памяти: при переполнении остаются самые свежие
            rows = rows[-self.max_items:]
        if self.require_consent:
            parsed = [(row, *self._from_row(row)) for row in rows]
            allowed = await _consented_users(self._owner(item) for _, _, item in parsed)
            rows = []
            for row, rid, item in parsed:
                if self._owner(item) in allowed:
                    rows.append(row)
                else:
                    stale.append(rid)
        for row in rows:
            rid, item = self._from_row(row)
            self.items.setdefault(rid, item)
            self._writer.persisted.add(rid)
        for rid in stale:
            # записи нет в памяти — фоновая запись удалит её из базы
            self._writer.persisted.add(rid)
            self.save(rid)
        return len(rows)

    async def purge_old(self) -> None:
        cutoff = _iso(_now() - timedelta(seconds=self.keep_seconds))
        await run_query(
            lambda: supabase_client.table(self.table).delete().lt(self.time_col, cutoff).execute()
        )

    async def delete_now(self, rid) -> None:
        """
        Удаляет запись из базы сразу и сообщает об ошибке (в отличие от save,
        который пишет в фоне). Нужно там, где запись нельзя оставить в базе ни
        на миг: погашенный код входа после перезапуска подгрузился бы снова.
        Запись должна быть уже убрана из словаря.
        """
        rid = str(rid)
        # дождаться фоновой записи (она могла ещё вставлять эту строку) …
        self._writer.schedule(rid)
        await self._writer.wait({rid})
        # … и удалить явно: фоновая запись не сообщает об ошибках
        await run_query(
            lambda: supabase_client.table(self.table).delete().eq(self.id_col, rid).execute()
        )
        self._writer.persisted.discard(rid)

    async def forget_user(self, user_id: int) -> None:
        rids = [rid for rid, item in list(self.items.items()) if self._owner(item) == user_id]
        for rid in rids:
            self.items.pop(rid, None)
            self.save(rid)
        await self._writer.wait(set(rids))

    async def wait(self) -> None:
        await self._writer.wait()


def _key_to_str(key: StorageKey) -> str:
    return json.dumps(
        [key.bot_id, key.chat_id, key.user_id, key.thread_id, key.business_connection_id, key.destiny]
    )


def _str_to_key(value: str) -> StorageKey:
    return StorageKey(*json.loads(value))


class PersistentMemoryStorage(MemoryStorage):
    """FSM-хранилище aiogram: как MemoryStorage, но с копией в таблице fsm_states."""

    table = "fsm_states"

    def __init__(self, keep_seconds: int = KEEP_SECONDS) -> None:
        super().__init__()
        self.keep_seconds = keep_seconds
        self._writer = _Writer(self.table, "key", self._snapshot, require_consent=True)
        _stores.append(self)

    def _snapshot(self, skey: str) -> dict | None:
        key = _str_to_key(skey)
        record = self.storage.get(key)
        if record is None or (record.state is None and not record.data):
            return None
        if _is_deleted(key.user_id):
            return None
        row = _jsonable({
            "key": skey,
            "user_id": key.user_id,
            "state": record.state,
            "data": record.data,
            "updated_at": _iso(_now()),
        })
        size = len(json.dumps(row, ensure_ascii=False).encode())
        if size > _MAX_PERSISTED_FSM_BYTES:
            logger.warning(f"FSM state too large to persist ({size} bytes)")
            return None
        return row

    async def set_state(self, key: StorageKey, state=None) -> None:
        await super().set_state(key, state)
        self._writer.schedule(_key_to_str(key))

    async def set_data(self, key: StorageKey, data: dict[str, Any]) -> None:
        await super().set_data(key, data)
        self._writer.schedule(_key_to_str(key))

    async def load(self) -> int:
        since = _now() - timedelta(seconds=self.keep_seconds)
        rows = await _load_rows(self.table, "key", since, "updated_at")
        if len(rows) > _MAX_RESTORED_FSM_STATES:
            rows = sorted(rows, key=lambda r: str(r.get("updated_at") or ""))[-_MAX_RESTORED_FSM_STATES:]
        # только пользователи с действующим согласием (см. DictStore.require_consent);
        # без согласия в шаге диалога нет данных о здоровье — человек начнёт заново
        allowed = await _consented_users(row.get("user_id") for row in rows)
        dropped = [row["key"] for row in rows if row.get("user_id") not in allowed and row.get("key")]
        rows = [row for row in rows if row.get("user_id") in allowed]
        for skey in dropped:
            self._writer.persisted.add(skey)
            self._writer.schedule(skey)  # записи нет в памяти — удалится из базы
        for row in rows:
            try:
                key = _str_to_key(row["key"])
            except (TypeError, ValueError):
                continue
            record = self.storage[key]
            if record.state is None and not record.data:
                record.state = row.get("state")
                record.data = row.get("data") or {}
            self._writer.persisted.add(row["key"])
        return len(rows)

    async def purge_old(self) -> None:
        cutoff = _iso(_now() - timedelta(seconds=self.keep_seconds))
        await run_query(
            lambda: supabase_client.table(self.table).delete().lt("updated_at", cutoff).execute()
        )

    async def forget_user(self, user_id: int) -> None:
        skeys = []
        for key in [k for k in list(self.storage) if k.user_id == user_id]:
            self.storage.pop(key, None)
            skey = _key_to_str(key)
            skeys.append(skey)
            self._writer.schedule(skey)
        await self._writer.wait(set(skeys))

    async def wait(self) -> None:
        await self._writer.wait()


async def load_all() -> None:
    """Подгружает незавершённое из базы при запуске. Ошибка не мешает старту."""
    for store in _stores:
        try:
            await store.purge_old()
            count = await store.load()
            if count:
                logger.info(f"Restored {count} rows from {store.table}")
        except Exception as e:
            logger.error(f"Restore from {store.table} failed: {type(e).__name__}")


async def purge_old_all() -> None:
    for store in _stores:
        try:
            await store.purge_old()
        except Exception as e:
            logger.error(f"Purge {store.table} failed: {type(e).__name__}")


async def forget_user(user_id: int) -> None:
    """Убирает из памяти незавершённые диалоги пользователя и дожидается, пока
    это дойдёт до базы (чтобы фоновая запись не вернула их после удаления)."""
    mark_user_deleted(user_id)
    for store in _stores:
        await store.forget_user(user_id)


async def wait_all() -> None:
    for store in _stores:
        await store.wait()
