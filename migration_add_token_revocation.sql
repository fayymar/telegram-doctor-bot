-- Отзыв токенов сессии: «Выйти», «Выйти на всех устройствах», удаление аккаунта.
-- Доступ только у бэкенда (service_role).

-- Отозванные отдельные токены; после истечения токена запись не нужна
CREATE TABLE IF NOT EXISTS revoked_tokens (
    jti text PRIMARY KEY,
    expires_at timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_revoked_tokens_expires ON revoked_tokens (expires_at);

-- Для пользователя: все токены, выданные не позже этого момента (мс), недействительны
CREATE TABLE IF NOT EXISTS token_cutoffs (
    user_id bigint PRIMARY KEY,
    not_before_ms bigint NOT NULL
);

ALTER TABLE revoked_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE token_cutoffs ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON revoked_tokens FROM anon, authenticated;
REVOKE ALL ON token_cutoffs FROM anon, authenticated;
