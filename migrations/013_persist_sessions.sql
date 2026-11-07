-- Незавершённые диалоги, чтобы они переживали перезапуск сервера
-- (services/persistent_state.py). Записи старше суток бэкенд удаляет сам.
-- Удаление аккаунта стирает строки пользователя (user_id) вместе с остальными
-- данными. Доступ только у бэкенда (service_role).

-- Консультации на сайте/в Mini App, начатые после входа (гостевые сюда не пишутся)
CREATE TABLE IF NOT EXISTS consultation_sessions (
    session_id text PRIMARY KEY,
    user_id bigint NOT NULL,
    data jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_consultation_sessions_user ON consultation_sessions (user_id);
CREATE INDEX IF NOT EXISTS idx_consultation_sessions_created ON consultation_sessions (created_at);

-- Одноразовые коды входа на сайт, выданные ботом (действуют 5 минут)
CREATE TABLE IF NOT EXISTS site_codes (
    code text PRIMARY KEY,
    user_id bigint NOT NULL,
    data jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_site_codes_user ON site_codes (user_id);
CREATE INDEX IF NOT EXISTS idx_site_codes_created ON site_codes (created_at);

-- Шаги диалогов бота (aiogram FSM): анкета, консультация, дневник, лекарства.
-- Без внешнего ключа на user_profiles: анкета идёт ещё до создания профиля
CREATE TABLE IF NOT EXISTS fsm_states (
    key text PRIMARY KEY,
    user_id bigint NOT NULL,
    state text,
    data jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_fsm_states_user ON fsm_states (user_id);
CREATE INDEX IF NOT EXISTS idx_fsm_states_updated ON fsm_states (updated_at);

ALTER TABLE consultation_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE site_codes ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsm_states ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON consultation_sessions FROM anon, authenticated;
REVOKE ALL ON site_codes FROM anon, authenticated;
REVOKE ALL ON fsm_states FROM anon, authenticated;
