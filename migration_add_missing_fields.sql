-- Миграция: добавление недостающих полей в user_profiles
-- Запустите этот скрипт в Supabase SQL Editor

-- Добавляем колонки если их нет
ALTER TABLE user_profiles
ADD COLUMN IF NOT EXISTS full_name TEXT,
ADD COLUMN IF NOT EXISTS phone TEXT,
ADD COLUMN IF NOT EXISTS birthdate DATE;

-- Удаляем колонку age если она есть (теперь вычисляется из birthdate)
ALTER TABLE user_profiles
DROP COLUMN IF EXISTS age;

-- Комментарии
COMMENT ON COLUMN user_profiles.full_name IS 'ФИО пользователя';
COMMENT ON COLUMN user_profiles.phone IS 'Номер телефона в международном формате';
COMMENT ON COLUMN user_profiles.birthdate IS 'Дата рождения пользователя';

-- Информация
SELECT 'Migration completed successfully!' as status;
