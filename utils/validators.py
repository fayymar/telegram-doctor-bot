"""Валидаторы для регистрации и редактирования профиля"""
import re
from datetime import datetime
from typing import Tuple


def validate_full_name(full_name: str) -> Tuple[bool, str]:
    """
    Валидация ФИО

    Args:
        full_name: Введенное ФИО

    Returns:
        (is_valid, error_message): True если валидно, иначе текст ошибки
    """
    full_name = full_name.strip()

    # Проверка длины
    if len(full_name) < 3:
        return False, "❌ ФИО слишком короткое (минимум 3 символа)"

    # Проверка на минимум 2 слова
    words = full_name.split()
    if len(words) < 2:
        return False, "❌ Пожалуйста, укажите хотя бы Фамилию и Имя\nНапример: Иванов Иван"

    # Проверка на максимальную длину
    if len(full_name) > 100:
        return False, "❌ ФИО слишком длинное (максимум 100 символов)"

    # Проверка на допустимые символы (буквы, пробелы, дефисы, апострофы)
    # Поддерживаем кириллицу, латиницу и базовые символы
    if not re.match(r"^[a-zA-Zа-яА-ЯёЁ\s\-']+$", full_name):
        return False, "❌ ФИО должно содержать только буквы, пробелы и дефисы\nБез цифр и специальных символов"

    # Проверка что каждое слово начинается с заглавной буквы
    for word in words:
        if len(word) > 0 and not word[0].isupper():
            return False, "❌ Каждое слово должно начинаться с заглавной буквы\nНапример: Иванов Иван Петрович"

    # Проверка что нет слов из одной буквы (кроме инициалов в конце)
    for i, word in enumerate(words[:-1]):  # Проверяем все кроме последнего
        if len(word) < 2:
            return False, "❌ Имя и фамилия должны содержать минимум 2 буквы"

    return True, ""


def validate_birthdate(date_string: str) -> Tuple[bool, str, datetime | None]:
    """
    Валидация даты рождения

    Args:
        date_string: Введенная дата

    Returns:
        (is_valid, error_message, parsed_date): True если валидно, иначе текст ошибки
    """
    date_string = date_string.strip()

    # Заменяем все разделители на точку
    normalized = date_string.replace("/", ".").replace(" ", ".").replace("-", ".")

    # Пробуем распарсить
    try:
        birthdate = datetime.strptime(normalized, "%d.%m.%Y")
    except ValueError:
        return False, "❌ Неверный формат даты\n\nИспользуйте формат: ДД.ММ.ГГГГ\nНапример: 15.03.1990", None

    # Проверка что дата не в будущем
    if birthdate > datetime.now():
        return False, "❌ Дата рождения не может быть в будущем", None

    # Вычисляем возраст
    age = (datetime.now() - birthdate).days // 365

    # Проверка минимального возраста (14 лет)
    if age < 14:
        return False, "❌ Минимальный возраст для регистрации: 14 лет", None

    # Проверка максимального возраста
    if age > 120:
        return False, "❌ Пожалуйста, укажите корректную дату рождения", None

    return True, "", birthdate


def validate_height(height_str: str) -> Tuple[bool, str, int | None]:
    """
    Валидация роста

    Args:
        height_str: Введенный рост

    Returns:
        (is_valid, error_message, height): True если валидно, иначе текст ошибки
    """
    height_str = height_str.strip()

    try:
        # Убираем возможные единицы измерения
        height_str = height_str.lower().replace("см", "").replace("cm", "").strip()

        # Парсим число
        height = int(height_str)

        # Проверка разумных пределов
        if height < 50:
            return False, "❌ Рост слишком маленький (минимум 50 см)", None

        if height > 250:
            return False, "❌ Рост слишком большой (максимум 250 см)", None

        return True, "", height

    except ValueError:
        return False, "❌ Пожалуйста, введите число\nНапример: 175", None


def validate_weight(weight_str: str) -> Tuple[bool, str, float | None]:
    """
    Валидация веса

    Args:
        weight_str: Введенный вес

    Returns:
        (is_valid, error_message, weight): True если валидно, иначе текст ошибки
    """
    weight_str = weight_str.strip()

    try:
        # Убираем возможные единицы измерения
        weight_str = weight_str.lower().replace("кг", "").replace("kg", "").strip()

        # Заменяем запятую на точку
        weight_str = weight_str.replace(",", ".")

        # Парсим число
        weight = float(weight_str)

        # Проверка разумных пределов
        if weight < 20:
            return False, "❌ Вес слишком маленький (минимум 20 кг)", None

        if weight > 300:
            return False, "❌ Вес слишком большой (максимум 300 кг)", None

        # Проверка на разумное количество знаков после запятой
        if "." in str(weight):
            decimal_places = len(str(weight).split(".")[1])
            if decimal_places > 1:
                return False, "❌ Укажите вес с точностью до 1 знака после запятой\nНапример: 70.5", None

        return True, "", weight

    except ValueError:
        return False, "❌ Пожалуйста, введите число\nНапример: 70 или 70.5", None


def validate_text_input(text: str, min_length: int = 1, max_length: int = 1000) -> Tuple[bool, str]:
    """
    Валидация текстового ввода (для симптомов, комментариев и т.д.)

    Args:
        text: Введенный текст
        min_length: Минимальная длина
        max_length: Максимальная длина

    Returns:
        (is_valid, error_message): True если валидно, иначе текст ошибки
    """
    text = text.strip()

    if len(text) < min_length:
        return False, f"❌ Текст слишком короткий (минимум {min_length} символов)"

    if len(text) > max_length:
        return False, f"❌ Текст слишком длинный (максимум {max_length} символов)"

    # Проверка на подозрительное содержимое (защита от спама)
    # Проверяем наличие большого количества одинаковых символов подряд
    if re.search(r'(.)\1{20,}', text):
        return False, "❌ Текст содержит подозрительные повторяющиеся символы"

    # Проверка на URL (если это не предполагается)
    url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
    if re.search(url_pattern, text):
        return False, "❌ Текст не должен содержать ссылки"

    return True, ""


def sanitize_text(text: str) -> str:
    """
    Очищает текст от потенциально опасного содержимого

    Args:
        text: Исходный текст

    Returns:
        Очищенный текст
    """
    # Убираем множественные пробелы
    text = re.sub(r'\s+', ' ', text)

    # Убираем пробелы в начале и конце
    text = text.strip()

    return text
