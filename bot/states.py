from aiogram.fsm.state import State, StatesGroup


class Registration(StatesGroup):
    """Состояния для регистрации пользователя"""
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
    
    # Этап 2: Давность симптомов
    waiting_for_duration = State()
    
    # Этап 3: Дополнительные симптомы
    selecting_additional_symptoms = State()
    waiting_for_other_symptoms = State()
    
    # Этап 4: Финальное подтверждение
    final_confirmation = State()


class FindSpecialist(StatesGroup):
    """Состояния для поиска специалиста"""
    choosing_category = State()
    viewing_specialists = State()
