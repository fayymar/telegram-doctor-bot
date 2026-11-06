# Авторизация API (с ноября 2026)

Раньше API доверял `user_id` из URL или тела запроса, поэтому любой мог читать и менять чужие данные.
Теперь бэкенд выдаёт **токен сессии**, и все запросы к данным пользователя идут с заголовком

```
Authorization: Bearer <token>
```

`user_id` берётся только из токена. Если в URL указан чужой `{user_id}`, сервер отвечает `403`, без токена — `401`.

## Как получить токен

| Откуда вход | Запрос | Тело |
|---|---|---|
| Telegram Mini App (symptoMed-app) | `POST /api/auth/telegram-webapp` | `{"init_data": Telegram.WebApp.initData}` |
| Сайт, Telegram Login Widget | `POST /api/auth/telegram-widget` | объект пользователя от виджета (`id, first_name, …, auth_date, hash`) |
| Сайт, Google/email (Supabase Auth) | `POST /api/auth/social` | `{"access_token": session.access_token}` |
| Сайт, 6-значный код через бота | `POST /api/auth/request`, затем опрашивать `GET /api/auth/status/{code}?secret={poll_secret}` | — |

Все способы входа возвращают `{"token", "id", "first_name", ...}`. Токен живёт 30 дней.
Проверить его можно запросом `GET /api/auth/me`.

### Что изменилось для 6-значного кода
- Код теперь **генерирует сервер**: `POST /api/auth/request` → `{"code", "poll_secret", "expires_in"}`.
- Узнать результат входа можно только по `poll_secret`. Это не даёт угадать чужой код и войти под чужим аккаунтом.

### Что изменилось для `/api/auth/social`
- Email и `provider_id` из тела больше не принимаются. Нужно передавать `access_token` из сессии Supabase.
  Сервер сам проверяет его у Supabase. `user_id` вычисляется по той же формуле, что `deriveUserId()` на фронте.

## Эндпоинты, которым нужен токен
`/api/profile/*`, `/api/consultations/*`, `/api/medications/*`, `/api/diary/*`,
`/api/health/heartrate/{id}` (GET), `/api/health/metrics/{id}` (GET), `/api/health/metrics/report/{id}`,
`/api/consultation/feedback`, `/api/auth/link-request`, `/api/auth/link-status/*`,
`/api/auth/me`, `/api/auth/metrics-token`.

Консультацию (`/api/consultation/*`) можно проходить и **гостем**, без токена.
С токеном учитываются профиль, история и показатели пользователя. Сессию консультации пользователя может продолжить только он сам.
`/api/consultation/result` теперь возвращает `consultation_id`: его нужно передавать в `/feedback`.

## Показатели с Apple Watch / iPhone Shortcut
`POST /api/health/metrics` и `POST /api/health/heartrate` принимают **токен метрик**:
- получить: `GET /api/auth/metrics-token` (с токеном сессии) → `{"token": "..."}`;
- в Shortcut: заголовок `Authorization: Bearer <token>` **или** поле `"token"` в JSON.

Токен метрик действует 180 дней; с ним можно только *отправлять* показатели. Читать данные им нельзя.
Поле `user_id` в теле игнорируется.

## Supabase
Бэкенд должен работать с ключом **service_role**, а на всех таблицах должен быть включён RLS
(см. `migration_enable_rls.sql`, там описан порядок действий). Публичный anon-ключ, который лежит в коде сайта,
после этого не даёт доступа к таблицам.
