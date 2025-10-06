from aiogram.fsm.state import State, StatesGroup


class RegistrationStates(StatesGroup):
    """Состояния регистрации пользователя"""
    waiting_for_age = State()
    waiting_for_gender = State()
    waiting_for_height = State()
    waiting_for_weight = State()


class ConsultationStates(StatesGroup):
    """Состояния консультации"""
    waiting_for_symptoms = State()
    waiting_for_answer = State()
    viewing_result = State()
