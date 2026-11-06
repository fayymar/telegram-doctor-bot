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

SITE_CODE_TTL = 300     # код действует 5 минут
SITE_CODE_DIGITS = 8    # 10^8 вариантов: перебор ограничен rate limit на сервере

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
        code = f"{secrets.randbelow(10 ** SITE_CODE_DIGITS):0{SITE_CODE_DIGITS}d}"
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


def redeem_site_code(code: str) -> dict | None:
    """Погашает код (одноразово). Возвращает данные Telegram-пользователя или None."""
    code = (code or "").strip().replace(" ", "")
    entry = site_codes.pop(code, None)
    if not entry or time.time() - entry["created_at"] > SITE_CODE_TTL:
        return None
    return entry


def site_code_message(code: str) -> str:
    """Текст сообщения с кодом (HTML)."""
    pretty = f"{code[:4]} {code[4:]}"
    return (
        "🔐 <b>Код для сайта Symed</b>\n\n"
        f"<code>{pretty}</code>\n\n"
        "Введите его на сайте symed.uz (или symed-web.vercel.app) — для входа "
        "или в Профиле для привязки Telegram. Код действует 5 минут.\n\n"
        "⚠️ <b>Никому не сообщайте этот код.</b> По нему можно войти в ваш аккаунт "
        "и увидеть ваши медицинские данные. Сотрудники Symed никогда его не попросят."
    )
