"""Утилиты для безопасного парсинга JSON из AI ответов"""
import json
import re
from typing import Optional, Dict, List, Union
from utils.logger import setup_logger

logger = setup_logger(__name__)


def extract_json_from_text(text: str, json_type: str = "object") -> Optional[Union[Dict, List]]:
    """
    Извлекает JSON из текста AI, пытаясь разные стратегии

    Args:
        text: Текст от AI, который может содержать JSON
        json_type: Тип ожидаемого JSON ("object" для {...} или "array" для [...])

    Returns:
        Распарсенный JSON или None если не удалось
    """
    if not text or not text.strip():
        logger.warning("Empty text provided for JSON extraction")
        return None

    # Стратегия 1: Попробовать распарсить весь текст
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    # Стратегия 2: Найти JSON через regex
    if json_type == "object":
        pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
    else:  # array
        pattern = r'\[[^\[\]]*(?:\[[^\[\]]*\][^\[\]]*)*\]'

    matches = re.finditer(pattern, text, re.DOTALL)

    # Пробуем каждый match от самого длинного
    for match in sorted(matches, key=lambda m: len(m.group()), reverse=True):
        try:
            json_str = match.group()
            parsed = json.loads(json_str)
            logger.debug(f"Successfully extracted JSON using regex: {json_str[:100]}...")
            return parsed
        except json.JSONDecodeError:
            continue

    # Стратегия 3: Найти JSON между маркерами ```json ... ```
    json_block_match = re.search(r'```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```', text, re.DOTALL)
    if json_block_match:
        try:
            parsed = json.loads(json_block_match.group(1))
            logger.debug("Successfully extracted JSON from code block")
            return parsed
        except json.JSONDecodeError:
            pass

    logger.warning(f"Failed to extract JSON from text: {text[:200]}...")
    return None


def safe_parse_json_object(text: str, default: Optional[Dict] = None) -> Dict:
    """
    Безопасно парсит JSON объект с fallback

    Args:
        text: Текст для парсинга
        default: Значение по умолчанию если парсинг не удался

    Returns:
        Распарсенный dict или default
    """
    result = extract_json_from_text(text, json_type="object")

    if result is None:
        logger.warning(f"Using default value for failed JSON parse")
        return default or {}

    if not isinstance(result, dict):
        logger.warning(f"Expected dict, got {type(result)}. Using default")
        return default or {}

    return result


def safe_parse_json_array(text: str, default: Optional[List] = None) -> List:
    """
    Безопасно парсит JSON массив с fallback

    Args:
        text: Текст для парсинга
        default: Значение по умолчанию если парсинг не удался

    Returns:
        Распарсенный list или default
    """
    result = extract_json_from_text(text, json_type="array")

    if result is None:
        logger.warning(f"Using default value for failed JSON parse")
        return default or []

    if not isinstance(result, list):
        logger.warning(f"Expected list, got {type(result)}. Using default")
        return default or []

    return result


def validate_json_structure(data: Dict, required_keys: List[str]) -> bool:
    """
    Проверяет что JSON содержит все требуемые ключи

    Args:
        data: Распарсенный JSON
        required_keys: Список обязательных ключей

    Returns:
        True если все ключи присутствуют
    """
    missing_keys = [key for key in required_keys if key not in data]

    if missing_keys:
        logger.warning(f"Missing required keys in JSON: {missing_keys}")
        return False

    return True
