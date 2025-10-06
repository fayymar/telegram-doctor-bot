from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class UserProfile(BaseModel):
    """Профиль пользователя"""
    user_id: int
    username: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None  # 'male', 'female', 'other'
    height: Optional[int] = None  # в см
    weight: Optional[float] = None  # в кг
    created_at: datetime = datetime.now()
    updated_at: datetime = datetime.now()


class Consultation(BaseModel):
    """История консультаций"""
    id: Optional[int] = None
    user_id: int
    symptoms: str  # JSON строка с симптомами
    questions_answers: str  # JSON строка с вопросами и ответами
    recommended_doctor: str
    urgency_level: str  # 'low', 'medium', 'high', 'emergency'
    created_at: datetime = datetime.now()


class Message(BaseModel):
    """История сообщений для контекста"""
    id: Optional[int] = None
    user_id: int
    consultation_id: Optional[int] = None
    role: str  # 'user', 'assistant'
    content: str
    created_at: datetime = datetime.now()
