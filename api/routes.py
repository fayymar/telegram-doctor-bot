"""Маршруты HTTP API."""
from aiohttp import web

from api.auth import (
    api_account_delete,
    api_auth_code,
    api_auth_link,
    api_auth_logout,
    api_auth_logout_all,
    api_auth_me,
    api_auth_metrics_token,
    api_auth_social,
    api_auth_telegram_webapp,
    api_auth_telegram_widget,
    api_consent_get,
    api_consent_post,
)
from api.common import (
    cors_middleware,
    health_check,
)
from api.consultation import (
    api_consultation_answer,
    api_consultation_duration,
    api_consultation_feedback,
    api_consultation_result,
    api_consultation_start,
    api_consultations_get,
)
from api.health import (
    api_health_heartrate,
    api_health_heartrate_get,
    api_health_metrics_get,
    api_health_metrics_post,
    api_health_metrics_report,
)
from api.profile import (
    api_diary_get,
    api_diary_post,
    api_medications_get,
    api_medications_post,
    api_profile_get,
    api_profile_post,
)


def create_app() -> web.Application:
    app = web.Application(middlewares=[cors_middleware])
    app.router.add_get('/health', health_check)
    app.router.add_get('/', health_check)
    app.router.add_post('/api/consultation/start', api_consultation_start)
    app.router.add_post('/api/consultation/answer', api_consultation_answer)
    app.router.add_post('/api/consultation/duration', api_consultation_duration)
    app.router.add_post('/api/consultation/result', api_consultation_result)
    app.router.add_post('/api/consultation/feedback', api_consultation_feedback)
    app.router.add_get('/api/consultations/{user_id}', api_consultations_get)
    app.router.add_get('/api/medications/{user_id}', api_medications_get)
    app.router.add_post('/api/medications/{user_id}', api_medications_post)
    app.router.add_post('/api/diary/{user_id}', api_diary_post)
    app.router.add_get('/api/diary/{user_id}', api_diary_get)
    app.router.add_get('/api/profile/{user_id}', api_profile_get)
    app.router.add_post('/api/profile/{user_id}', api_profile_post)
    app.router.add_get('/api/health/heartrate/{user_id}', api_health_heartrate_get)
    app.router.add_post('/api/health/heartrate', api_health_heartrate)
    app.router.add_post('/api/health/metrics', api_health_metrics_post)
    app.router.add_post('/api/health/metrics/report/{user_id}', api_health_metrics_report)
    app.router.add_get('/api/health/metrics/{user_id}', api_health_metrics_get)
    app.router.add_post('/api/auth/social', api_auth_social)
    app.router.add_post('/api/auth/telegram-webapp', api_auth_telegram_webapp)
    app.router.add_post('/api/auth/telegram-widget', api_auth_telegram_widget)
    app.router.add_get('/api/auth/me', api_auth_me)
    app.router.add_get('/api/auth/metrics-token', api_auth_metrics_token)
    app.router.add_post('/api/auth/code', api_auth_code)
    app.router.add_post('/api/auth/link', api_auth_link)
    app.router.add_post('/api/auth/logout', api_auth_logout)
    app.router.add_post('/api/auth/logout-all', api_auth_logout_all)
    app.router.add_get('/api/consent', api_consent_get)
    app.router.add_post('/api/consent', api_consent_post)
    app.router.add_delete('/api/account', api_account_delete)
    return app
