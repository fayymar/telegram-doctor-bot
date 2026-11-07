"""HTTP API показателей здоровья (пульс, давление, SpO2, шаги) и алерты в Telegram."""
import asyncio
from datetime import datetime, timedelta, timezone

from aiohttp import web

from api.common import (
    _consent_required_response,
    _is_rate_limited,
    _metrics_user_id,
    _rate_limit_response,
    _spawn,
    _unauthorized,
    auth_required,
    consent_required,
    json_response,
)
from bot.instance import bot
from database.connection import run_query, supabase_client
from services.consent import has_consent
from utils.logger import setup_logger

logger = setup_logger(__name__)


def _fetch_heartrate_records(user_id: int) -> list:
    """Синхронный запрос к Supabase — вызывать только через run_query."""
    resp = (
        supabase_client.table('health_metrics')
        .select('value, recorded_at, source')
        .eq('user_id', user_id)
        .eq('metric_type', 'heartrate')
        .order('recorded_at', desc=True)
        .limit(10)
        .execute()
    )
    return resp.data or []


@auth_required
async def api_health_heartrate_get(request: web.Request) -> web.Response:
    """GET /api/health/heartrate/{user_id}"""
    user_id = request["user_id"]
    try:
        records = await run_query(_fetch_heartrate_records, user_id)
    except Exception as e:
        if 'Name or service not known' in str(e):
            logger.warning(f"Heartrate GET DNS error for user_id={user_id}, retrying in 1s: {e}")
            await asyncio.sleep(1)
            try:
                records = await run_query(_fetch_heartrate_records, user_id)
            except Exception as retry_e:
                logger.error(f"Heartrate GET retry failed for user_id={user_id}: {retry_e}", exc_info=True)
                return json_response({'error': 'Internal server error'}, status=500)
        else:
            logger.error(f"Heartrate GET error for user_id={user_id}: {e}", exc_info=True)
            return json_response({'error': 'Internal server error'}, status=500)

    return json_response({'records': records, 'has_data': len(records) > 0})


async def api_health_heartrate(request: web.Request) -> web.Response:
    """POST /api/health/heartrate — требует токен сессии или токен метрик."""
    try:
        data = await request.json()
    except Exception:
        return json_response({'error': 'Invalid JSON'}, status=400)
    if not isinstance(data, dict):
        return json_response({'error': 'Invalid JSON'}, status=400)

    user_id = await _metrics_user_id(request, data)
    if user_id is None:
        return _unauthorized()
    if not await has_consent(user_id):
        return _consent_required_response()

    try:
        hr = float(data.get('heartrate'))
    except (TypeError, ValueError):
        return json_response({'error': 'heartrate required'}, status=400)
    if not 20 <= hr <= 250:
        return json_response({'error': 'heartrate out of range'}, status=400)
    timestamp = data.get('timestamp') or datetime.now(timezone.utc).isoformat()

    try:
        record = {
            'user_id': user_id,
            'metric_type': 'heartrate',
            'value': hr,
            'unit': 'bpm',
            'recorded_at': timestamp,
            'source': 'apple_watch',
        }
        await run_query(lambda: supabase_client.table('health_metrics').insert(record).execute())

        if hr > 120 or hr < 50:
            msg = f"🚨 Пульс: {hr:.0f} уд/мин! Значительно отличается от нормы. Рекомендуем обратиться к врачу."
        elif hr > 100:
            msg = f"❤️ Пульс получен: {hr:.0f} уд/мин ⚠️ Немного выше нормы. Отдохните."
        else:
            msg = f"❤️ Пульс получен: {hr:.0f} уд/мин ✅ В норме"
        await bot.send_message(user_id, msg)

        return json_response({'status': 'ok', 'message': f'Пульс сохранён: {hr:.0f} уд/мин'})
    except Exception as e:
        logger.error(f"Health heartrate error: {e}", exc_info=True)
        return json_response({'error': 'Internal server error'}, status=500)


def _interpret_heartrate(hr: float) -> str:
    if hr < 50 or hr > 120:
        return f"❤️ Пульс: {hr:.0f} уд/мин 🚨 Критично"
    if hr < 60:
        return f"❤️ Пульс: {hr:.0f} уд/мин ⚠️ Ниже нормы"
    if hr > 100:
        return f"❤️ Пульс: {hr:.0f} уд/мин ⚠️ Повышен"
    return f"❤️ Пульс: {hr:.0f} уд/мин ✅ В норме"


