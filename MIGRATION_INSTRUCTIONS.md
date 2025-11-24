# Инструкция по миграции БД

## Проблема
При попытке запустить бота возникает ошибка "Произошла ошибка при подключении к базе данных", потому что в таблице `user_profiles` отсутствуют необходимые колонки.

## Решение

### Шаг 1: Войдите в Supabase Dashboard
1. Откройте https://supabase.com/dashboard
2. Выберите ваш проект

### Шаг 2: Откройте SQL Editor
1. В левом меню выберите "SQL Editor"
2. Нажмите "New Query"

### Шаг 3: Выполните миграцию
Скопируйте и вставьте содержимое файла `migration_add_missing_fields.sql` и нажмите "Run"

```sql
-- Миграция: добавление недостающих полей в user_profiles

ALTER TABLE user_profiles
ADD COLUMN IF NOT EXISTS full_name TEXT,
ADD COLUMN IF NOT EXISTS phone TEXT,
ADD COLUMN IF NOT EXISTS birthdate DATE;

ALTER TABLE user_profiles
DROP COLUMN IF EXISTS age;

COMMENT ON COLUMN user_profiles.full_name IS 'ФИО пользователя';
COMMENT ON COLUMN user_profiles.phone IS 'Номер телефона в международном формате';
COMMENT ON COLUMN user_profiles.birthdate IS 'Дата рождения пользователя';

SELECT 'Migration completed successfully!' as status;
```

### Шаг 4: Проверка
После выполнения миграции должно появиться сообщение "Migration completed successfully!"

### Шаг 5: Перезапустите бота
Бот автоматически перезапустится на Render, либо перезапустите вручную.

## Что было исправлено

**До миграции (старая schema):**
```
user_profiles:
- user_id
- username
- age          ❌ (устаревшее поле)
- gender
- height
- weight
```

**После миграции (новая schema):**
```
user_profiles:
- user_id
- username
- full_name    ✅ (добавлено)
- phone        ✅ (добавлено)
- birthdate    ✅ (добавлено)
- gender
- height
- weight
```

## Дополнительные исправления в коде

✅ Добавлен proper logging в `basic.py` вместо `print()`
✅ Улучшена обработка ошибок с детальным логированием
✅ Обновлена schema в `supabase_schema.sql`

## Если миграция не помогла

Проверьте логи на Render:
1. Откройте https://dashboard.render.com
2. Выберите ваш сервис
3. Перейдите в "Logs"
4. Найдите строку с ошибкой (будет содержать `Database error in cmd_start`)

Полный traceback ошибки теперь будет виден в логах благодаря `exc_info=True`.
