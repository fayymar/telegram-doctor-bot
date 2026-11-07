CREATE TABLE IF NOT EXISTS health_metrics (
  id SERIAL PRIMARY KEY,
  user_id BIGINT,
  metric_type TEXT NOT NULL DEFAULT 'heartrate',
  value NUMERIC NOT NULL,
  unit TEXT DEFAULT 'bpm',
  recorded_at TIMESTAMPTZ DEFAULT NOW(),
  source TEXT DEFAULT 'apple_watch'
);