def _interpret_blood_pressure(systolic: float, diastolic: float) -> str:
    if systolic >= 140 or diastolic >= 90:
        label = "🚨 Высокое"
    elif systolic >= 130 or diastolic >= 85:
        label = "⚠️ Слегка повышенное"
    elif systolic < 90 or diastolic < 60:
        label = "⚠️ Пониженное"
    else:
        label = "✅ Норма"
    return f"🩺 Давление: {systolic:.0f}/{diastolic:.0f} мм рт.ст. {label}"


def _interpret_spo2(spo2: float) -> str:
    if spo2 < 90:
        return f"🫁 SpO2: {spo2:.0f}% 🚨 Критично низкая насыщенность"
    if spo2 < 95:
        return f"🫁 SpO2: {spo2:.0f}% ⚠️ Понижена"
    return f"🫁 SpO2: {spo2:.0f}% ✅ Норма"


def _interpret_steps(steps: int) -> str:
    if steps >= 10000:
        return f"👣 Шаги: {steps} за день 🏃 Высокая активность"
    if steps >= 5000:
        return f"👣 Шаги: {steps} за день 👍 Средняя активность"
    return f"👣 Шаги: {steps} за день 🛋️ Низкая активность"


def _has_deviation(received: dict) -> bool:
    """Проверяет наличие отклонений от нормы."""
    return bool(_get_abnormal_metrics(received))


def _get_abnormal_metrics(received: dict) -> list:
    """Возвращает список ключей метрик с отклонениями: 'heartrate', 'blood_pressure', 'spo2'."""
    abnormal = []
    hr = received.get('heartrate')
    if hr is not None and (hr < 60 or hr > 100):
        abnormal.append('heartrate')
    s = received.get('systolic')
    d = received.get('diastolic')
    if s is not None and d is not None and (s >= 140 or d >= 90 or s < 90 or d < 60):
        abnormal.append('blood_pressure')
    spo2 = received.get('spo2')
    if spo2 is not None and spo2 < 95:
        abnormal.append('spo2')
    return abnormal


def _build_alert_msg(received: dict) -> str:
    """Формирует сообщение об отклонениях для Telegram."""
    lines = ["⚠️ Обнаружены отклонения в показателях:\n"]
    recommendations = []

    if 'heartrate' in received:
        hr = received['heartrate']
        lines.append(_interpret_heartrate(hr))
        if hr < 50 or hr > 120:
            recommendations.append("Критически аномальный пульс — немедленно обратитесь за медицинской помощью.")
        elif hr < 60 or hr > 100:
            recommendations.append("Нестандартный пульс — отдохните и повторите измерение через 15 минут.")

    if 'systolic' in received and 'diastolic' in received:
        s, d = received['systolic'], received['diastolic']
        lines.append(_interpret_blood_pressure(s, d))
        if s >= 140 or d >= 90:
            recommendations.append(
                "При повышенном давлении рекомендуем отдохнуть, избегать физических нагрузок "
                "и измерить давление повторно через 15-30 минут. "
                "Если давление стабильно выше 140/90 — обратитесь к врачу."
            )
        elif s < 90 or d < 60:
            recommendations.append(
                "При пониженном давлении выпейте воды, лягте и поднимите ноги. "
                "Если состояние не улучшается — обратитесь к врачу."
            )

    if 'spo2' in received:
        spo2 = received['spo2']
        lines.append(_interpret_spo2(spo2))
        if spo2 < 90:
            recommendations.append("Критически низкое насыщение крови кислородом — немедленно обратитесь за медицинской помощью.")
        elif spo2 < 95:
            recommendations.append("Пониженное насыщение крови кислородом — обеспечьте приток свежего воздуха и отдохните.")

    if 'steps' in received:
        lines.append(_interpret_steps(int(received['steps'])))

    if recommendations:
        lines.append(f"\n💡 Рекомендация: {' '.join(recommendations)}")

    return "\n".join(lines)


async def send_delayed_alert(user_id, received: dict, delay: int = 120):
    """Отправляет уведомление об отклонениях через delay секунд."""
    await asyncio.sleep(delay)
    msg = _build_alert_msg(received)
    try:
        await bot.send_message(user_id, msg)
        logger.info(f"Delayed alert sent to user_id={user_id}")
    except Exception as e:
        logger.error(f"Delayed alert send error for user_id={user_id}: {e}")


