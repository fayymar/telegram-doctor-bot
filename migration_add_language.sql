-- Миграция: добавление поля language в user_profiles
-- Запустите этот скрипт в Supabase SQL Editor

-- Добавляем поле language
ALTER TABLE user_profiles
ADD COLUMN IF NOT EXISTS language VARCHAR(5) DEFAULT 'ru';

-- Комментарий
COMMENT ON COLUMN user_profiles.language IS 'Язык интерфейса пользователя (ru, uz)';

-- Создаем индекс для быстрого поиска по языку
CREATE INDEX IF NOT EXISTS idx_user_profiles_language ON user_profiles(language);

SELECT 'Language field added successfully!' as status;
