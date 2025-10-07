from aiogram.fsm.state import State, StatesGroup


class RegistrationStates(StatesGroup):
    """Состояния регистрации пользователя"""
    waiting_for_age = State()
    waiting_for_gender = State()
    waiting_for_height = State()
    waiting_for_weight = State()


class ConsultationStates(StatesGroup):
    """Состояния консультации - новая структура"""
    # Этап 1: Описание симптомов
    waiting_for_symptoms = State()
    confirming_symptoms = State()
    adding_symptoms = State()
    
    # Этап 2: Давность
    selecting_duration = State()
    
    # Этап 3: Дополнительные симптомы от AI
    selecting_additional_symptoms = State()
    entering_custom_symptoms = State()
    
    # Этап 4: Финальное подтверждение
    final_confirmation = State()
    
    # Результат
    viewing_result = State()
