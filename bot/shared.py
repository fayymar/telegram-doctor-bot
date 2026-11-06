"""Shared in-memory state между main.py и bot handlers."""

# web_auth_codes: code -> {telegram_id, first_name, last_name, username, photo_url, verified, created_at}
web_auth_codes: dict = {}

# link_codes: code -> {web_user_id, verified, telegram_id, created_at}
link_codes: dict = {}

# ── Защита от перебора кодов ──────────────────────────────────────────────────
# Коды входа и привязки — 6 цифр. Без ограничения их можно перебирать, отправляя
# боту /link 000000…999999, и привязать свой Telegram к чужому веб-профилю.
import time as _time

_CODE_FAIL_LIMIT = 5         # неверных кодов
_CODE_FAIL_WINDOW = 15 * 60  # за 15 минут с одного Telegram-аккаунта
_code_failures: dict = {}    # telegram_id -> [timestamps]


def code_attempts_blocked(telegram_id: int) -> bool:
    """True, если пользователь исчерпал лимит неверных кодов."""
    now = _time.time()
    recent = [t for t in _code_failures.get(telegram_id, []) if now - t < _CODE_FAIL_WINDOW]
    if recent:
        _code_failures[telegram_id] = recent
    else:
        _code_failures.pop(telegram_id, None)
    return len(recent) >= _CODE_FAIL_LIMIT


def record_failed_code_attempt(telegram_id: int) -> None:
    _code_failures.setdefault(telegram_id, []).append(_time.time())
    if len(_code_failures) > 50_000:  # не даём словарю расти бесконечно
        now = _time.time()
        for k in [k for k, v in _code_failures.items() if not v or now - v[-1] > _CODE_FAIL_WINDOW]:
            del _code_failures[k]


TOO_MANY_ATTEMPTS_TEXT = "⏳ Слишком много неверных кодов. Попробуйте снова через 15 минут."
