"""Калькуляторы здоровья (ИМТ, идеальный вес и т.д.)"""
from typing import Tuple, Optional


def calculate_bmi(weight_kg: float, height_cm: int) -> float:
    """
    Рассчитывает Индекс Массы Тела (ИМТ/BMI)

    Args:
        weight_kg: Вес в килограммах
        height_cm: Рост в сантиметрах

    Returns:
        ИМТ (округленный до 1 знака)
    """
    height_m = height_cm / 100
    bmi = weight_kg / (height_m ** 2)
    return round(bmi, 1)


def get_bmi_category(bmi: float) -> Tuple[str, str, str]:
    """
    Определяет категорию ИМТ и рекомендации

    Args:
        bmi: Индекс массы тела

    Returns:
        (категория, эмодзи, рекомендация)
    """
    if bmi < 16:
        return "Выраженный дефицит массы", "⚠️", "Критически низкий вес. Необходима консультация врача!"
    elif bmi < 18.5:
        return "Недостаточная масса", "⚡", "Рекомендуется набор веса под наблюдением врача"
    elif bmi < 25:
        return "Норма", "✅", "Вес в пределах нормы. Отличный результат!"
    elif bmi < 30:
        return "Избыточная масса", "⚠️", "Рекомендуется снижение веса и физическая активность"
    elif bmi < 35:
        return "Ожирение I степени", "🔴", "Необходима консультация диетолога"
    elif bmi < 40:
        return "Ожирение II степени", "🔴", "Высокий риск для здоровья. Обратитесь к врачу"
    else:
        return "Ожирение III степени", "🔴", "Критическое состояние. Срочно к врачу!"


def get_ideal_weight_range(height_cm: int, gender: str = None) -> Tuple[float, float]:
    """
    Рассчитывает диапазон идеального веса по формуле Devine

    Args:
        height_cm: Рост в сантиметрах
        gender: Пол ('male', 'female' или None для усредненного)

    Returns:
        (мин_вес, макс_вес) в кг
    """
    height_m = height_cm / 100

    # Используем диапазон ИМТ 18.5-24.9 (норма)
    min_bmi = 18.5
    max_bmi = 24.9

    min_weight = min_bmi * (height_m ** 2)
    max_weight = max_bmi * (height_m ** 2)

    return round(min_weight, 1), round(max_weight, 1)


def format_bmi_info(weight_kg: float, height_cm: int, gender: str = None) -> str:
    """
    Форматирует полную информацию об ИМТ

    Args:
        weight_kg: Вес в килограммах
        height_cm: Рост в сантиметрах
        gender: Пол (опционально)

    Returns:
        Отформатированная строка с информацией об ИМТ
    """
    bmi = calculate_bmi(weight_kg, height_cm)
    category, emoji, recommendation = get_bmi_category(bmi)
    min_weight, max_weight = get_ideal_weight_range(height_cm, gender)

    info = f"📊 *Индекс массы тела (ИМТ)*\n\n"
    info += f"{emoji} *ИМТ:* {bmi}\n"
    info += f"*Категория:* {category}\n\n"
    info += f"💡 *Рекомендация:*\n{recommendation}\n\n"
    info += f"⚖️ *Идеальный вес для вашего роста:*\n"
    info += f"{min_weight}-{max_weight} кг"

    # Показываем разницу с текущим весом
    if weight_kg < min_weight:
        diff = round(min_weight - weight_kg, 1)
        info += f"\n\n📈 Для достижения нормы: +{diff} кг"
    elif weight_kg > max_weight:
        diff = round(weight_kg - max_weight, 1)
        info += f"\n\n📉 Для достижения нормы: -{diff} кг"

    return info


def calculate_age(birthdate_str: str) -> Optional[int]:
    """
    Вычисляет возраст по дате рождения

    Args:
        birthdate_str: Дата рождения в формате ISO (YYYY-MM-DD)

    Returns:
        Возраст в годах или None если не удалось вычислить
    """
    try:
        from datetime import datetime
        birthdate = datetime.fromisoformat(birthdate_str)
        today = datetime.now()
        age = today.year - birthdate.year
        # Корректируем если день рождения еще не наступил в этом году
        if (today.month, today.day) < (birthdate.month, birthdate.day):
            age -= 1
        return age
    except Exception:
        return None
