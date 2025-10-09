import os
import json
import re
from groq import Groq


class AIService:
    """Сервис для работы с Groq AI"""
    
    def __init__(self):
        self.client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        self.model = "llama-3.1-8b-instant"
    
    def _call_ai(self, system_prompt: str, user_message: str, temperature: float = 0.7) -> str:
        """
        Базовый метод для вызова AI
        
        Args:
            system_prompt: Системный промпт
            user_message: Сообщение пользователя
            temperature: Температура генерации (0-1)
        
        Returns:
            Ответ от AI
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                temperature=temperature,
                max_tokens=1024
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"AI Error: {e}")
            return ""
    
    def validate_symptoms(self, text: str) -> dict:
        """
        Проверяет, описывает ли текст медицинские симптомы
        
        Args:
            text: Текст от пользователя
        
        Returns:
            {
                'is_valid': bool,  # True если это симптомы
                'symptoms': str,   # Извлеченные симптомы
                'reason': str      # Причина, если невалидно
            }
        """
        system_prompt = """Ты медицинский ассистент. Твоя задача - проверить, описывает ли пользователь медицинские симптомы или жалобы на здоровье.

СИМПТОМЫ - это:
- Физические ощущения (боль, температура, слабость, тошнота и т.д.)
- Изменения в состоянии здоровья
- Видимые проявления (сыпь, отек, покраснение и т.д.)
- Нарушения функций организма

НЕ СИМПТОМЫ:
- Рецепты
- Инструкции
- Вопросы не о здоровье
- Случайный текст
- Просьбы что-то сделать

Ответь СТРОГО в JSON формате:
{
    "is_valid": true/false,
    "symptoms": "краткое описание симптомов" или "",
    "reason": "почему невалидно" или ""
}"""

        user_message = f"Проверь, описывает ли это симптомы:\n\n{text}"
        
        response = self._call_ai(system_prompt, user_message, temperature=0.3)
        
        try:
            # Извлекаем JSON из ответа
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                return {
                    'is_valid': result.get('is_valid', False),
                    'symptoms': result.get('symptoms', ''),
                    'reason': result.get('reason', '')
                }
        except Exception as e:
            print(f"JSON Parse Error: {e}")
        
        # Если не удалось распарсить, считаем невалидным
        return {
            'is_valid': False,
            'symptoms': '',
            'reason': 'Не удалось распознать симптомы'
        }
    
    def improve_symptoms_text(self, text: str) -> str:
        """
        Окультуривает и улучшает описание симптомов от пользователя
        
        Args:
            text: Исходный текст от пользователя
        
        Returns:
            Улучшенный, структурированный текст симптомов
        """
        system_prompt = """Ты медицинский редактор. Твоя задача - улучшить и структурировать описание симптомов от пациента, сохраняя всю важную информацию.

ПРАВИЛА:
1. Исправь грамматические и орфографические ошибки
2. Структурируй информацию логично
3. Используй правильные медицинские термины
4. Сохрани ВСЮ важную информацию (локализация боли, интенсивность, время и т.д.)
5. Убери лишние слова ("типа", "как бы", "ну вот" и т.д.)
6. Сделай текст понятным для врача
7. НЕ добавляй информацию, которой нет в оригинале
8. НЕ ставь диагнозы

ФОРМАТ ОТВЕТА: просто улучшенный текст, без дополнительных комментариев

Примеры:
Исходно: "у меня как бы голова болит и типа в висках стреляет уже 2 день"
Улучшено: "Головная боль в области висков, стреляющего характера. Беспокоит в течение 2 дней."

Исходно: "жывот болит справо низу когда хожу"
Улучшено: "Боль в правой нижней части живота, усиливается при ходьбе."