async def send_remeasure_reminder(user_id, abnormal_metrics: list, delay: int = 14400):
    """Напоминание о повторном измерении через delay секунд (по умолчанию 4 часа)."""
    await asyncio.sleep(delay)

    metric_names = {
        'blood_pressure': 'давление',
        'heartrate': 'пульс',
        'spo2': 'SpO2',
    }
    metrics_text = [metric_names.get(m, m) for m in abnormal_metrics]
    metrics_list = ', '.join(metrics_text)

    message = (
        f"🔔 Напоминание о повторном измерении\n\n"
        f"Ранее были обнаружены отклонения: {metrics_list}.\n"
        f"Рекомендуем измерить повторно чтобы убедиться что показатели пришли в норму.\n\n"
        f"Откройте приложение Symed → Здоровье → «Отправить показатели сейчас»"
    )

    try:
        await bot.send_message(chat_id=user_id, text=message)
        logger.info(f"Remeasure reminder sent to user {user_id}")
    except Exception as e:
        logger.error(f"Failed to send reminder to {user_id}: {e}")


async def api_health_metrics_post(request: web.Request) -> web.Response:
    """
    POST /api/health/metrics — тихое сохранение + отложенный алерт при отклонениях.
    Требует токен сессии или токен метрик (заголовок Authorization или поле "token").
    """
    try:
        data = await request.json()
    except Exception:
        return json_response({'error': 'Invalid JSON'}, status=400)
    if not isinstance(data, dict):
        return json_response({'error': 'Invalid JSON'}, status=400)

    user_id = await _metrics_user_id(request, data)
    if user_id is None:
        return _unauthorized()
    if not await has_consent(user_id):
        return _consent_required_response()
    timestamp = data.get('timestamp') or datetime.now(timezone.utc).isoformat()

    # Если передан часовой пояс (формат "+05:00") — конвертируем timestamp в UTC
    tz_str = data.get('timezone')
    if tz_str and timestamp:
        try:
            import re as _re
            from datetime import timezone as _tz
            m = _re.match(r'([+-])(\d{2}):(\d{2})', str(tz_str))
            if m:
                sign = 1 if m.group(1) == '+' else -1
                offset = timedelta(hours=int(m.group(2)), minutes=int(m.group(3))) * sign
                # Убираем возможный суффикс Z или существующий offset перед парсингом
                ts_clean = timestamp.rstrip('Z').split('+')[0]
                if ts_clean.count('-') > 2:          # "2026-05-04T10:00:00-05:00"
                    ts_clean = ts_clean.rsplit('-', 1)[0]
                dt_local = datetime.fromisoformat(ts_clean).replace(tzinfo=_tz(offset))
                timestamp = dt_local.astimezone(_tz.utc).strftime('%Y-%m-%dT%H:%M:%S')
                logger.info(f"Timezone {tz_str} applied, recorded_at={timestamp}")
        except Exception as tz_err:
            logger.warning(f"Timezone conversion failed (tz={tz_str}): {tz_err}")

    METRIC_MAP = [
        ('heartrate',  'heartrate',              'bpm'),
        ('systolic',   'blood_pressure_systolic', 'mmHg'),
        ('diastolic',  'blood_pressure_diastolic','mmHg'),
        ('spo2',       'spo2',                   '%'),
        ('steps',      'steps',                  'steps'),
    ]

    records_to_insert = []
    received = {}
    for field, metric_type, unit in METRIC_MAP:
        raw = data.get(field)
        if raw is None or raw == 0:
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if not 0 < value < 1_000_000:
            continue
        row = {
            'user_id': user_id,
            'metric_type': metric_type,
            'value': value,
            'unit': unit,
            'recorded_at': timestamp,
            'source': 'apple_watch',
        }
        records_to_insert.append(row)
        received[field] = value

    if not records_to_insert:
        return json_response({'error': 'No valid metrics provided'}, status=400)

    # Тихое сохранение в Supabase
    try:
        await run_query(lambda: supabase_client.table('health_metrics').insert(records_to_insert).execute())
    except Exception as e:
        logger.error(f"Health metrics insert error: {e}", exc_info=True)
        return json_response({'error': 'Internal server error'}, status=500)

    logger.info(f"Silent save for user {user_id}: {len(records_to_insert)} metrics")

    # Проверка отклонений — если есть, запускаем отложенный алерт через 2 минуты
    if _has_deviation(received):
        abnormal = _get_abnormal_metrics(received)
        _spawn(send_delayed_alert(user_id, received, delay=120))
        _spawn(send_remeasure_reminder(user_id, abnormal, delay=14400))
        logger.info(f"Deviation detected for user_id={user_id}, alert in 120s, reminder in 4h")

    return json_response({'status': 'ok', 'saved': len(records_to_insert)})


