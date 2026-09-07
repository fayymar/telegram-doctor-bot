from datetime import datetime

from pydantic import BaseModel


class UserProfile(BaseModel):
    """Модель профиля пользователя"""
    user_id: int
    username: str | None = None
    full_name: str | None = None
    phone: str | None = None
    birthdate: str | None = None  # Хранится как строка в формате ISO (YYYY-MM-DD)
    gender: str | None = None  # 'male' или 'female'
    height: int | None = None  # в см
    weight: float | None = None  # в кг
    created_at: datetime | None = None
    updated_at: datetime | None = None
    
    class Config:
        from_attributes = True


class Consultation(BaseModel):
    """Модель консультации"""
    id: int | None = None
    user_id: int
    symptoms: str  # JSON строка с симптомами
    questions_answers: str  # JSON строка с вопросами и ответами
    recommended_doctor: str
    urgency_level: str  # 'low', 'medium', 'high', 'emergency'
    created_at: datetime | None = None
    
    class Config:
        from_attributes = True


class Message(BaseModel):
    """Модель сообщения в консультации"""
    id: int | None = None
    user_id: int
    consultation_id: int | None = None
    role: str  # 'user' или 'assistant'
    content: str
    created_at: datetime | None = None
    
    class Config:
        from_attributes = True
