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

    if len(full_name) > 100:
        return False, "❌ Имя слишком длинное (максимум 100 символов)"

    # Принимаем любое имя — одно слово или несколько, любой регистр
    return True, ""


def validate_birthdate(date_string: str) -> Tuple[bool, str, datetime | None]:
    """
    Гибкий парсер дат рождения.
    Принимает десятки форматов: числовые, текстовые, сокращённые, смешанные.
    """
    s = date_string.strip()

    # ── Словари для текстовых месяцев ─────────────────────────────────────
    MONTHS_RU = {
        "янв": 1, "январь": 1, "января": 1,
        "фев": 2, "февраль": 2, "февраля": 2,
        "мар": 3, "март": 3, "марта": 3,
        "апр": 4, "апрель": 4, "апреля": 4,
        "май": 5, "мая": 5,
        "июн": 6, "июнь": 6, "июня": 6,
        "июл": 7, "июль": 7, "июля": 7,
        "авг": 8, "август": 8, "августа": 8,
        "сен": 9, "сентябрь": 9, "сентября": 9,
        "окт": 10, "октябрь": 10, "октября": 10,
        "ноя": 11, "ноябрь": 11, "ноября": 11,
        "дек": 12, "декабрь": 12, "декабря": 12,
    }
    MONTHS_UZ = {
        "yan": 1, "yanvar": 1,
        "fev": 2, "fevral": 2,
        "mar": 3, "mart": 3,
        "apr": 4, "aprel": 4,
        "may": 5,
        "iyn": 6, "iyun": 6,
        "iyl": 7, "iyul": 7,
        "avg": 8, "avgust": 8,
        "sen": 9, "sentabr": 9,
        "okt": 10, "oktabr": 10,
        "noy": 11, "noyabr": 11,
        "dek": 12, "dekabr": 12,
    }

    def _fix_year(y: int) -> int:
        """Превращает 2-значный год в 4-значный: 94 → 1994, 05 → 2005."""
        if y < 100:
            return 1900 + y if y >= 10 else 2000 + y
        return y

    def _make_date(d: int, m: int, y: int) -> datetime | None:
        try:
            return datetime(y, m, d)
        except ValueError:
            return None

    # ── 1. Числовые форматы ────────────────────────────────────────────────
    # Заменяем разделители на точки, убираем лишние пробелы
    normalized = re.sub(r"[/\\-]", ".", s)
    normalized = re.sub(r"\s+", ".", normalized)

    # ДД.ММ.ГГГГ и ДД.ММ.ГГ
    m_num = re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.(\d{2,4})", normalized)
    if m_num:
        d, mo, y = int(m_num[1]), int(m_num[2]), _fix_year(int(m_num[3]))
        dt = _make_date(d, mo, y)
        if dt:
            birthdate = dt
            goto_check = True
        else:
            return False, "❌ Неверная дата. Проверьте день и месяц.", None

    # ГГГГ.ММ.ДД (ISO)
    elif re.fullmatch(r"\d{4}\.\d{1,2}\.\d{1,2}", normalized):
        parts = normalized.split(".")
        dt = _make_date(int(parts[2]), int(parts[1]), int(parts[0]))
        if dt:
            birthdate = dt
            goto_check = True
        else:
            return False, "❌ Неверная дата.", None

    # ── 2. Текстовые форматы ───────────────────────────────────────────────
    else:
        # Приводим к нижнему регистру, разбиваем на токены
        lower = s.lower()
        tokens = re.split(r"[\s.,]+", lower)
        tokens = [t for t in tokens if t]

        month_num = None
        day_num = None
        year_num = None

        for tok in tokens:
            # Месяц словарём (ru или uz)
            if tok in MONTHS_RU:
                month_num = MONTHS_RU[tok]
            elif tok in MONTHS_UZ:
                month_num = MONTHS_UZ[tok]
            # Год (4 цифры)
            elif re.fullmatch(r"\d{4}", tok):
                year_num = int(tok)
            # День или 2-значный год
            elif re.fullmatch(r"\d{1,2}", tok):
                val = int(tok)
                if day_num is None and 1 <= val <= 31:
                    day_num = val
                elif year_num is None:
                    year_num = _fix_year(val)

        # Если год не нашли, но есть 2-значное число после дня
        if year_num is None and day_num is not None:
            for tok in tokens:
                if re.fullmatch(r"\d{2}", tok):
                    year_num = _fix_year(int(tok))
                    break

        if not all([day_num, month_num, year_num]):
            missing = []
            if not day_num:   missing.append("день")
            if not month_num: missing.append("месяц")
            if not year_num:  missing.append("год")
            return False, (
                f"❌ Не удалось распознать: {', '.join(missing)}\n\n"
                "Попробуйте: 06.11.1994 или 6 ноя 94 или 6 ноября 1994"
            ), None

        dt = _make_date(day_num, month_num, year_num)
        if not dt:
            return False, "❌ Неверная дата. Проверьте день и месяц.", None
        birthdate = dt
        goto_check = True

    # ── Проверки после парсинга ───────────────────────────────────────────
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
