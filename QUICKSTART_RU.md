# 🚀 Быстрый старт

## Шаг 1: Получение необходимых ключей

### 1.1. Telegram Bot Token

1. Откройте [@BotFather](https://t.me/BotFather) в Telegram
2. Отправьте `/newbot`
3. Придумайте имя бота (например: "Мой медицинский бот")
4. Придумайте username бота (должен заканчиваться на bot, например: `mymedical_bot`)
5. Скопируйте токен, который даст BotFather

### 1.2. Google Gemini API Key

1. Перейдите на [Google AI Studio](https://aistudio.google.com/app/apikey)
2. Войдите через Google аккаунт
3. Нажмите **"Get API Key"** → **"Create API key"**
4. Скопируйте ключ

**Важно:** Бесплатный лимит - 15 запросов/минуту и 1 млн токенов/день

### 1.3. Supabase

1. Зарегистрируйтесь на [supabase.com](https://supabase.com)
2. Создайте новый проект:
   - Название: `medical-bot` (любое)
   - Database Password: придумайте сложный пароль
   - Region: выберите ближайший (например, Frankfurt)
3. Дождитесь создания проекта (1-2 минуты)
4. Перейдите в **Settings** → **API**
5. Скопируйте:
   - **Project URL** (будет вида `https://xxxxx.supabase.co`)
   - **anon public** key (длинный ключ)

6. Создайте таблицы:
   - Перейдите в **SQL Editor**
   - Нажмите **"New query"**
   - Скопируйте весь код из файла `supabase_schema.sql`
   - Нажмите **"Run"** (или Ctrl/Cmd + Enter)
   - Должно появиться: "Success. No rows returned"

## Шаг 2: Настройка проекта

### 2.1. Создание .env файла

```bash
# Скопируйте пример
cp .env.example .env

# Откройте .env в текстовом редакторе и вставьте свои ключи
```

Пример заполненного `.env`:

```env
BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
GEMINI_API_KEY=AIzaSyA...ваш_ключ
SUPABASE_URL=https://abcdefgh.supabase.co
SUPABASE_KEY=eyJhbGci...ваш_длинный_ключ
```

### 2.2. Установка зависимостей

```bash
# Создайте виртуальное окружение
python -m venv venv

# Активируйте его
# На Linux/Mac:
source venv/bin/activate
# На Windows:
venv\Scripts\activate

# Установите пакеты
pip install -r requirements.txt
```

### 2.3. Запуск скрипта настройки

```bash
python setup.py
```

Это создаст нужные директории и файлы.

## Шаг 3: Запуск бота

```bash
python main.py
```

Если всё настроено правильно, вы увидите:

```
INFO - Бот запущен
```

## Шаг 4: Тестирование

1. Найдите вашего бота в Telegram по username
2. Отправьте `/start`
3. Заполните профиль (возраст, пол, рост, вес)
4. Нажмите "🩺 Новая консультация"
5. Опишите симптомы, например: "болит голова и температура 38"

Бот задаст уточняющие вопросы и порекомендует врача!

## 🚨 Частые проблемы

### Ошибка: "Отсутствуют обязательные переменные окружения"

**Решение:** Проверьте, что все переменные в `.env` заполнены правильно.

### Ошибка: "Connection error" при работе с Supabase

**Решение:** 
1. Убедитесь, что URL и KEY из Supabase скопированы верно
2. Проверьте, что таблицы созданы (запустите SQL скрипт)

### Бот не отвечает

**Решение:**
1. Проверьте, что токен бота правильный
2. Убедитесь, что бот запущен (`python main.py` работает без ошибок)
3. Попробуйте отправить боту `/start`

### Ошибка при анализе симптомов

**Решение:**
1. Проверьте Gemini API key
2. Убедитесь, что не превышен лимит (15 запросов/минуту)

## 📦 Деплой на Render (опционально)

Если хотите, чтобы бот работал 24/7:

1. Создайте репозиторий на GitHub и загрузите код
2. Зарегистрируйтесь на [render.com](https://render.com)
3. New → Web Service
4. Connect к вашему GitHub репозиторию
5. Настройки:
   - Name: `medical-bot`
   - Environment: `Python`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `python main.py`
6. Добавьте Environment Variables:
   - `BOT_TOKEN`
   - `GEMINI_API_KEY`
   - `SUPABASE_URL`
   - `SUPABASE_KEY`
7. Нажмите "Create Web Service"

Готово! Бот будет работать на Render.

## 🎉 Готово!

Теперь ваш медицинский бот работает и готов помогать пользователям!

## 📚 Дальнейшее изучение

- Изучите код в папке `bot/handlers/` чтобы понять, как работает бот
- Попробуйте изменить список специалистов в `services/ai_service.py`
- Добавьте новые команды в `bot/handlers/basic.py`

## ❓ Нужна помощь?

Создайте issue в GitHub репозитории или изучите документацию:
- [aiogram документация](https://docs.aiogram.dev/)
- [Google Gemini API](https://ai.google.dev/gemini-api/docs)
- [Supabase документация](https://supabase.com/docs)
