from groq import Groq
from typing import Dict, List, Optional
import json
import config

client = Groq(api_key=config.GROQ_API_KEY)


class MedicalAIService:
    def __init__(self):
        self.model = "llama-3.1-8b-instant"
        
        # Список болезней для фильтрации
        self.diseases_to_filter = [
            'грипп', 'орви', 'простуда', 'ангина', 'гастрит', 'язва',
            'диабет', 'гипертония', 'мигрень', 'астма', 'бронхит',
            'пневмония', 'covid', 'ковид', 'коронавирус'
        ]
    
    async def generate_additional_symptoms(
        self,
        initial_symptoms: List[str],
        duration: str,
        user_profile: Optional[Dict] = None
    ) -> List[str]:
        """Генерировать 8-10 дополнительных симптомов на основе начальных
        
        Args:
            initial_symptoms: начальные симптомы пользователя
            duration: давность симптомов
            user_profile: профиль пользователя
            
        Returns:
            Список из 8-10 дополнительных симптомов
        """
        print(f"🔍 Генерация дополнительных симптомов:")
        print(f"   Начальные симптомы: {initial_symptoms}")
        print(f"   Давность: {duration}")
        
        profile_info = self._format_profile(user_profile)
        
        prompt = f"""На основе данных пациента, предложи 8-10 ДОПОЛНИТЕЛЬНЫХ симптомов которые часто встречаются вместе с указанными.

ДАННЫЕ ПАЦИЕНТА:
{profile_info}

УКАЗАННЫЕ СИМПТОМЫ: {', '.join(initial_symptoms)}
ДАВНОСТЬ: {duration}

ВАЖНЫЕ ТРЕБОВАНИЯ:
1. Предложи ТОЛЬКО симптомы (НЕ болезни, НЕ диагнозы)
2. НЕ дублируй указанные симптомы: {', '.join(initial_symptoms)}
3. Симптомы должны быть простыми и понятными (НЕ используй медицинские термины типа "Nausea")
4. Каждый симптом - это короткая фраза (2-4 слова максимум)
5. Верни РОВНО 8-10 симптомов

ПРИМЕРЫ ХОРОШИХ СИМПТОМОВ:
- Повышенная температура
- Общая слабость
- Головокружение  
- Потеря аппетита
- Боль в мышцах

ПРИМЕРЫ ПЛОХИХ (НЕ такие):
- Грипп (это диагноз)
- ОРВИ (это диагноз)
- Nausea (непонятное слово)
- Головная боль пульсирующего характера с локализацией в височной области (слишком сложно)

Ответь ТОЛЬКО JSON массивом симптомов без объяснений:
{{"symptoms": ["симптом1", "симптом2", ...]}}"""

        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4,
                max_tokens=300
            )
            
            response_text = response.choices[0].message.content.strip()
            print(f"✅ AI ответил ({len(response_text)} символов)")
            
            # Убираем markdown
            if response_text.startswith("```json"):
                response_text = response_text[7:-3].strip()
            elif response_text.startswith("```"):
                response_text = response_text[3:-3].strip()
            
            result = json.loads(response_text)
            symptoms = result.get("symptoms", [])
            
            # Фильтрация
            filtered = self._filter_symptoms(symptoms, initial_symptoms)
            print(f"✅ Отфильтровано симптомов: {len(filtered)}")
            print(f"   Симптомы: {filtered[:5]}...")
            
            return filtered[:10]  # Максимум 10
            
        except Exception as e:
            print(f"❌ Ошибка генерации симптомов: {type(e).__name__}: {str(e)}")
            # Fallback: базовые симптомы
            return [
                "Повышенная температура",
                "Общая слабость",
                "Головокружение",
                "Потеря аппетита",
                "Боль в мышцах",
                "Озноб",
                "Усталость",
                "Затрудненное дыхание"
            ]
    
    async def recommend_doctor(
        self,
        initial_symptoms: List[str],
        duration: str,
        additional_symptoms: List[str],
        user_profile: Optional[Dict] = None
    ) -> Dict:
        """Рекомендовать врача на основе всех данных
        
        Returns:
            {
                "doctor": "название специалиста",
                "urgency": "low|medium|high|emergency",
                "reasoning": "объяснение"
            }
        """
        print(f"👨‍⚕️ Формирование рекомендации:")
        print(f"   Начальные симптомы: {initial_symptoms}")
        print(f"   Дополнительные: {additional_symptoms}")
        print(f"   Давность: {duration}")
        
        all_symptoms = initial_symptoms + additional_symptoms
        profile_info = self._format_profile(user_profile)
        
        prompt = f"""Ты медицинский ассистент. На основе симптомов пациента рекомендуй УЗКОГО специалиста.

ДАННЫЕ ПАЦИЕНТА:
{profile_info}

ВСЕ СИМПТОМЫ: {', '.join(all_symptoms)}
ДАВНОСТЬ: {duration}

ДОСТУПНЫЕ СПЕЦИАЛИСТЫ:
Кардиолог, Невролог, Гастроэнтеролог, Эндокринолог, Пульмонолог, Уролог, Гинеколог, Дерматолог, Офтальмолог, Отоларинголог (ЛОР), Ортопед-травматолог, Ревматолог, Аллерголог-иммунолог, Психиатр, Онколог, Хирург, Проктолог, Маммолог, Нефролог

ПРАВИЛА:
1. НЕ рекомендуй терапевта - только узких специалистов
2. Выбери ОДНОГО наиболее подходящего специалиста
3. Определи уровень срочности: low, medium, high, emergency
4. Дай краткое объяснение (1-2 предложения)

Ответь ТОЛЬКО JSON:
{{
  "doctor": "название специалиста",
  "urgency": "low|medium|high|emergency",
  "reasoning": "краткое объяснение"
}}"""

        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=300
            )
            
            response_text = response.choices[0].message.content.strip()
            print(f"✅ Рекомендация получена ({len(response_text)} символов)")
            
            # Убираем markdown
            if response_text.startswith("```json"):
                response_text = response_text[7:-3].strip()
            elif response_text.startswith("```"):
                response_text = response_text[3:-3].strip()
            
            result = json.loads(response_text)
            print(f"👨‍⚕️ Рекомендован: {result.get('doctor')} (срочность: {result.get('urgency')})")
            
            return result
            
        except Exception as e:
            print(f"❌ Ошибка рекомендации: {type(e).__name__}: {str(e)}")
            # Fallback
            return {
                "doctor": "Терапевт",
                "urgency": "medium",
                "reasoning": "Рекомендуем начать с консультации терапевта для первичной оценки состояния."
            }
    
    def _filter_symptoms(self, symptoms: List[str], initial_symptoms: List[str]) -> List[str]:
        """Фильтровать симптомы: убрать дубликаты и болезни"""
        filtered = []
        initial_lower = [s.lower() for s in initial_symptoms]
        
        for symptom in symptoms:
            symptom_clean = symptom.strip()
            symptom_lower = symptom_clean.lower()
            
            # Проверяем на дубликаты
            is_duplicate = any(
                initial in symptom_lower or symptom_lower in initial
                for initial in initial_lower
            )
            
            # Проверяем на болезни
            is_disease = any(
                disease in symptom_lower
                for disease in self.diseases_to_filter
            )
            
            # Проверяем длину (не слишком длинные)
            is_too_long = len(symptom_clean) > 50
            
            if not is_duplicate and not is_disease and not is_too_long:
                filtered.append(symptom_clean)
        
        return filtered
    
    def _format_profile(self, profile: Optional[Dict]) -> str:
        """Форматировать профиль пользователя"""
        if not profile:
            return "Информация о пациенте не указана"
        
        lines = []
        
        # Вычисляем возраст из даты рождения
        if profile.get("birthdate"):
            try:
                from datetime import datetime
                birthdate = datetime.fromisoformat(profile['birthdate']).date()
                today = datetime.now().date()
                age = today.year - birthdate.year - ((today.month, today.day) < (birthdate.month, birthdate.day))
                lines.append(f"Возраст: {age} лет")
            except:
                pass
        
        if profile.get("gender"):
            gender_map = {"male": "мужской", "female": "женский"}
            lines.append(f"Пол: {gender_map.get(profile['gender'], profile['gender'])}")
        if profile.get("height"):
            lines.append(f"Рост: {profile['height']} см")
        if profile.get("weight"):
            lines.append(f"Вес: {profile['weight']} кг")
        
        return "\n".join(lines) if lines else "Информация о пациенте не указана"


# Глобальный экземпляр
ai_service = MedicalAIService()
