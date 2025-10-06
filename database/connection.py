from supabase import create_client, Client
from typing import Optional, List, Dict, Any
from datetime import datetime
import json
import config


class DatabaseService:
    def __init__(self):
        self.client: Client = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
    
    # === Работа с профилями пользователей ===
    
    async def get_user_profile(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получить профиль пользователя"""
        response = self.client.table("user_profiles").select("*").eq("user_id", user_id).execute()
        return response.data[0] if response.data else None
    
    async def create_user_profile(self, user_id: int, username: Optional[str] = None) -> Dict[str, Any]:
        """Создать профиль пользователя"""
        data = {
            "user_id": user_id,
            "username": username,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        response = self.client.table("user_profiles").insert(data).execute()
        return response.data[0]
    
    async def update_user_profile(self, user_id: int, **kwargs) -> Dict[str, Any]:
        """Обновить профиль пользователя"""
        kwargs["updated_at"] = datetime.now().isoformat()
        response = self.client.table("user_profiles").update(kwargs).eq("user_id", user_id).execute()
        return response.data[0]
    
    # === Работа с консультациями ===
    
    async def create_consultation(
        self,
        user_id: int,
        symptoms: List[str],
        questions_answers: List[Dict[str, str]],
        recommended_doctor: str,
        urgency_level: str
    ) -> Dict[str, Any]:
        """Создать новую консультацию"""
        data = {
            "user_id": user_id,
            "symptoms": json.dumps(symptoms, ensure_ascii=False),
            "questions_answers": json.dumps(questions_answers, ensure_ascii=False),
            "recommended_doctor": recommended_doctor,
            "urgency_level": urgency_level,
            "created_at": datetime.now().isoformat()
        }
        response = self.client.table("consultations").insert(data).execute()
        return response.data[0]
    
    async def get_user_consultations(self, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Получить последние консультации пользователя"""
        response = (
            self.client.table("consultations")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return response.data
    
    # === Работа с сообщениями ===
    
    async def add_message(
        self,
        user_id: int,
        role: str,
        content: str,
        consultation_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Добавить сообщение в историю"""
        data = {
            "user_id": user_id,
            "role": role,
            "content": content,
            "consultation_id": consultation_id,
            "created_at": datetime.now().isoformat()
        }
        response = self.client.table("messages").insert(data).execute()
        return response.data[0]
    
    async def get_conversation_history(
        self,
        user_id: int,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Получить историю разговора"""
        response = (
            self.client.table("messages")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        # Возвращаем в прямом порядке (от старых к новым)
        return list(reversed(response.data))


# Глобальный экземпляр
db = DatabaseService()
