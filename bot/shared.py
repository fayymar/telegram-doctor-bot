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

SITE_CODE_TTL = 300  # код действует 5 минут
# 8 символов без похожих (0/O, 1/I/L): 31^8 ≈ 8.5·10^11 вариантов. При лимите
# 10 попыток в минуту на IP подобрать чужой код за 5 минут нереально даже с
# тысячами адресов, поэтому общая блокировка входа (которой можно было бы
# «положить» вход всем) не нужна.
SITE_CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
SITE_CODE_LEN = 8

# code -> {telegram_id, first_name, last_name, username, created_at}
site_codes: dict = {}


def _purge_expired_site_codes() -> None:
    now = time.time()
    for code, entry in list(site_codes.items()):
        if now - entry["created_at"] > SITE_CODE_TTL:
            site_codes.pop(code, None)


def issue_site_code(telegram_user) -> str:
    """
    Создаёт одноразовый код для входа/привязки на сайте для данного
    Telegram-пользователя. Предыдущий код этого пользователя аннулируется.
    """
    _purge_expired_site_codes()
    for code, entry in list(site_codes.items()):
        if entry["telegram_id"] == telegram_user.id:
            site_codes.pop(code, None)
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


def redeem_site_code(code: str) -> dict | None:
    """Погашает код (одноразово). Возвращает данные Telegram-пользователя или None."""
    code = normalize_site_code(code)
    entry = site_codes.pop(code, None)
    if not entry or time.time() - entry["created_at"] > SITE_CODE_TTL:
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
