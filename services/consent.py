"""
Согласие на обработку персональных данных (включая данные о здоровье).

Закон РУз «О персональных данных»:
- ст. 25: данные о здоровье — специальные персональные данные, их обработка
  допускается с согласия субъекта в письменной форме, в т.ч. электронной;
- ст. 15: трансграничная передача в страны без «адекватной защиты» —
  с согласия субъекта.

Мы фиксируем факт согласия (кто, когда, какая версия текста, откуда) в таблице
consents. При изменении текста согласия увеличивайте CONSENT_VERSION — тогда
все пользователи увидят новый текст и дадут согласие заново.
"""
import time

from database.connection import run_query, supabase_client
from security.auth import WEB_USER_ID_MIN, derive_web_user_id
from utils.logger import setup_logger

logger = setup_logger(__name__)

CONSENT_VERSION = "2026-11-07"
PRIVACY_URL = "https://symed.uz/privacy"
CONSENT_SOURCES = ("bot", "web", "miniapp")

# Текст согласия. Должен совпадать с текстом на сайте и в Mini App.
CONSENT_TEXT_HTML = (
    "🔒 <b>Согласие на обработку данных</b>\n\n"
    "Symed работает с данными о вашем здоровье: симптомами, анамнезом, "
    "показателями и историей консультаций. Без вашего согласия мы не можем их обрабатывать.\n\n"
    "Нажимая «Согласен», вы соглашаетесь:\n"
    "• на обработку ваших персональных данных, включая данные о здоровье, "
    "чтобы подобрать вам врача-специалиста;\n"
    "• на хранение данных на защищённых серверах в Германии (ЕС);\n"
    "• на передачу симптомов, ответов на вопросы, возраста, пола и медицинского "
    "анамнеза <b>без имени и телефона</b> AI-сервисам в США для анализа.\n\n"
    "Отозвать согласие и удалить все данные можно в любой момент командой /deletedata.\n\n"
    "Symed не ставит диагноз и не заменяет врача."
)

# Кэш: user_id -> версия согласия (чтобы не ходить в базу на каждое сообщение)
_consent_cache: dict[int, str] = {}
_CACHE_LIMIT = 50_000
# Счётчик удалений данных: проверка, начатая до удаления, не должна
# закэшировать согласие, прочитанное из ещё не удалённых строк
_deletions = 0


def _remember(user_id: int, version: str) -> None:
    if len(_consent_cache) >= _CACHE_LIMIT:
        _consent_cache.clear()
    _consent_cache[user_id] = version


async def has_consent(user_id: int) -> bool:
    """Дал ли пользователь согласие на текущую версию текста."""
    if _consent_cache.get(user_id) == CONSENT_VERSION:
        return True
    started_at = _deletions
    resp = await run_query(
        lambda: supabase_client.table("consents")
        .select("version")
        .eq("user_id", user_id)
        .eq("version", CONSENT_VERSION)
        .limit(1)
        .execute()
    )
    if resp.data:
        if _deletions == started_at:
            _remember(user_id, CONSENT_VERSION)
        return True
    return False


async def record_consent(user_id: int | None, source: str, session_id: str | None = None) -> None:
    """Записывает факт согласия на текущую версию текста (для вошедшего — один раз на версию)."""
    if source not in CONSENT_SOURCES:
        raise ValueError(f"unknown consent source: {source}")
    # Повторное согласие на ту же версию не создаёт новых строк (у гостя нет user_id —
    # его согласие привязано к конкретной консультации и записывается один раз на неё)
    if user_id is not None and await has_consent(user_id):
        return
    row = {"version": CONSENT_VERSION, "source": source}
    if user_id is not None:
        row["user_id"] = user_id
    if session_id:
        row["session_id"] = session_id
    started_at = _deletions
    await run_query(lambda: supabase_client.table("consents").insert(row).execute())
    # Если параллельно шло удаление данных, строка могла быть уже стёрта — не кэшируем
    if user_id is not None and _deletions == started_at:
        _remember(user_id, CONSENT_VERSION)
    logger.info(f"Consent {CONSENT_VERSION} recorded: user={user_id} source={source}")


# Таблицы с данными пользователя. consents — первой: с этого момента проверки согласия сразу отказывают;
# user_profiles — последней (на неё ссылаются FK).
_USER_TABLES = ("consents", "messages", "consultations", "medications", "health_diary", "health_metrics", "user_profiles")


async def _linked_user_ids(user_id: int) -> list[int]:
    """
    Аккаунты, связанные с user_id привязкой сайт <-> Telegram (/api/auth/link).
    Привязка возможна только кодом, который бот выдаёт владельцу Telegram, поэтому
    оба аккаунта принадлежат одному человеку и удаляются вместе.
    """
    ids = {user_id}
    own = await run_query(
        lambda: supabase_client.table("user_profiles")
        .select("linked_telegram_id, linked_web_id")
        .eq("user_id", user_id)
        .execute()
    )
    back = await run_query(
        lambda: supabase_client.table("user_profiles")
        .select("user_id")
        .or_(f"linked_telegram_id.eq.{user_id},linked_web_id.eq.{user_id}")
        .execute()
    )
    for row in own.data or []:
        for key in ("linked_telegram_id", "linked_web_id"):
            try:
                if row.get(key):
                    ids.add(int(row[key]))
            except (TypeError, ValueError):
                pass
    for row in back.data or []:
        if row.get("user_id") is not None:
            ids.add(int(row["user_id"]))
    return sorted(ids)


# Поиск входа Supabase Auth перебором списка пользователей (для аккаунтов,
# созданных до того, как auth_uid стал сохраняться в профиле)
_AUTH_PAGE_SIZE = 1000
_AUTH_SCAN_PAGES = 20


async def _auth_uids_for(ids: list[int]) -> dict[int, str]:
    """
    Для веб-аккаунтов (вход через Google/Apple/email) находит UUID пользователя
    Supabase Auth: сначала по сохранённому auth_uid, иначе перебором списка
    пользователей. Номер аккаунта вычисляется из UUID (derive_web_user_id),
    поэтому совпадение проверяется в обе стороны.
    """
    web_ids = {i for i in ids if i >= WEB_USER_ID_MIN}
    if not web_ids:
        return {}
    found: dict[int, str] = {}
    resp = await run_query(
        lambda: supabase_client.table("user_profiles")
        .select("user_id, auth_uid")
        .in_("user_id", sorted(web_ids))
        .execute()
    )
    for row in resp.data or []:
        uid = row.get("auth_uid")
        if uid and derive_web_user_id(uid) == int(row["user_id"]):
            found[int(row["user_id"])] = uid
    missing = web_ids - set(found)
    page = 1
    while missing and page <= _AUTH_SCAN_PAGES:
        users = await run_query(supabase_client.auth.admin.list_users, page, _AUTH_PAGE_SIZE)
        for u in users or []:
            wid = derive_web_user_id(str(u.id))
            if wid in missing:
                found[wid] = str(u.id)
                missing.discard(wid)
        if not users or len(users) < _AUTH_PAGE_SIZE:
            break
        page += 1
    return found


async def delete_all_user_data(user_id: int, include_linked: bool = True) -> None:
    """
    Удаляет все данные пользователя во всех таблицах, включая записи о согласии
    (отзыв согласия). При include_linked — и в привязанном аккаунте (сайт <-> Telegram):
    так работают «Удалить аккаунт» и /deletedata. Без него удаляется только этот аккаунт
    (например, когда пользователь просто заблокировал бота).
    Ошибка в одной таблице не прерывает удаление остальных, но в конце
    пробрасывается, чтобы пользователь узнал о сбое.
    """
    try:
        ids = await _linked_user_ids(user_id) if include_linked else [user_id]
    except Exception as e:
        logger.error(f"Linked accounts lookup failed for user {user_id}: {type(e).__name__}")
        raise RuntimeError("failed to resolve linked accounts") from e
    global _deletions
    _deletions += 1
    for uid in ids:
        _consent_cache.pop(uid, None)
    failed = []
    # Все выданные токены (сайт, Mini App, Shortcut) перестают действовать
    try:
        from services.sessions import revoke_all_tokens
        await revoke_all_tokens(ids)
    except Exception as e:
        # В памяти токены уже отозваны; не сохранилось только в базе
        logger.error(f"Token revocation persist failed for user {user_id}: {type(e).__name__}")
    # Вход через Google/Apple/email (Supabase Auth) тоже удаляем — вместе с email.
    # UUID ищем до удаления профиля: он хранится там.
    try:
        auth_uids = await _auth_uids_for(ids)
    except Exception as e:
        logger.error(f"Auth user lookup failed for user {user_id}: {type(e).__name__}")
        auth_uids = {}
        failed.append("auth")
    for table in _USER_TABLES:
        try:
            await run_query(lambda t=table: supabase_client.table(t).delete().in_("user_id", ids).execute())
        except Exception as e:
            logger.error(f"Delete user data failed: table={table} user={user_id}: {type(e).__name__}")
            failed.append(table)
    # Повторно удаляем записи о согласии: параллельный POST /api/consent или
    # кнопка «Согласен» могли вставить строку уже после первого удаления
    try:
        await run_query(lambda: supabase_client.table("consents").delete().in_("user_id", ids).execute())
    except Exception as e:
        logger.error(f"Delete user data failed: table=consents (final) user={user_id}: {type(e).__name__}")
        if "consents" not in failed:
            failed.append("consents")
    for uid in auth_uids.values():
        try:
            await run_query(supabase_client.auth.admin.delete_user, uid)
        except Exception as e:
            logger.error(f"Delete auth user failed for user {user_id}: {type(e).__name__}")
            if "auth" not in failed:
                failed.append("auth")
    # Повторно: параллельная проверка has_consent могла снова закэшировать
    # согласие, пока строки ещё не были удалены
    _deletions += 1
    for uid in ids:
        _consent_cache.pop(uid, None)
    if failed:
        raise RuntimeError(f"failed to delete from: {', '.join(failed)}")
    logger.info(f"All data deleted for user {user_id} (accounts: {len(ids)}) at {int(time.time())}")
