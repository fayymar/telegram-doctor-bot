import google.generativeai as genai
from typing import Dict, List, Optional
import json
import config

genai.configure(api_key=config.GEMINI_API_KEY)


class MedicalAIService:
    def __init__(self):
        self.model = genai.GenerativeModel('gemini-1.5-flash-latest')
        
        # Системный промпт для медицинского анализа
        self.system_prompt = """Ты - опытный медицинский ассистент, который помогает определить, к какому УЗКОМУ специалисту нужно обратиться пациенту на основе симптомов.

ВАЖНЫЕ ПРАВИЛА:
1. НЕ рекомендуй терапевта - только узких специалистов
2. Задавай уточняющие вопросы для точной диагностики
3. Учитывай возраст, пол, рост и вес пациента
4. Определяй уровень срочности: low, medium, high, emergency
5. Если симптомы указывают на несколько специалистов, выбери наиболее подходящего
6. Отвечай ТОЛЬКО в формате JSON

СПЕЦИАЛИСТЫ (выбирай из этого списка):
- Кардиолог (сердце, сосуды, давление)
- Невролог (головные боли, головокружения, нервная система)
- Гастроэнтеролог (ЖКТ, пищеварение)
- Эндокринолог (гормоны, щитовидка, диабет)
- Пульмонолог (легкие, дыхание)
- Уролог (мочевыделительная система)
- Гинеколог (женское здоровье)
- Дерматолог (кожа, волосы, ногти)
- Офтальмолог (глаза, зрение)
- Отоларинголог (ЛОР - ухо, горло, нос)
- Ортопед (кости, суставы, травмы)
- Ревматолог (суставы, аутоиммунные)
- Аллерголог (аллергии)
- Психиатр (психическое здоровье)
- Онколог (подозрение на опухоли)

ФОРМАТ ОТВЕТА:
{
  "action": "ask_question" | "recommend_doctor",
  "question": "текст вопроса" (если action = ask_question),
  "doctor": "название специалиста" (если action = recommend_doctor),
  "urgency": "low|medium|high|emergency" (если action = recommend_doctor),
  "reasoning": "краткое объяснение"
}"""
    
    async def analyze_symptoms(
        self,
        symptoms: List[str],
        qa_history: List[Dict[str, str]],
        user_profile: Optional[Dict] = None
    ) -> Dict:
        """Анализировать симптомы и определить следующий шаг"""
        
        # Формируем контекст
        context = f"""
ПРОФИЛЬ ПАЦИЕНТА:
{self._format_profile(user_profile)}

СИМПТОМЫ:
{', '.join(symptoms)}

ИСТОРИЯ ВОПРОСОВ И ОТВЕТОВ:
{self._format_qa_history(qa_history)}

Проанализируй информацию и реши: нужно задать уточняющий вопрос или уже можно рекомендовать специалиста?
"""
        
        try:
            response = self.model.generate_content(
                f"{self.system_prompt}\n\n{context}",
                generation_config=genai.types.GenerationConfig(
                    temperature=0.3,
                    max_output_tokens=500,
                )
            )
            
            # Парсим JSON из ответа
            response_text = response.text.strip()
            print(f"Gemini ответ: {response_text[:200]}")  # Логируем первые 200 символов
            
            # Убираем markdown форматирование если есть
            if response_text.startswith("```json"):
                response_text = response_text[7:-3].strip()
            elif response_text.startswith("```"):
                response_text = response_text[3:-3].strip()
            
            result = json.loads(response_text)
            return result
            
        except json.JSONDecodeError as e:
            print(f"Ошибка парсинга JSON: {e}")
            print(f"Ответ от Gemini был: {response_text[:500] if 'response_text' in locals() else 'не получен'}")
            # Fallback: задаём базовый вопрос
            return {
                "action": "ask_question",
                "question": "Расскажите подробнее о ваших симптомах. Что именно вас беспокоит?",
                "reasoning": "Ошибка обработки ответа AI"
            }
        except Exception as e:
            print(f"Ошибка при анализе симптомов: {type(e).__name__}: {str(e)}")
            # Fallback: задаём базовый вопрос
            return {
                "action": "ask_question",
                "question": "Расскажите подробнее о ваших симптомах. Что именно вас беспокоит?",
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