@auth_required
@consent_required
async def api_health_metrics_report(request: web.Request) -> web.Response:
    """POST /api/health/metrics/report/{user_id} — ручной отчёт о последних метриках"""
    user_id = request["user_id"]
    if _is_rate_limited(request, "report", limit=5, window=60):
        return _rate_limit_response()

    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        resp = await run_query(
            lambda: supabase_client.table('health_metrics')
            .select('metric_type, value, recorded_at')
            .eq('user_id', user_id)
            .gte('recorded_at', cutoff)
            .order('recorded_at', desc=True)
            .execute()
        )
        rows = resp.data or []
    except Exception as e:
        logger.error(f"Report fetch error for user_id={user_id}: {e}", exc_info=True)
        return json_response({'error': 'Internal server error'}, status=500)

    # Берём последнюю запись каждого типа
    seen: dict = {}
    for row in rows:
        mt = row['metric_type']
        if mt not in seen:
            seen[mt] = row

    if not seen:
        return json_response({'status': 'ok', 'message': 'No data in the last hour'})

    # Собираем received-словарь для построения отчёта
    received: dict = {}
    if 'heartrate' in seen:
        received['heartrate'] = seen['heartrate']['value']
    if 'blood_pressure_systolic' in seen:
        received['systolic'] = seen['blood_pressure_systolic']['value']
    if 'blood_pressure_diastolic' in seen:
        received['diastolic'] = seen['blood_pressure_diastolic']['value']
    if 'spo2' in seen:
        received['spo2'] = seen['spo2']['value']
    if 'steps' in seen:
        received['steps'] = seen['steps']['value']

    # Формируем полный отчёт
    lines = ["📊 Ваши показатели здоровья:\n"]
    all_ok = True

    if 'heartrate' in received:
        line = _interpret_heartrate(received['heartrate'])
        lines.append(line)
        if '🚨' in line or '⚠️' in line:
            all_ok = False

    if 'systolic' in received and 'diastolic' in received:
        line = _interpret_blood_pressure(received['systolic'], received['diastolic'])
        lines.append(line)
        if '🚨' in line or '⚠️' in line:
            all_ok = False
    elif 'systolic' in received:
        lines.append(f"🩺 Систолическое: {received['systolic']:.0f} мм рт.ст.")

    if 'spo2' in received:
        line = _interpret_spo2(received['spo2'])
        lines.append(line)
        if '🚨' in line or '⚠️' in line:
            all_ok = False

    if 'steps' in received:
        lines.append(_interpret_steps(int(received['steps'])))

    lines.append("\nВсе показатели в норме 👌" if all_ok else "\n⚠️ Есть показатели, требующие внимания.")

    msg = "\n".join(lines)
    try:
        await bot.send_message(user_id, msg)
        logger.info(f"Report sent to user_id={user_id}")
    except Exception as e:
        logger.error(f"Report send error for user_id={user_id}: {e}", exc_info=True)
        return json_response({'error': 'Telegram send failed'}, status=500)

    return json_response({'status': 'ok', 'message': 'Report sent'})


@auth_required
async def api_health_metrics_get(request: web.Request) -> web.Response:
    """GET /api/health/metrics/{user_id}?type=metric_type&limit=10"""
    user_id = request["user_id"]

    metric_type = request.rel_url.query.get('type')
    try:
        limit = max(1, min(int(request.rel_url.query.get('limit', 10)), 200))
    except ValueError:
        limit = 10

    try:
        query = (
            supabase_client.table('health_metrics')
            .select('metric_type, value, unit, recorded_at, source')
            .eq('user_id', user_id)
            .order('recorded_at', desc=True)
            .limit(limit)
        )
        if metric_type:
            query = query.eq('metric_type', metric_type)
        resp = await run_query(query.execute)
        records = resp.data or []
        return json_response({'records': records, 'has_data': len(records) > 0})
    except Exception as e:
        logger.error(f"Health metrics GET error user_id={user_id}: {e}", exc_info=True)
        return json_response({'error': 'Internal server error'}, status=500)
