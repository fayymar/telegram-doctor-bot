import os
from dotenv import load_dotenv
from utils.logger import setup_logger

# Загружаем переменные из .env файла (для локальной разработки)
load_dotenv()

logger = setup_logger(__name__)

# Telegram Bot Token
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is not set")

# Groq API Key
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY environment variable is not set")

# Модель Groq
GROQ_MODEL = "deepseek-r1-distill-qwen-32b"

# Supabase credentials
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL and SUPABASE_KEY environment variables must be set")

# Настройки
DEBUG = os.getenv("DEBUG", "False").lower() == "true"
PORT = int(os.getenv("PORT", 8080))

# FSM Timeout (в секундах)
FSM_TIMEOUT = int(os.getenv("FSM_TIMEOUT", 1800))  # 30 минут по умолчанию

logger.info("✅ Configuration loaded successfully")
logger.info(f"   - Supabase URL: {SUPABASE_URL}")
logger.info(f"   - Port: {PORT}")
logger.info(f"   - Debug mode: {DEBUG}")
logger.info(f"   - FSM timeout: {FSM_TIMEOUT}s")
logger.info(f"   - Groq model: {GROQ_MODEL}")
