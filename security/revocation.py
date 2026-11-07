"""
Отзыв токенов сессии (в памяти процесса).

Токены подписаны HMAC и сами по себе не отзываются, поэтому сервер хранит:
- список отозванных токенов (по их jti) — «Выйти» на одном устройстве;
- для пользователя момент, раньше которого все его токены недействительны —
  «Выйти на всех устройствах» и удаление аккаунта.

Это состояние читается при каждой проверке токена, поэтому живёт в памяти.
Сохранение в базу и загрузка при старте — services/sessions.py.
"""
import time

# jti -> время истечения токена (unix, сек); после него запись не нужна
_revoked_jti: dict[str, float] = {}
# user_id -> момент (мс): токены, выданные не позже него, недействительны
_cutoff_ms: dict[int, int] = {}


def token_issued_ms(payload: dict) -> int:
    """Момент выдачи токена в мс. У старых токенов есть только iat (сек) —
    считаем их выданными в конце этой секунды (строже, а не мягче)."""
    if isinstance(payload.get("iatm"), int):
        return payload["iatm"]
    return int(payload.get("iat", 0)) * 1000 + 999


def is_revoked(uid: int, payload: dict) -> bool:
    cutoff = _cutoff_ms.get(uid)
    if cutoff is not None and token_issued_ms(payload) <= cutoff:
        return True
    jti = payload.get("jti")
    return bool(jti) and jti in _revoked_jti


def remember_revoked_token(jti: str, expires_at: float) -> None:
    _revoked_jti[jti] = expires_at


def remember_cutoff(user_id: int, not_before_ms: int) -> None:
    if not_before_ms > _cutoff_ms.get(user_id, -1):
        _cutoff_ms[user_id] = not_before_ms


def issue_ms(user_id: int) -> int:
    """Момент выдачи нового токена: строго позже последнего отзыва этого пользователя,
    иначе токен, выданный в ту же миллисекунду, считался бы отозванным."""
    return max(now_ms(), _cutoff_ms.get(int(user_id), -1) + 1)


def now_ms() -> int:
    return int(time.time() * 1000)


def purge_expired() -> None:
    now = time.time()
    for jti, exp in list(_revoked_jti.items()):
        if exp < now:
            _revoked_jti.pop(jti, None)


def _reset_for_tests() -> None:
    _revoked_jti.clear()
    _cutoff_ms.clear()
