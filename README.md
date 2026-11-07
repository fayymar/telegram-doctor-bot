# Symed — Telegram-бот и API для подбора врача по симптомам

Пользователь описывает симптомы, AI задаёт уточняющие вопросы и рекомендует
1–3 узких специалиста с уровнем срочности. Symed не ставит диагноз и не заменяет врача.

Этот репозиторий — бэкенд: Telegram-бот и HTTP API для сайта
([symed-web](https://github.com/fayymar/symed-web), symed.uz) и Telegram Mini App
([symptoMed-app](https://github.com/fayymar/symptoMed-app)).

## Что умеет

- **Консультация.** Проверка «красных флагов» по правилам, затем уточняющие
  вопросы, давность и анамнез от AI. Опасные симптомы всегда дают «экстренно»
  и совет вызвать 103.
- **Профиль и анамнез:** хронические болезни, аллергии, наследственность, образ жизни.
- **История консультаций** и её экспорт.
- **Лекарства** с напоминаниями, **дневник здоровья**, **показатели**
  (пульс, давление, SpO2, шаги) с алертами при отклонениях.
- **Поиск клиник и специалистов.**
- **Вход на сайт:**
  - через Telegram: бот присылает одноразовый код (`/login`);
  - через Google, Apple или email (Supabase Auth);
  - в Mini App — автоматически по подписи Telegram.
- **Согласие на обработку данных о здоровье** (закон РУз «О персональных данных»).
  Без него данные не обрабатываются. Отзыв и полное удаление — `/deletedata`
  в боте или «Удалить аккаунт» на сайте.

## Стек

- Python 3.11, [aiogram 3](https://docs.aiogram.dev/) (бот) и aiohttp (HTTP API) в одном процессе.
- **AI:**
  - Anthropic Claude Haiku — основная модель;
  - Groq (Llama) — резервная, если задан `GROQ_API_KEY`.
- Supabase (PostgreSQL, регион Франкфурт): данные и Supabase Auth для входа на сайт.
- Хостинг — Render, `render.yaml`.

## Структура

```
main.py                 # запуск: бот, HTTP API, фоновые задачи
api/                    # HTTP API для сайта и Mini App
  routes.py             # все маршруты /api/*
  common.py             # авторизация, согласие, лимиты, CORS, сессии консультаций
  consultation.py, profile.py, health.py, auth.py
config.py               # переменные окружения
bot/                    # Telegram-бот: обработчики, клавиатуры, состояния, middleware согласия
services/
  consultation_agent.py # логика консультации (вопросы, итоговая рекомендация)
  ai_service.py         # вызовы Claude / Groq
  red_flags.py          # правила опасных симптомов
  consent.py            # согласие, удаление всех данных пользователя
  sessions.py           # отзыв токенов (выход, выход везде)
security/               # токены сессии (HMAC), проверка подписи Telegram, отзыв токенов
database/connection.py  # клиент Supabase
utils/                  # валидация, экспорт анамнеза, логирование
migrations/             # SQL-миграции по порядку (001…)
tests/                  # pytest
API_AUTH.md             # авторизация API, согласие, выход
```

## Запуск локально

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env   # заполнить ключи
python main.py
```

Переменные окружения (подробно — в `.env.example`):

| Переменная | Что это |
| --- | --- |
| `BOT_TOKEN` | токен бота от @BotFather |
| `ANTHROPIC_API_KEY` | ключ Anthropic (основная модель) |
| `GROQ_API_KEY` | необязательно: резервная модель |
| `SUPABASE_URL`, `SUPABASE_KEY` | проект Supabase; ключ **service_role**, не anon |
| `SESSION_SECRET` | необязательно: секрет подписи токенов (по умолчанию выводится из `BOT_TOKEN`) |
| `PORT`, `DEBUG`, `FSM_TIMEOUT`, `LOG_DIR` | необязательные настройки |

## База данных

Миграции лежат в `migrations/`. Их выполняют по порядку номеров в Supabase → SQL Editor:
сначала `001_schema.sql`, затем остальные. Для таблиц включён RLS, и доступ к данным есть
только у бэкенда с ключом service_role (см. `009_enable_rls.sql`). Ключ service_role должен
быть в `SUPABASE_KEY` **до** выполнения `009`.

## Тесты

```bash
pytest -q
```

Тесты не ходят в Telegram, Anthropic и Supabase: окружение подменяется в `tests/conftest.py`.
Они запускаются в GitHub Actions на каждый push и pull request.

## API

Все `/api/*`, кроме входа и гостевой консультации, требуют `Authorization: Bearer <token>`.
Подробности — в [API_AUTH.md](API_AUTH.md).

- **Вход и выход:**
  - `POST /api/auth/code` — по коду из бота;
  - `/api/auth/social` — Google, Apple, email;
  - `/api/auth/telegram-webapp` — Mini App;
  - `/api/auth/telegram-widget` — Telegram Login Widget;
  - `/api/auth/link` — привязать Telegram;
  - `GET /api/auth/me`;
  - `GET /api/auth/metrics-token`;
  - `POST /api/auth/logout`, `/api/auth/logout-all`.
- **Согласие и удаление:** `GET`/`POST /api/consent`, `DELETE /api/account`.
- **Консультация:**
  - `POST /api/consultation/start`, `answer`, `duration`, `result`, `feedback`;
  - `GET /api/consultations/{user_id}`.
- **Данные пользователя:** `/api/profile/{user_id}`, `/api/medications/{user_id}`, `/api/diary/{user_id}`.
- **Показатели:**
  - `POST /api/health/heartrate`, `/api/health/metrics`, `/api/health/metrics/report/{user_id}`;
  - `GET /api/health/metrics/{user_id}`, `/api/health/heartrate/{user_id}`.
- **Служебное:** `GET /health`.
