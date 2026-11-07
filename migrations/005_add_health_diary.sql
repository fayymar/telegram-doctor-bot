-- Миграция: добавление таблицы для дневника здоровья
-- Запустите этот скрипт в Supabase SQL Editor

-- Создаем таблицу health_diary
CREATE TABLE IF NOT EXISTS health_diary (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    entry_date DATE NOT NULL,
    entry_time TIME,
    temperature DECIMAL(4,1), -- Температура тела в °C
    blood_pressure_sys INTEGER, -- Систолическое давление
    blood_pressure_dia INTEGER, -- Диастолическое давление
    pulse INTEGER, -- Пульс (уд/мин)
    weight DECIMAL(5,2), -- Вес в кг
    symptoms TEXT, -- Симптомы
    mood TEXT, -- Настроение
    notes TEXT, -- Заметки
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Индекс для быстрого поиска по user_id и дате
CREATE INDEX IF NOT EXISTS idx_health_diary_user_date ON health_diary(user_id, entry_date DESC);

-- Комментарии
COMMENT ON TABLE health_diary IS 'Дневник здоровья пользователя';
COMMENT ON COLUMN health_diary.entry_date IS 'Дата записи';
COMMENT ON COLUMN health_diary.entry_time IS 'Время записи';
COMMENT ON COLUMN health_diary.temperature IS 'Температура тела в °C';
COMMENT ON COLUMN health_diary.blood_pressure_sys IS 'Систолическое (верхнее) давление';
COMMENT ON COLUMN health_diary.blood_pressure_dia IS 'Диастолическое (нижнее) давление';
COMMENT ON COLUMN health_diary.pulse IS 'Пульс в ударах в минуту';
COMMENT ON COLUMN health_diary.weight IS 'Вес в килограммах';
COMMENT ON COLUMN health_diary.symptoms IS 'Описание симптомов';
COMMENT ON COLUMN health_diary.mood IS 'Настроение/самочувствие';
COMMENT ON COLUMN health_diary.notes IS 'Дополнительные заметки';

SELECT 'Health diary table created successfully!' as status;
