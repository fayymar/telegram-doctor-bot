import logging
import sys
import os
from logging.handlers import RotatingFileHandler
from typing import Optional


def setup_logger(name: str, level: Optional[int] = None) -> logging.Logger:
    """
    Настройка логгера с:
    - Выводом в stdout (для Render)
    - Ротацией файлов (локально / если LOG_DIR задан)
    - Структурированным форматом
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(level or logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Stdout handler (всегда — для Render logs)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler с ротацией (опционально — если LOG_DIR задан)
    log_dir = os.getenv("LOG_DIR", "")
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "bot.log")
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=5 * 1024 * 1024,  # 5 MB
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger
