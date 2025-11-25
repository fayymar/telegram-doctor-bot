from aiogram.fsm.state import State, StatesGroup


class Registration(StatesGroup):
    """Состояния для регистрации пользователя"""
    choosing_language = State()  # Выбор языка
    waiting_for_full_name = State()
    waiting_for_phone = State()
    waiting_for_birthdate = State()
    waiting_for_gender = State()
    waiting_for_height = State()
    waiting_for_weight = State()


class EditProfile(StatesGroup):
    """Состояния для редактирования профиля"""
    choosing_field = State()  # Выбор поля для редактирования
    waiting_for_full_name = State()
    waiting_for_phone = State()
    waiting_for_birthdate = State()
    waiting_for_gender = State()
    waiting_for_height = State()
    waiting_for_weight = State()


class Consultation(StatesGroup):
    """Состояния для консультации"""
    # Этап 1: Основные симптомы
    waiting_for_symptoms = State()
    confirming_symptoms = State()

    # Этап 2: Дополнительные симптомы (первый выбор)
    selecting_additional_symptoms = State()
    waiting_for_other_symptoms = State()

    # Этап 3: Уточняющие симптомы (второй выбор)
    selecting_clarifying_symptoms = State()
    waiting_for_clarifying_symptoms = State()

    # Этап 4: Давность симптомов
    waiting_for_duration = State()

    # Этап 5: Финальное подтверждение
    final_confirmation = State()


class FindSpecialist(StatesGroup):
    """Состояния для поиска специалиста"""
    choosing_category = State()
    viewing_specialists = State()


class ViewHistory(StatesGroup):
    """Состояния для просмотра истории"""
    viewing_list = State()  # Просмотр списка консультаций
    viewing_details = State()  # Просмотр деталей конкретной консультации


class MedicationReminder(StatesGroup):
    """Состояния для напоминаний о лекарствах"""
    waiting_for_medication_name = State()
    waiting_for_dosage = State()
    waiting_for_frequency = State()
    waiting_for_times = State()
    waiting_for_start_date = State()
    waiting_for_end_date = State()
    waiting_for_notes = State()
    confirming = State()


class HealthDiary(StatesGroup):
    """Состояния для дневника здоровья"""
    choosing_metrics = State()
    waiting_for_temperature = State()
    waiting_for_blood_pressure = State()
    waiting_for_pulse = State()
    waiting_for_weight = State()
    waiting_for_symptoms = State()
    waiting_for_mood = State()
    waiting_for_notes = State()
    confirming = State()
