-- ============================================================================
-- Закрывает прямой доступ к медицинским данным через публичный anon-ключ.
--
-- Почему это нужно: anon-ключ Supabase лежит в коде сайта (NEXT_PUBLIC_...)
-- и виден любому. Без RLS через него можно читать и менять ВСЕ таблицы
-- напрямую, минуя бэкенд и его проверку авторизации.
--
-- ПОРЯДОК (важно, иначе бот перестанет видеть базу):
--   1. В Render → Environment поменяйте SUPABASE_KEY на ключ service_role
--      (Supabase → Project Settings → API Keys → вкладка "Legacy API keys",
--      длинный ключ, начинается с eyJ...). Новые ключи sb_secret_... текущая
--      версия библиотеки supabase-py не принимает. Перезапустите сервис.
--   2. Убедитесь в логах, что нет предупреждения "SUPABASE_KEY is a public key".
--   3. Только после этого выполните этот скрипт в Supabase → SQL Editor.
--
-- Политики не создаём: бэкенд с service_role обходит RLS, а anon/authenticated
-- получают «запрещено всё». Сайт использует Supabase только для входа (Auth),
-- таблицы он напрямую не читает, поэтому ничего не сломается.
-- ============================================================================

DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'user_profiles', 'consultations', 'messages',
        'medications', 'health_diary', 'health_metrics', 'medical_embeddings'
    ]
    LOOP
        IF to_regclass('public.' || t) IS NOT NULL THEN
            EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
            EXECUTE format('REVOKE ALL ON public.%I FROM anon, authenticated', t);
            RAISE NOTICE 'RLS enabled: %', t;
        END IF;
    END LOOP;
END $$;

-- Если когда-то создавалась функция exec_sql (её пытался вызывать старый код
-- при старте) — она позволяет выполнять произвольный SQL. Удаляем.
DROP FUNCTION IF EXISTS public.exec_sql(text);

-- Проверка: у всех таблиц rowsecurity = true
SELECT tablename, rowsecurity FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;
