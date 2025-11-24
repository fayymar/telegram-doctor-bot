-- Миграция: добавление таблицы для напоминаний о лекарствах
-- Запустите этот скрипт в Supabase SQL Editor

-- Создаем таблицу medications
CREATE TABLE IF NOT EXISTS medications (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    medication_name TEXT NOT NULL,
    dosage TEXT NOT NULL,
    frequency TEXT NOT NULL, -- 'once', 'twice', 'thrice', 'custom'
    times TEXT[] NOT NULL, -- Массив времен приема, например ['09:00', '21:00']
    start_date DATE NOT NULL,
    end_date DATE,
    notes TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Индекс для быстрого поиска по user_id
CREATE INDEX IF NOT EXISTS idx_medications_user_id ON medications(user_id);

-- Индекс для активных напоминаний
CREATE INDEX IF NOT EXISTS idx_medications_active ON medications(is_active);

-- Комментарии
COMMENT ON TABLE medications IS 'Напоминания о приеме лекарств';
COMMENT ON COLUMN medications.medication_name IS 'Название лекарства';
COMMENT ON COLUMN medications.dosage IS 'Дозировка (например, "1 таблетка", "5 мл")';
COMMENT ON COLUMN medications.frequency IS 'Частота приема';
COMMENT ON COLUMN medications.times IS 'Времена приема в формате HH:MM';
COMMENT ON COLUMN medications.start_date IS 'Дата начала приема';
COMMENT ON COLUMN medications.end_date IS 'Дата окончания приема (необязательно)';
COMMENT ON COLUMN medications.notes IS 'Дополнительные заметки';
COMMENT ON COLUMN medications.is_active IS 'Активно ли напоминание';

SELECT 'Medications table created successfully!' as status;
