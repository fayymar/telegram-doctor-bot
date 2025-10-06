from groq import Groq
from typing import Dict, List, Optional
import json
import config

client = Groq(api_key=config.GROQ_API_KEY)


class MedicalAIService:
    def __init__(self):
        self.model = "llama-3.1-8b-instant"  # Быстрая модель для медицинского анализа
        
        # Системный промпт для медицинского анализа
        self.system_prompt = """Ты - медицинский ассистент. Определи к какому узкому специалисту обратиться.

ПРАВИЛА:
1. НЕ рекомендуй терапевта - только узких специалистов
2. Задай МАКСИМУМ 1 уточняющий вопрос, затем рекомендуй врача
3. Если уже задан 1+ вопрос - ОБЯЗАТЕЛЬНО рекомендуй врача (action: recommend_doctor)
4. Вопросы должны быть короткими и конкретными
5. Отвечай ТОЛЬКО в формате JSON

СПЕЦИАЛИСТЫ:
Кардиолог, Невролог, Гастроэнтеролог, Эндокринолог, Пульмонолог, Уролог, Гинеколог, Дерматолог, Офтальмолог, Отоларинголог (ЛОР), Ортопед, Ревматолог, Аллерголог, Психиатр, Онколог

ФОРМАТ ОТВЕТА (только JSON без объяснений):
{
  "action": "ask_question" или "recommend_doctor",
  "question": "короткий вопрос" (только если action = ask_question),
  "doctor": "название специалиста" (только если action = recommend_doctor),
  "urgency": "low/medium/high/emergency" (только если action = recommend_doctor),
  "reasoning": "краткое объяснение одним предложением"
}"""
    
    async def analyze_symptoms(
        self,
        symptoms: List[str],
        qa_history: List[Dict[str, str]],
        user_profile: Optional[Dict] = None
    ) -> Dict:
        """Анализировать симптомы и определить следующий шаг"""
        
        # Логируем входные данные
        print(f"📊 Анализ симптомов:")
        print(f"   Симптомы: {symptoms}")
        print(f"   Вопросов задано: {len(qa_history)}")
        if qa_history:
            print(f"   Последний Q&A: {qa_history[-1]}")
        
        # Формируем контекст
        context = f"""
ПРОФИЛЬ ПАЦИЕНТА:
{self._format_profile(user_profile)}

СИМПТОМЫ:
{', '.join(symptoms)}

ИСТОРИЯ ВОПРОСОВ И ОТВЕТОВ:
{self._format_qa_history(qa_history)}

Проанализируй информацию и реши: нужно задать уточняющий вопрос или уже можно рекомендовать специалиста?

ВАЖНО: 
- Если уже задано 3+ вопросов, рекомендуй врача
- НЕ повторяй вопросы из истории
- Каждый новый вопрос должен быть уникальным
"""
        
        try:
            # Пробуем без response_format (не все модели поддерживают)
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": context}
                ],
                temperature=0.3,
                max_tokens=500
            )
            
            # Получаем ответ
            response_text = response.choices[0].message.content.strip()
            print(f"✅ Groq ответ получен ({len(response_text)} символов)")
            print(f"📝 Полный ответ: {response_text}")
            
            # Убираем markdown если есть
            if response_text.startswith("```json"):
                response_text = response_text[7:-3].strip()
            elif response_text.startswith("```"):
                response_text = response_text[3:-3].strip()
            
            result = json.loads(response_text)
            print(f"✅ JSON распарсен: action={result.get('action')}")
            
            if result.get('action') == 'ask_question':
                print(f"❓ AI задаёт вопрос: {result.get('question', '')[:100]}...")
            elif result.get('action') == 'recommend_doctor':
                print(f"👨‍⚕️ AI рекомендует: {result.get('doctor')} (срочность: {result.get('urgency')})")
            
            # Валидация ответа
            if "action" not in result:
                raise ValueError("Ответ не содержит поле 'action'")
            
            return result
            
        except json.JSONDecodeError as e:
            print(f"❌ Ошибка парсинга JSON: {e}")
            print(f"Ответ от Groq был: {response_text[:500] if 'response_text' in locals() else 'не получен'}")
            return {
                "action": "ask_question",
                "question": "Расскажите подробнее о ваших симптомах. Что именно вас беспокоит?",
                "reasoning": "Ошибка обработки ответа AI"
            }
        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)
            print(f"❌ Ошибка {error_type}: {error_msg}")
            
            # Пытаемся получить детали ошибки
            if hasattr(e, 'response'):
                try:
                    print(f"Response status: {e.response.status_code}")
                    error_detail = e.response.json() if hasattr(e.response, 'json') else str(e.response.content)
                    print(f"Response body: {error_detail}")
                except:
                    pass
            
            return {
                "action": "ask_question",
                "question": "Расскажите подробнее о ваших симптомах. Когда они появились и как проявляются?",
                "reasoning": "Временная техническая проблема с AI"
            }
    
    def _format_profile(self, profile: Optional[Dict]) -> str:
        """Форматировать профиль пользователя"""
        if not profile:
            return "Информация о пациенте не указана"
        
        lines = []
        if profile.get("age"):
            lines.append(f"Возраст: {profile['age']} лет")
        if profile.get("gender"):
            gender_map = {"male": "мужской", "female": "женский", "other": "другой"}
            lines.append(f"Пол: {gender_map.get(profile['gender'], profile['gender'])}")
        if profile.get("height"):
            lines.append(f"Рост: {profile['height']} см")
        if profile.get("weight"):
            lines.append(f"Вес: {profile['weight']} кг")
        
        return "\n".join(lines) if lines else "Информация о пациенте не указана"
    
    def _format_qa_history(self, qa_history: List[Dict[str, str]]) -> str:
        """Форматировать историю вопросов и ответов"""
        if not qa_history:
            return "Нет дополнительных вопросов"
        
        lines = []
        for i, qa in enumerate(qa_history, 1):
            lines.append(f"{i}. Вопрос: {qa['question']}")
            lines.append(f"   Ответ: {qa['answer']}")
        
        return "\n".join(lines)


# Глобальный экземпляр
ai_service = MedicalAIService()
