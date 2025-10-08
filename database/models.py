from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class UserProfile(BaseModel):
    """Модель профиля пользователя"""
    user_id: int
    username: Optional[str] = None
    full_name: Optional[str] = None
    phone: Optional[str] = None
    birthdate: Optional[str] = None  # Хранится как строка в формате ISO (YYYY-MM-DD)
    gender: Optional[str] = None  # 'male' или 'female'
    height: Optional[int] = None  # в см
    weight: Optional[float] = None  # в кг
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class Consultation(BaseModel):
    """Модель консультации"""
    id: Optional[int] = None
    user_id: int
    symptoms: str  # JSON строка с симптомами
    questions_answers: str  # JSON строка с вопросами и ответами
    recommended_doctor: str
    urgency_level: str  # 'low', 'medium', 'high', 'emergency'
    created_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class Message(BaseModel):
    """Модель сообщения в консультации"""
    id: Optional[int] = None
    user_id: int
    consultation_id: Optional[int] = None
    role: str  # 'user' или 'assistant'
    content: str
    created_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True
