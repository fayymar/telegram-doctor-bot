"""Валидаторы для регистрации и редактирования профиля"""
import re
from datetime import datetime
from typing import Tuple


def validate_full_name(full_name: str) -> Tuple[bool, str]:
    """
    Валидация ФИО
    """
    full_name = full_name.strip()

    if len(full_name) < 3:
        return False, "❌ ФИО слишком короткое (минимум 3 символа)"

    words = full_name.split()
    if len(words) < 2:
        return False, "❌ Пожалуйста, укажите хотя бы Фамилию и Имя\nНапример: Иванов Иван"

    if len(full_name) > 100:
        return False, "❌ ФИО слишком длинное (максимум 100 символов)"

    if not re.match(r"^[a-zA-Zа-яА-ЯёЁ\s\-']+$", full_name):
        return False, "❌ ФИО должно содержать только буквы, пробелы и дефисы\nБез цифр и специальных символов"

    for word in words:
        if len(word) > 0 and not word[0].isupper():
            return False, "❌ Каждое слово должно начинаться с заглавной буквы\nНапример: Иванов Иван Петрович"

    for word in words[:-1]:
        if len(word) < 2:
            return False, "❌ Имя и фамилия должны содержать минимум 2 буквы"

    return True, ""


def validate_birthdate(date_string: str) -> Tuple[bool, str, datetime | None]:
    """
    Валидация даты рождения
    """
    date_string = date_string.strip()

    normalized = date_string.replace("/", ".").replace(" ", ".").replace("-", ".")

    try:
        birthdate = datetime.strptime(normalized, "%d.%m.%Y")
    except ValueError:
        return False, "❌ Неверный формат даты\n\nИспользуйте формат: ДД.ММ.ГГГГ\nНапример: 15.03.1990", None

    if birthdate > datetime.now():
        return False, "❌ Дата рождения не может быть в будущем", None

    age = (datetime.now() - birthdate).days // 365

    if age < 14:
        return False, "❌ Минимальный возраст для регистрации: 14 лет", None

    if age > 120:
        return False, "❌ Пожалуйста, укажите корректную дату рождения", None

    return True, "", birthdate


def validate_age_or_birthdate(value: str) -> Tuple[bool, str, datetime | None, int | None]:
    """
    Принимает либо возраст числом (например, 29),
    либо дату рождения (например, 15.03.1990).

    Возвращает:
    (is_valid, error_message, birthdate, age)

    В БД сохраняем birthdate, чтобы не ломать существующую схему.
    Если пользователь ввёл только возраст, сохраняем 01.01.<год рождения>.
    """
    value = value.strip()

    if re.fullmatch(r"\d{1,3}", value):
        age = int(value)

        if age < 14:
            return False, "❌ Минимальный возраст для регистрации: 14 лет", None, None

        if age > 120:
            return False, "❌ Пожалуйста, укажите корректный возраст", None, None

        current_year = datetime.now().year
        birth_year = current_year - age
        birthdate = datetime(birth_year, 1, 1)

        return True, "", birthdate, age

    is_valid, error_message, birthdate = validate_birthdate(value)
    if not is_valid or birthdate is None:
        return False, (
            "❌ Введите возраст числом или дату рождения\n\n"
            "Примеры:\n"
            "• 29\n"
            "• 15.03.1990"
        ), None, None

    age = (datetime.now() - birthdate).days // 365
    return True, "", birthdate, age


def validate_height(height_str: str) -> Tuple[bool, str, int | None]:
    """
    Валидация роста
    """
    height_str = height_str.strip()

    try:
        height_str = height_str.lower().replace("см", "").replace("cm", "").strip()
        height = int(height_str)

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
    """
    weight_str = weight_str.strip()

    try:
        weight_str = weight_str.lower().replace("кг", "").replace("kg", "").strip()
        weight_str = weight_str.replace(",", ".")

        weight = float(weight_str)

        if weight < 20:
            return False, "❌ Вес слишком маленький (минимум 20 кг)", None

        if weight > 300:
            return False, "❌ Вес слишком большой (максимум 300 кг)", None

        if "." in str(weight):
            decimal_places = len(str(weight).split(".")[1])
            if decimal_places > 1:
                return False, "❌ Укажите вес с точностью до 1 знака после запятой\nНапример: 70.5", None

        return True, "", weight

    except ValueError:
        return False, "❌ Пожалуйста, введите число\nНапример: 70 или 70.5", None


def validate_text_input(text: str, min_length: int = 1, max_length: int = 1000) -> Tuple[bool, str]:
    """
    Валидация текстового ввода
    """
    text = text.strip()

    if len(text) < min_length:
        return False, f"❌ Текст слишком короткий (минимум {min_length} символов)"

    if len(text) > max_length:
        return False, f"❌ Текст слишком длинный (максимум {max_length} символов)"

    if re.search(r'(.)\1{20,}', text):
        return False, "❌ Текст содержит подозрительные повторяющиеся символы"

    url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
    if re.search(url_pattern, text):
        return False, "❌ Текст не должен содержать ссылки"

    return True, ""


def sanitize_text(text: str) -> str:
    """
    Очистка текста
    """
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    return text
