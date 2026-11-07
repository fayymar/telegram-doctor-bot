"""
Shared in-memory state между main.py и bot handlers.

Вход на сайт и привязка аккаунтов работают по коду, который ВЫДАЁТ БОТ
пользователю в его собственный чат, а пользователь вводит его на сайте.
Так код всегда принадлежит тому Telegram-аккаунту, который его получил:
чужая ссылка на бота не может ни залогинить злоумышленника под жертвой,
ни скопировать профиль жертвы в чужой аккаунт.
"""
import secrets
import time
from datetime import datetime, timezone

from services.persistent_state import DictStore, _parse_dt
from utils.logger import setup_logger

logger = setup_logger(__name__)

SITE_CODE_TTL = 300  # код действует 5 минут
# 8 символов без похожих (0/O, 1/I/L): 31^8 ≈ 8.5·10^11 вариантов. При лимите
# 10 попыток в минуту на IP подобрать чужой код за 5 минут нереально даже с
# тысячами адресов, поэтому общая блокировка входа (которой можно было бы
# «положить» вход всем) не нужна.
SITE_CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
SITE_CODE_LEN = 8

# code -> {telegram_id, first_name, last_name, username, created_at}
# Копия в базе — чтобы выданный код работал и после перезапуска сервера.
# После любого изменения вызывайте site_code_store.save(code).
site_codes: dict = {}


def _code_to_row(code: str, entry: dict) -> dict:
    return {
        "code": code,
        "user_id": entry["telegram_id"],
        "data": {k: entry.get(k, "") for k in ("first_name", "last_name", "username")},
        "created_at": datetime.fromtimestamp(entry["created_at"], tz=timezone.utc).isoformat(),
    }


def _code_from_row(row: dict) -> tuple[str, dict]:
    data = row.get("data") or {}
    created = _parse_dt(row.get("created_at"))
    return str(row["code"]), {
        "telegram_id": int(row["user_id"]),
        "first_name": data.get("first_name", ""),
        "last_name": data.get("last_name", ""),
        "username": data.get("username", ""),
        "created_at": created.timestamp() if created else 0.0,
    }


site_code_store = DictStore(
    site_codes,
    "site_codes",
    "code",
    to_row=_code_to_row,
    from_row=_code_from_row,
    owner=lambda e: e.get("telegram_id"),
    keep_seconds=SITE_CODE_TTL,
    one_per_owner=True,  # действует только последний выданный код
)


def _purge_expired_site_codes() -> None:
    now = time.time()
    for code, entry in list(site_codes.items()):
        if now - entry["created_at"] > SITE_CODE_TTL:
            site_codes.pop(code, None)
            site_code_store.save(code)


def issue_site_code(telegram_user) -> str:
    """
    Создаёт одноразовый код для входа/привязки на сайте для данного
    Telegram-пользователя. Предыдущий код этого пользователя аннулируется.
    """
    _purge_expired_site_codes()
    for code, entry in list(site_codes.items()):
        if entry["telegram_id"] == telegram_user.id:
            site_codes.pop(code, None)
            site_code_store.save(code)
    while True:
        code = "".join(secrets.choice(SITE_CODE_ALPHABET) for _ in range(SITE_CODE_LEN))
        if code not in site_codes:
            break
    site_codes[code] = {
        "telegram_id": telegram_user.id,
        "first_name": telegram_user.first_name or "",
        "last_name": telegram_user.last_name or "",
        "username": telegram_user.username or "",
        "created_at": time.time(),
    }
    site_code_store.save(code)
    return code


# Кириллические буквы, похожие на латинские: пользователь мог набрать код
# в русской раскладке
_CYRILLIC_LOOKALIKES = str.maketrans("АВЕКМНРСТХУ", "ABEKMHPCTXY")


def normalize_site_code(code: str) -> str:
    """
    Приводит введённый код к каноническому виду: 'k7rm-4qxa' → 'K7RM4QXA'.
    Убирает пробелы и дефисы, заменяет похожую кириллицу на латиницу.
    """
    up = str(code or "").upper().translate(_CYRILLIC_LOOKALIKES)
    return "".join(ch for ch in up if ch in SITE_CODE_ALPHABET)


async def redeem_site_code(code: str) -> dict | None:
    """Погашает код (одноразово). Возвращает данные Telegram-пользователя или None."""
    code = normalize_site_code(code)
    entry = site_codes.pop(code, None)
    if not entry:
        return None
    # Гасим и в базе ДО входа: иначе после перезапуска сервера код подгрузился
    # бы снова и сработал второй раз. Не удалось — не пускаем (код уже погашен
    # в памяти, человек просто запросит новый)
    try:
        await site_code_store.delete_now(code)
    except Exception as e:
        logger.error(f"Site code redeem: DB delete failed: {type(e).__name__}")
        return None
    if time.time() - entry["created_at"] > SITE_CODE_TTL:
        return None
    return entry


def site_code_message(code: str) -> str:
    """Текст сообщения с кодом (HTML)."""
    pretty = f"{code[:4]}-{code[4:]}"
    return (
        "🔐 <b>Код для сайта Symed</b>\n\n"
        f"<code>{pretty}</code>\n\n"
        "Введите его на сайте symed.uz (или symed-web.vercel.app) — для входа "
        "или в Профиле для привязки Telegram. Код действует 5 минут.\n\n"
        "⚠️ <b>Никому не сообщайте этот код.</b> По нему можно войти в ваш аккаунт "
        "и увидеть ваши медицинские данные. Сотрудники Symed никогда его не попросят."
    )
