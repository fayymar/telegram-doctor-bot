import os
from supabase import create_client, Client


# Получаем переменные окружения
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Проверяем наличие переменных
if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError(
        "Missing Supabase credentials. "
        "Please set SUPABASE_URL and SUPABASE_KEY environment variables."
    )

# Создаём клиент Supabase
supabase_client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

print("✅ Supabase client initialized successfully")
