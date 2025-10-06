-- Таблица профилей пользователей
CREATE TABLE IF NOT EXISTS user_profiles (
    user_id BIGINT PRIMARY KEY,
    username TEXT,
    age INTEGER,
    gender TEXT CHECK (gender IN ('male', 'female', 'other')),
    height INTEGER,
    weight DECIMAL(5,2),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Таблица консультаций
CREATE TABLE IF NOT EXISTS consultations (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES user_profiles(user_id) ON DELETE CASCADE,
    symptoms TEXT NOT NULL,
    questions_answers TEXT NOT NULL,
    recommended_doctor TEXT NOT NULL,
    urgency_level TEXT CHECK (urgency_level IN ('low', 'medium', 'high', 'emergency')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Таблица сообщений (история диалогов)
CREATE TABLE IF NOT EXISTS messages (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES user_profiles(user_id) ON DELETE CASCADE,
    consultation_id INTEGER REFERENCES consultations(id) ON DELETE SET NULL,
    role TEXT CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Индексы для быстрого поиска
CREATE INDEX IF NOT EXISTS idx_consultations_user_id ON consultations(user_id);
CREATE INDEX IF NOT EXISTS idx_consultations_created_at ON consultations(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_messages_user_id ON messages(user_id);
CREATE INDEX IF NOT EXISTS idx_messages_consultation_id ON messages(consultation_id);

-- Комментарии к таблицам
COMMENT ON TABLE user_profiles IS 'Профили пользователей телеграм бота';
COMMENT ON TABLE consultations IS 'История медицинских консультаций';
COMMENT ON TABLE messages IS 'История диалогов пользователей с ботом';
