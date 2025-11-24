"""Настройка логирования для всего приложения"""
import logging
import sys
from typing import Optional


def setup_logger(name: str, level: Optional[int] = None) -> logging.Logger:
    """
    Создает и настраивает logger для модуля

    Args:
        name: Имя модуля (обычно __name__)
        level: Уровень логирования (по умолчанию INFO)

    Returns:
        Настроенный logger
    """
    logger = logging.getLogger(name)

    # Если уже настроен - возвращаем
    if logger.handlers:
        return logger

    # Устанавливаем уровень
    logger.setLevel(level or logging.INFO)

    # Создаем форматтер
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Хендлер для консоли
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger
