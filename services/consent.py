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

CONSENT_VERSION = "2026-11-08"
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
    "• на хранение данных на защищённых серверах в ЕС;\n"
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
# Пользователи, чьё удаление идёт прямо сейчас
_deleting_users: set[int] = set()


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
        # снова дал согласие после удаления аккаунта — диалоги снова сохраняются.
        # Пока удаление этого пользователя идёт, запрет не снимаем: удаление ещё
        # сотрёт и это согласие (consents удаляется и в конце)
        if user_id not in _deleting_users:
            from services.persistent_state import clear_user_deleted
            clear_user_deleted(user_id)
    logger.info(f"Consent {CONSENT_VERSION} recorded: user={user_id} source={source}")


# Таблицы с данными пользователя. consents — первой: с этого момента проверки согласия сразу отказывают;
# user_profiles — последней (на неё ссылаются FK).
_USER_TABLES = (
    "consents", "messages", "consultations", "medications", "health_diary", "health_metrics",
    # незавершённые диалоги (services/persistent_state.py)
    "consultation_sessions", "fsm_states", "site_codes",
    "user_profiles",  # последним: хранит auth_uid, см. delete_all_user_data
)


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
            missing = set()  # просмотрели всех пользователей: входа у них просто нет
            break
        page += 1
    if missing:
        # Не успели просмотреть весь список — нельзя утверждать, что вход удалён
        raise RuntimeError("auth user scan limit reached")
    return found


async def delete_all_user_data(user_id: int) -> None:
    """
    Удаляет все данные аккаунта во всех таблицах, включая записи о согласии
    (отзыв согласия), отзывает его токены и удаляет вход Supabase Auth
    (Google/Apple/email). Так работают «Удалить аккаунт», /deletedata и
    блокировка бота.

    Привязанный аккаунт (сайт <-> Telegram) НЕ удаляется: код привязки
    подтверждает только владельца Telegram, а не того, кто ввёл его на сайте,
    поэтому привязка не даёт права удалять другой аккаунт. Связь с ним
    разрывается, его данные остаются, их удаляют отдельно.

    Ошибка в одной таблице не прерывает удаление остальных, но в конце
    пробрасывается, чтобы пользователь узнал о сбое.
    """
    ids = [user_id]
    # Вход Supabase Auth ищем ДО удаления: его UUID хранится в профиле. Если найти
    # не удалось, ничего не удаляем — иначе вход пережил бы удаление без следа.
    try:
        auth_uids = await _auth_uids_for(ids)
    except Exception as e:
        logger.error(f"Auth user lookup failed for user {user_id}: {type(e).__name__}")
        raise RuntimeError("failed to resolve auth user") from e
    global _deletions
    _deletions += 1
    _consent_cache.pop(user_id, None)
    _deleting_users.add(user_id)
    try:
        return await _delete_all_user_data_inner(user_id, ids, auth_uids)
    finally:
        _deleting_users.discard(user_id)
        # Запрет записи в базу — заново с этого момента: согласие, данное во
        # время удаления, само удаление и стёрло
        from services.persistent_state import mark_user_deleted
        mark_user_deleted(user_id)


async def _delete_all_user_data_inner(user_id: int, ids: list, auth_uids: dict) -> None:
    global _deletions
    failed = []
    # Незавершённые консультации и шаги диалогов в памяти тоже содержат данные
    # о здоровье. Сначала убираем их из памяти и дожидаемся фоновой записи в
    # базу — иначе она могла бы вернуть строки уже после удаления ниже
    try:
        from services.persistent_state import forget_user
        await forget_user(user_id)
    except Exception as e:
        logger.error(f"Forget in-progress state failed for user {user_id}: {type(e).__name__}")
    # Все выданные токены (сайт, Mini App, Shortcut) перестают действовать
    try:
        from services.sessions import revoke_all_tokens
        await revoke_all_tokens(ids)
    except Exception as e:
        # В памяти токены уже отозваны; запись в базу повторится в фоне, но сообщаем
        # о сбое, чтобы пользователь повторил удаление
        logger.error(f"Token revocation persist failed for user {user_id}: {type(e).__name__}")
        failed.append("token_revocation")
    for table in _USER_TABLES:
        if table == "user_profiles" and any(t in _USER_TABLES for t in failed):
            # Профиль (последний в списке) хранит auth_uid — указатель на вход
            # Supabase. Если что-то не удалилось, оставляем профиль, чтобы повтор
            # удаления нашёл и вход, и остаток данных
            failed.append(table)
            continue
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
    # Разрываем привязку в профиле другого аккаунта
    for column in ("linked_telegram_id", "linked_web_id"):
        try:
            await run_query(
                lambda c=column: supabase_client.table("user_profiles")
                .update({c: None}).eq(c, str(user_id)).execute()
            )
        except Exception as e:
            logger.error(f"Unlink failed: column={column} user={user_id}: {type(e).__name__}")
            failed.append("unlink")
    # Вход Supabase удаляем, только если все данные действительно стёрты: иначе
    # человек потерял бы единственный способ войти и удалить оставшееся (новый вход
    # через Google/email — это новый аккаунт с другим номером)
    data_failed = [t for t in failed if t in _USER_TABLES]
    for uid in ([] if data_failed else auth_uids.values()):
        try:
            await run_query(supabase_client.auth.admin.delete_user, uid)
        except Exception as e:
            logger.error(f"Delete auth user failed for user {user_id}: {type(e).__name__}")
            if "auth" not in failed:
                failed.append("auth")
    # Повторно: параллельная проверка has_consent могла снова закэшировать
    # согласие, пока строки ещё не были удалены
    _deletions += 1
    _consent_cache.pop(user_id, None)
    if failed:
        raise RuntimeError(f"failed to delete from: {', '.join(failed)}")
    logger.info(f"All data deleted for user {user_id} at {int(time.time())}")
