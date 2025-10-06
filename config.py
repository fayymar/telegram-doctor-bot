import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Bot Token
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Google Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Проверка наличия всех необходимых переменных
required_vars = {
    "BOT_TOKEN": BOT_TOKEN,
    "GEMINI_API_KEY": GEMINI_API_KEY,
    "SUPABASE_URL": SUPABASE_URL,
    "SUPABASE_KEY": SUPABASE_KEY,
}

missing_vars = [key for key, value in required_vars.items() if not value]
if missing_vars:
    raise ValueError(f"Отсутствуют обязательные переменные окружения: {', '.join(missing_vars)}")
