"""
Универсальное форматирование телефонных номеров для любых стран
Использует библиотеку phonenumbers (Google libphonenumber)
"""

import phonenumbers
from phonenumbers import NumberParseException
from typing import Tuple, Optional


def format_phone_number(phone_input: str, default_country: str = "UZ") -> Tuple[bool, str, Optional[str]]:
    """
    Форматирует телефонный номер в международный стандарт
    
    Args:
        phone_input: Введённый номер телефона (любой формат)
        default_country: Код страны по умолчанию (ISO 3166-1 alpha-2)
    
    Returns:
        Tuple[bool, str, Optional[str]]:
            - success: True если номер валиден
            - formatted_number: Отформатированный номер или исходная строка
            - error_message: Сообщение об ошибке (если есть)
    
    Примеры:
        >>> format_phone_number("998901234567")
        (True, "+998 90 123 45 67", None)
        
        >>> format_phone_number("79001234567")
        (True, "+7 900 123-45-67", None)
        
        >>> format_phone_number("901234567", "UZ")
        (True, "+998 90 123 45 67", None)
        
        >>> format_phone_number("invalid")
        (False, "invalid", "Неверный формат номера")
    """
    
    # Удаляем все пробелы, дефисы, скобки
    cleaned = phone_input.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    
    # Если номер не начинается с +, добавляем его
    if not cleaned.startswith("+"):
        cleaned = "+" + cleaned
    
    try:
        # Пытаемся распарсить номер
        parsed_number = phonenumbers.parse(cleaned, default_country)
        
        # Проверяем валидность
        if not phonenumbers.is_valid_number(parsed_number):
            # Если номер невалиден, пробуем с кодом страны по умолчанию
            if not cleaned.startswith("+"):
                cleaned_with_country = phone_input.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
                parsed_number = phonenumbers.parse(cleaned_with_country, default_country)
                
                if not phonenumbers.is_valid_number(parsed_number):
                    return False, phone_input, "❌ Номер не соответствует формату ни одной страны"
            else:
                return False, phone_input, "❌ Номер не соответствует формату ни одной страны"
        
        # Форматируем в международный формат
        formatted = phonenumbers.format_number(parsed_number, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
        
        # Получаем информацию о стране
        country_code = phonenumbers.region_code_for_number(parsed_number)
        country_name = get_country_name(country_code)
        
        return True, formatted, None
        
    except NumberParseException as e:
        # Если не удалось распарсить, пробуем добавить код страны по умолчанию
        try:
            # Убираем + если есть
            cleaned_no_plus = cleaned.lstrip("+")
            
            # Пробуем с кодом страны по умолчанию
            parsed_number = phonenumbers.parse(cleaned_no_plus, default_country)
            
            if phonenumbers.is_valid_number(parsed_number):
                formatted = phonenumbers.format_number(parsed_number, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
                return True, formatted, None
            else:
                return False, phone_input, "❌ Неверный формат номера телефона"
                
        except NumberParseException:
            return False, phone_input, f"❌ Не удалось распознать номер телефона"


def get_country_name(country_code: str) -> str:
    """
    Возвращает название страны по коду
    
    Args:
        country_code: ISO код страны (например, "UZ", "RU", "US")
    
    Returns:
        str: Название страны на русском
    """
    countries = {
        "UZ": "Узбекистан",
        "RU": "Россия",
        "KZ": "Казахстан",
        "KG": "Киргизия",
        "TJ": "Таджикистан",
        "TM": "Туркменистан",
        "BY": "Беларусь",
        "UA": "Украина",
        "US": "США",
        "GB": "Великобритания",
        "DE": "Германия",
        "FR": "Франция",
        "TR": "Турция",
        "AE": "ОАЭ",
        "SA": "Саудовская Аравия",
        "CN": "Китай",
        "IN": "Индия",
        "JP": "Япония",
        "KR": "Южная Корея"
    }
    
    return countries.get(country_code, country_code)


def detect_country_from_number(phone_input: str) -> Optional[str]:
    """
    Определяет страну по номеру телефона
    
    Args:
        phone_input: Номер телефона
    
    Returns:
        Optional[str]: ISO код страны или None
    """
    try:
        cleaned = phone_input.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        if not cleaned.startswith("+"):
            cleaned = "+" + cleaned
        
        parsed = phonenumbers.parse(cleaned, None)
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.region_code_for_number(parsed)
    except:
        pass
    
    return None


def get_phone_info(phone_input: str, default_country: str = "UZ") -> dict:
    """
    Получает полную информацию о номере телефона
    
    Args:
        phone_input: Номер телефона
        default_country: Страна по умолчанию
    
    Returns:
        dict: Информация о номере
    """
    try:
        cleaned = phone_input.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        if not cleaned.startswith("+"):
            cleaned = "+" + cleaned
        
        parsed = phonenumbers.parse(cleaned, default_country)
        
        if not phonenumbers.is_valid_number(parsed):
            return {"valid": False}
        
        country_code = phonenumbers.region_code_for_number(parsed)
        number_type = phonenumbers.number_type(parsed)
        
        type_names = {
            phonenumbers.PhoneNumberType.MOBILE: "Мобильный",
            phonenumbers.PhoneNumberType.FIXED_LINE: "Городской",
            phonenumbers.PhoneNumberType.FIXED_LINE_OR_MOBILE: "Мобильный/Городской",
            phonenumbers.PhoneNumberType.TOLL_FREE: "Бесплатный",
            phonenumbers.PhoneNumberType.PREMIUM_RATE: "Платный",
            phonenumbers.PhoneNumberType.VOIP: "VoIP"
        }
        
        return {
            "valid": True,
            "formatted": phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL),
            "e164": phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164),
            "country_code": country_code,
            "country_name": get_country_name(country_code),
            "number_type": type_names.get(number_type, "Неизвестно")
        }
        
    except:
        return {"valid": False}


# Примеры использования
if __name__ == "__main__":
    test_numbers = [
        "998901234567",           # Узбекистан с кодом
        "90 123 45 67",          # Узбекистан без кода
        "+7 900 123-45-67",      # Россия
        "79001234567",           # Россия без +
        "+1 (555) 123-4567",     # США
        "+44 20 7946 0958",      # Великобритания
        "+86 138 0013 8000",     # Китай
        "invalid",               # Невалидный
    ]
    
    print("=== ТЕСТИРОВАНИЕ ФОРМАТИРОВАНИЯ ===\n")
    
    for number in test_numbers:
        success, formatted, error = format_phone_number(number)
        
        if success:
            info = get_phone_info(number)
            print(f"✅ Вход:  {number}")
            print(f"   Выход: {formatted}")
            print(f"   Страна: {info.get('country_name', 'N/A')} ({info.get('country_code', 'N/A')})")
            print(f"   Тип: {info.get('number_type', 'N/A')}")
            print(f"   E164: {info.get('e164', 'N/A')}")
        else:
            print(f"❌ Вход:  {number}")
            print(f"   Ошибка: {error}")
        
        print()
