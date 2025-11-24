"""Утилиты для экспорта анамнеза пользователя"""
import json
from datetime import datetime
from typing import Dict, List, Optional
from io import StringIO

from utils.health_calculator import calculate_bmi, get_bmi_category


def format_anamnesis_text(
    user_profile: Dict,
    consultations: List[Dict]
) -> str:
    """
    Форматирует анамнез пользователя в текстовый формат

    Args:
        user_profile: Профиль пользователя из БД
        consultations: Список консультаций

    Returns:
        Отформатированный текст анамнеза
    """
    output = StringIO()

    # Заголовок
    output.write("=" * 60 + "\n")
    output.write("МЕДИЦИНСКИЙ АНАМНЕЗ\n")
    output.write("=" * 60 + "\n\n")

    # Дата экспорта
    export_date = datetime.now().strftime("%d.%m.%Y %H:%M")
    output.write(f"Дата экспорта: {export_date}\n\n")

    # Личные данные
    output.write("-" * 60 + "\n")
    output.write("ЛИЧНЫЕ ДАННЫЕ\n")
    output.write("-" * 60 + "\n\n")

    full_name = user_profile.get('full_name', 'Не указано')
    output.write(f"ФИО: {full_name}\n")

    # Возраст из даты рождения
    birthdate = user_profile.get('birthdate')
    if birthdate:
        try:
            birth_date_obj = datetime.fromisoformat(str(birthdate))
            age = (datetime.now() - birth_date_obj).days // 365
            output.write(f"Дата рождения: {birth_date_obj.strftime('%d.%m.%Y')} (возраст: {age} лет)\n")
        except:
            output.write(f"Дата рождения: {birthdate}\n")
    else:
        output.write("Дата рождения: Не указано\n")

    gender_map = {
        'male': 'Мужской',
        'female': 'Женский',
        'other': 'Другой'
    }
    gender = gender_map.get(user_profile.get('gender'), 'Не указано')
    output.write(f"Пол: {gender}\n")

    phone = user_profile.get('phone', 'Не указано')
    output.write(f"Телефон: {phone}\n")

    # Физические параметры
    output.write("\n" + "-" * 60 + "\n")
    output.write("ФИЗИЧЕСКИЕ ПАРАМЕТРЫ\n")
    output.write("-" * 60 + "\n\n")

    height = user_profile.get('height')
    weight = user_profile.get('weight')

    if height:
        output.write(f"Рост: {height} см\n")
    else:
        output.write("Рост: Не указано\n")

    if weight:
        output.write(f"Вес: {weight} кг\n")
    else:
        output.write("Вес: Не указано\n")

    # ИМТ
    if height and weight:
        try:
            bmi = calculate_bmi(weight, height)
            category, emoji, recommendation = get_bmi_category(bmi)
            output.write(f"ИМТ: {bmi} ({category})\n")
            output.write(f"Рекомендация: {recommendation}\n")
        except:
            output.write("ИМТ: Не удалось рассчитать\n")
    else:
        output.write("ИМТ: Недостаточно данных для расчета\n")

    # История консультаций
    output.write("\n" + "=" * 60 + "\n")
    output.write("ИСТОРИЯ КОНСУЛЬТАЦИЙ\n")
    output.write("=" * 60 + "\n\n")

    if not consultations or len(consultations) == 0:
        output.write("Консультации отсутствуют\n")
    else:
        output.write(f"Всего консультаций: {len(consultations)}\n\n")

        for idx, consultation in enumerate(consultations, 1):
            output.write("-" * 60 + "\n")
            output.write(f"КОНСУЛЬТАЦИЯ #{idx}\n")
            output.write("-" * 60 + "\n\n")

            # Дата
            try:
                created = datetime.fromisoformat(consultation['created_at'].replace('Z', '+00:00'))
                date_str = created.strftime('%d.%m.%Y в %H:%M')
                output.write(f"Дата: {date_str}\n\n")
            except:
                output.write(f"Дата: {consultation.get('created_at', 'Не указано')}\n\n")

            # Симптомы
            try:
                symptoms_data = json.loads(consultation['symptoms'])
                main_symptoms = symptoms_data.get('main', 'не указано')
                duration = symptoms_data.get('duration', 'не указано')
                additional = symptoms_data.get('additional', [])

                output.write("Основные симптомы:\n")
                output.write(f"  {main_symptoms}\n\n")

                output.write(f"Давность: {duration}\n\n")

                if additional and len(additional) > 0:
                    output.write("Дополнительные симптомы:\n")
                    for symptom in additional:
                        output.write(f"  • {symptom}\n")
                    output.write("\n")
                else:
                    output.write("Дополнительные симптомы: Нет\n\n")
            except:
                output.write("Симптомы: Не удалось загрузить\n\n")

            # Рекомендации
            specialist = consultation.get('recommended_doctor', 'Не указано')
            output.write(f"Рекомендованный специалист: {specialist}\n")

            urgency = consultation.get('urgency_level', 'Не указано')
            urgency_map = {
                'low': 'Низкая (плановый приём)',
                'medium': 'Средняя (в течение недели)',
                'high': 'Высокая (в течение 24 часов)',
                'emergency': 'СРОЧНО! Требуется скорая помощь'
            }
            urgency_text = urgency_map.get(urgency, urgency)
            output.write(f"Срочность: {urgency_text}\n\n")

    # Футер
    output.write("=" * 60 + "\n")
    output.write("КОНЕЦ ДОКУМЕНТА\n")
    output.write("=" * 60 + "\n\n")

    output.write("Этот документ создан автоматически Telegram Medical Bot\n")
    output.write("Документ носит информационный характер и не является\n")
    output.write("официальным медицинским заключением.\n")

    result = output.getvalue()
    output.close()

    return result


def generate_filename(user_id: int, full_name: Optional[str] = None) -> str:
    """
    Генерирует имя файла для экспорта

    Args:
        user_id: ID пользователя
        full_name: ФИО пользователя (опционально)

    Returns:
        Имя файла
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if full_name:
        # Убираем пробелы и специальные символы из имени
        safe_name = "".join(c for c in full_name if c.isalnum() or c in (' ', '_')).strip()
        safe_name = safe_name.replace(' ', '_')
        return f"anamnesis_{safe_name}_{timestamp}.txt"
    else:
        return f"anamnesis_user{user_id}_{timestamp}.txt"
