"""Утилиты для retry логики при сбоях"""
import asyncio
import time
from typing import Callable, Any, Optional, TypeVar
from functools import wraps
from utils.logger import setup_logger

logger = setup_logger(__name__)

T = TypeVar('T')


def retry_on_failure(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,)
):
    """
    Декоратор для автоматического повтора при ошибке

    Args:
        max_attempts: Максимальное количество попыток
        delay: Начальная задержка между попытками (в секундах)
        backoff: Множитель для экспоненциальной задержки
        exceptions: Кортеж исключений для перехвата

    Example:
        @retry_on_failure(max_attempts=3, delay=1.0)
        def unstable_function():
            # код который может упасть
            pass
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            current_delay = delay
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    logger.warning(
                        f"Attempt {attempt}/{max_attempts} failed for {func.__name__}: {e}"
                    )

                    if attempt < max_attempts:
                        logger.info(f"Retrying in {current_delay:.1f} seconds...")
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(
                            f"All {max_attempts} attempts failed for {func.__name__}"
                        )

            # Если все попытки исчерпаны - пробрасываем последнее исключение
            if last_exception:
                raise last_exception

        return wrapper
    return decorator


async def async_retry_on_failure(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,)
):
    """
    Декоратор для автоматического повтора асинхронных функций при ошибке

    Args:
        max_attempts: Максимальное количество попыток
        delay: Начальная задержка между попытками (в секундах)
        backoff: Множитель для экспоненциальной задержки
        exceptions: Кортеж исключений для перехвата
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            current_delay = delay
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    logger.warning(
                        f"Attempt {attempt}/{max_attempts} failed for {func.__name__}: {e}"
                    )

                    if attempt < max_attempts:
                        logger.info(f"Retrying in {current_delay:.1f} seconds...")
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(
                            f"All {max_attempts} attempts failed for {func.__name__}"
                        )

            # Если все попытки исчерпаны - пробрасываем последнее исключение
            if last_exception:
                raise last_exception

        return wrapper
    return decorator


def safe_execute(func: Callable[..., T], default: T, *args, **kwargs) -> T:
    """
    Безопасно выполняет функцию с fallback значением

    Args:
        func: Функция для выполнения
        default: Значение по умолчанию при ошибке
        *args: Аргументы функции
        **kwargs: Именованные аргументы функции

    Returns:
        Результат функции или default при ошибке
    """
    try:
        return func(*args, **kwargs)
    except Exception as e:
        logger.error(f"Error executing {func.__name__}: {e}. Using default value")
        return default
