-- Согласия на обработку персональных данных (включая данные о здоровье).
-- Закон РУз «О персональных данных», ст. 25 (письменное, в т.ч. электронное
-- согласие на обработку специальных данных) и ст. 15 (трансграничная передача).
CREATE TABLE IF NOT EXISTS consents (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT,                 -- NULL у гостевой консультации
    session_id  TEXT,                   -- id гостевой консультации
    version     TEXT NOT NULL,          -- версия текста согласия (services/consent.py)
    source      TEXT NOT NULL CHECK (source IN ('bot', 'web', 'miniapp')),
    accepted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_consents_user_version ON consents (user_id, version);

-- Доступ только с бэкенда (service_role), как у остальных таблиц
ALTER TABLE consents ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON consents FROM anon, authenticated;
