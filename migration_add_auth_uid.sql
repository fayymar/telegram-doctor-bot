-- UUID пользователя Supabase Auth для веб-аккаунтов (вход через Google/Apple/email).
-- Нужен, чтобы «Удалить аккаунт» удалял и сам вход (вместе с email).
-- Заполняет только сервер (service_role); через API профиля это поле не меняется.
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS auth_uid text;