Исходно: "температура высокая кашель сухой слабость"
Улучшено: "Повышенная температура тела. Сухой кашель. Общая слабость."""

        user_message = f"Улучши описание симптомов:\n\n{text}"
        
        response = self._call_ai(system_prompt, user_message, temperature=0.3)
        
        # Очищаем ответ от лишнего
        improved = response.strip()
        
        # Убираем возможные вводные фразы AI
        phrases_to_remove = [
            "Улучшенный текст:",
            "Улучшено:",
            "Вот улучшенный вариант:",
            "Исправленный текст:",
        ]
        
        for phrase in phrases_to_remove:
            if improved.startswith(phrase):
                improved = improved[len(phrase):].strip()
        
        return improved if improved else text
    
    def generate_additional_symptoms(self, main_symptoms: str, duration: str) -> list[str]:
        """
        Генерирует список дополнительных симптомов для уточнения
        
        Args:
            main_symptoms: Основные симптомы пользователя
            duration: Давность симптомов
        
        Returns:
            Список из 8-10 релевантных симптомов
        """
        system_prompt = """Ты опытный русскоязычный врач-диагност. На основе основных симптомов пациента, предложи 8-10 дополнительных симптомов для уточнения диагноза.

КРИТИЧЕСКИ ВАЖНО:
1. Симптомы ТОЛЬКО на РУССКОМ языке (никаких английских слов или транслитерации!)
2. Используй ПРАВИЛЬНЫЕ русские медицинские термины
3. Симптомы должны быть КОРОТКИМИ (2-4 слова)
4. Только симптомы, НЕ названия болезней
5. Релевантные основным жалобам
6. Разнообразные (не повторяться)

ПРАВИЛЬНЫЕ примеры:
✅ "Тошнота" (НЕ "Hausea", НЕ "Nausea")
✅ "Потливость" (НЕ "Потаение", НЕ "Sweating") 
✅ "Рвота" (НЕ "Вомитинг", НЕ "Vomiting")
✅ "Головокружение"
✅ "Слабость"
✅ "Повышенная температура"

Формат ответа: JSON массив строк ТОЛЬКО на русском языке
["симптом 1", "симптом 2", ..., "симптом 8"]"""

        user_message = f"""Основные симптомы: {main_symptoms}
Давность: {duration}

Предложи 8-10 дополнительных симптомов для уточнения НА РУССКОМ ЯЗЫКЕ."""

        response = self._call_ai(system_prompt, user_message, temperature=0.7)
        
        try:
            # Ищем JSON массив в ответе
            json_match = re.search(r'\[.*\]', response, re.DOTALL)
            if json_match:
                symptoms = json.loads(json_match.group())
                # Фильтруем и очищаем симптомы
                return self._filter_symptoms(symptoms)
        except Exception as e:
            print(f"JSON Parse Error: {e}")
        
        # Возвращаем пустой список если не удалось
        return []
    
    def _filter_symptoms(self, symptoms: list[str]) -> list[str]:
        """
        Фильтрует список симптомов
        
        Args:
            symptoms: Исходный список
        
        Returns:
            Отфильтрованный список (без дубликатов, болезней, длинных фраз)
        """
        filtered = []
        seen = set()
        
        # Список болезней для исключения
        disease_keywords = [
            'инфаркт', 'инсульт', 'диабет', 'рак', 'грипп', 'ковид',
            'пневмония', 'гастрит', 'язва', 'артрит', 'астма'
        ]
        
        for symptom in symptoms:
            # Очищаем от лишних символов
            clean = symptom.strip().strip('"').strip("'").lower()
            
            # Пропускаем если:
            # 1. Уже есть в списке
            # 2. Слишком длинный (> 50 символов)
            # 3. Содержит название болезни
            if (clean in seen or 
                len(clean) > 50 or 
                any(disease in clean for disease in disease_keywords)):
                continue
            
            seen.add(clean)
            filtered.append(symptom.strip().strip('"').strip("'"))
        
        return filtered[:10]  # Максимум 10 симптомов
    
    def recommend_doctor(self, 
                        main_symptoms: str, 
                        duration: str, 
                        additional_symptoms: list[str],
                        user_profile: dict) -> dict:
        """
        Рекомендует врача и уровень срочности
        
        Args:
            main_symptoms: Основные симптомы
            duration: Давность симптомов
            additional_symptoms: Дополнительные симптомы
            user_profile: Профиль пользователя (пол, возраст, рост, вес)
        
        Returns:
            {
                'specialist': 'Название специалиста',
                'urgency': 'low'|'medium'|'high'|'emergency',
                'reasoning': 'Обоснование'
            }
        """
        # Список доступных специалистов
        specialists = [
            "Кардиолог", "Невролог", "Гастроэнтеролог", "Эндокринолог", 
            "Пульмонолог", "Уролог", "Гинеколог", "Дерматолог", 
            "Офтальмолог", "Отоларинголог (ЛОР)", "Ортопед-травматолог", 
            "Ревматолог", "Аллерголог-иммунолог", "Психиатр", "Онколог", 
            "Хирург", "Проктолог", "Маммолог", "Нефролог", "Терапевт"
        ]
        
        system_prompt = f"""Ты опытный врач-терапевт. На основе симптомов пациента:
1. Определи наиболее подходящего специалиста из списка
2. Оцени уровень срочности обращения
3. Кратко объясни почему

ДОСТУПНЫЕ СПЕЦИАЛИСТЫ:
{', '.join(specialists)}

УРОВНИ СРОЧНОСТИ:
- emergency: Требуется скорая помощь (угроза жизни)
- high: Обратиться в течение 24 часов
- medium: Обратиться в течение недели
- low: Плановый прием

Ответь СТРОГО в JSON формате:
{{
    "specialist": "Название специалиста из списка",
    "urgency": "emergency/high/medium/low",
    "reasoning": "Краткое обоснование (2-3 предложения)"
}}"""

        # Формируем данные пациента
        age = user_profile.get('age', 'не указан')
        gender = "мужчина" if user_profile.get('gender') == 'male' else "женщина"
        
        user_message = f"""ДАННЫЕ ПАЦИЕНТА:
Пол: {gender}
Возраст: {age} лет

ОСНОВНЫЕ СИМПТОМЫ:
{main_symptoms}

ДАВНОСТЬ: {duration}

ДОПОЛНИТЕЛЬНЫЕ СИМПТОМЫ:
{', '.join(additional_symptoms) if additional_symptoms else 'нет'}

Определи специалиста и срочность."""

        response = self._call_ai(system_prompt, user_message, temperature=0.3)
        
        try:
            # Извлекаем JSON
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                
                # Проверяем что специалист из списка
                specialist = result.get('specialist', 'Терапевт')
                if specialist not in specialists:
                    specialist = 'Терапевт'
                
                return {
                    'specialist': specialist,
                    'urgency': result.get('urgency', 'medium'),
                    'reasoning': result.get('reasoning', '')
                }
        except Exception as e:
            print(f"JSON Parse Error: {e}")
        
        # Возвращаем дефолт если не удалось
        return {
            'specialist': 'Терапевт',
            'urgency': 'medium',
            'reasoning': 'Рекомендуется консультация терапевта для первичного осмотра.'
        }
