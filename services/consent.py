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


def _remember(user_id: int, version: str) -> None:
    if len(_consent_cache) >= _CACHE_LIMIT:
        _consent_cache.clear()
    _consent_cache[user_id] = version


async def has_consent(user_id: int) -> bool:
    """Дал ли пользователь согласие на текущую версию текста."""
    if _consent_cache.get(user_id) == CONSENT_VERSION:
        return True
    resp = await run_query(
        lambda: supabase_client.table("consents")
        .select("version")
        .eq("user_id", user_id)
        .eq("version", CONSENT_VERSION)
        .limit(1)
        .execute()
    )
    if resp.data:
        _remember(user_id, CONSENT_VERSION)
        return True
    return False


async def record_consent(user_id: int | None, source: str, session_id: str | None = None) -> None:
    """Записывает факт согласия на текущую версию текста."""
    if source not in CONSENT_SOURCES:
        raise ValueError(f"unknown consent source: {source}")
    row = {"version": CONSENT_VERSION, "source": source}
    if user_id is not None:
        row["user_id"] = user_id
    if session_id:
        row["session_id"] = session_id
    await run_query(lambda: supabase_client.table("consents").insert(row).execute())
    if user_id is not None:
        _remember(user_id, CONSENT_VERSION)
    logger.info(f"Consent {CONSENT_VERSION} recorded: user={user_id} source={source}")


# Таблицы с данными пользователя. user_profiles — последней (на неё ссылаются FK).
_USER_TABLES = ("messages", "consultations", "medications", "health_diary", "health_metrics", "consents", "user_profiles")


async def delete_all_user_data(user_id: int) -> None:
    """
    Удаляет все данные пользователя во всех таблицах, включая записи о согласии
    (отзыв согласия). Ошибка в одной таблице не прерывает удаление остальных,
    но в конце пробрасывается, чтобы пользователь узнал о сбое.
    """
    _consent_cache.pop(user_id, None)
    failed = []
    for table in _USER_TABLES:
        try:
            await run_query(lambda t=table: supabase_client.table(t).delete().eq("user_id", user_id).execute())
        except Exception as e:
            logger.error(f"Delete user data failed: table={table} user={user_id}: {type(e).__name__}")
            failed.append(table)
    if failed:
        raise RuntimeError(f"failed to delete from: {', '.join(failed)}")
    logger.info(f"All data deleted for user {user_id} at {int(time.time())}")
