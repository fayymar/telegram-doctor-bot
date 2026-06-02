-- Добавляет колонку rating для оценки консультации
ALTER TABLE consultations
ADD COLUMN IF NOT EXISTS rating TEXT CHECK (rating IN ('good', 'bad'));
