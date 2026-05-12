import os
import asyncio
from functools import partial
from supabase import create_client, Client
from utils.logger import setup_logger

logger = setup_logger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError(
        "Missing Supabase credentials. "
        "Please set SUPABASE_URL and SUPABASE_KEY environment variables."
    )

supabase_client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

logger.info("✅ Supabase client initialized successfully")


async def run_query(func, *args, **kwargs):
    """
    Запускает синхронный вызов Supabase в отдельном потоке
    чтобы не блокировать asyncio event loop.
    
    Использование:
        result = await run_query(
            lambda: supabase_client.table('users').select('*').execute()
        )
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, partial(func, *args, **kwargs))
