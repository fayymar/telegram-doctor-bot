-- Поля анамнеза и привязки аккаунтов в user_profiles.
-- Раньше бот пытался добавить их сам через RPC exec_sql при старте — это
-- небезопасно (функция позволяет выполнить любой SQL), поэтому теперь вручную.
ALTER TABLE user_profiles
    ADD COLUMN IF NOT EXISTS chronic_diseases   TEXT[] DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS drug_allergies     TEXT   DEFAULT '',
    ADD COLUMN IF NOT EXISTS smoking            TEXT   DEFAULT 'no',
    ADD COLUMN IF NOT EXISTS hereditary         TEXT[] DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS physical_activity  TEXT,
    ADD COLUMN IF NOT EXISTS linked_telegram_id TEXT,
    ADD COLUMN IF NOT EXISTS linked_web_id      TEXT;
