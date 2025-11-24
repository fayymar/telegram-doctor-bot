import os
from groq import Groq
from utils.logger import setup_logger
from utils.json_parser import safe_parse_json_object, safe_parse_json_array, validate_json_structure
from utils.retry import retry_on_failure

logger = setup_logger(__name__)


class AIService:
    """Сервис для работы с Groq AI"""

    def __init__(self):
        self.client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        self.model = "llama-3.1-8b-instant"
        logger.info("AIService initialized")

    @retry_on_failure(max_attempts=3, delay=1.0, exceptions=(Exception,))
    def _call_ai(self, system_prompt: str, user_message: str, temperature: float = 0.7) -> str:
        """
        Базовый метод для вызова AI с retry логикой

        Args:
            system_prompt: Системный промпт
            user_message: Сообщение пользователя
            temperature: Температура генерации (0-1)

        Returns:
            Ответ от AI

        Raises:
            Exception: При ошибке после всех попыток
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
            result = response.choices[0].message.content.strip()
            logger.debug(f"AI response received (length: {len(result)})")
            return result
        except Exception as e:
            logger.error(f"AI API Error: {type(e).__name__}: {e}")
            raise

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

        try:
            response = self._call_ai(system_prompt, user_message, temperature=0.3)

            # Используем безопасный парсер
            result = safe_parse_json_object(response, default={
                'is_valid': False,
                'symptoms': '',
                'reason': 'Не удалось распознать формат ответа'
            })

            # Проверяем наличие обязательных полей
            if not validate_json_structure(result, ['is_valid', 'symptoms', 'reason']):
                logger.warning("AI returned incomplete validation result")
                return {
                    'is_valid': False,
                    'symptoms': '',
                    'reason': 'Некорректный ответ от AI'
                }

            logger.info(f"Symptom validation: valid={result['is_valid']}")
            return result

        except Exception as e:
            logger.error(f"Error in validate_symptoms: {e}")
            return {
                'is_valid': False,
                'symptoms': '',
                'reason': 'Ошибка при проверке. Попробуйте ещё раз'
            }

    def improve_symptoms_text(self, text: str) -> str:
        """
        Окультуривает и улучшает описание симптомов от пользователя

        Args:
            text: Исходный текст от пользователя

        Returns:
            Улучшенный, структурированный текст симптомов (или исходный при ошибке)
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

        try:
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

            # Если улучшение пустое - возвращаем оригинал
            if not improved:
                logger.warning("AI returned empty improvement, using original text")
                return text

            logger.info("Symptoms text improved successfully")
            return improved

        except Exception as e:
            logger.error(f"Error in improve_symptoms_text: {e}. Using original text")
            return text  # Возвращаем оригинал при ошибке

    def generate_additional_symptoms(self, main_symptoms: str, duration: str) -> list[str]:
        """
        Генерирует список дополнительных симптомов для уточнения

        Args:
            main_symptoms: Основные симптомы пользователя
            duration: Давность симптомов

        Returns:
            Список из 8-10 релевантных симптомов (пустой список при ошибке)
        """
        system_prompt = """Ты опытный русскоязычный врач-диагност. На основе основных симптомов пациента, предложи 8-10 дополнительных симптомов для уточнения диагноза.

КРИТИЧЕСКИ ВАЖНО - ТОЛЬКО РУССКИЙ ЯЗЫК:
1. Используй ТОЛЬКО литературный русский язык
2. НЕ используй украинские слова (шкіра → кожа, голова → голова, біль → боль)
3. НЕ используй английские слова или транслитерацию
4. НЕ используй слова из других языков
5. Проверь каждое слово - оно должно быть русским!

ПРАВИЛЬНЫЕ русские медицинские термины:
✅ "Зуд кожи" (НЕ "Зудящая шкіра"!)
✅ "Покраснение кожи" (НЕ "Червона шкіра"!)
✅ "Головная боль" (НЕ "Головний біль"!)
✅ "Тошнота" (НЕ "Нудота"!)
✅ "Слабость" (НЕ "Слабкість"!)
✅ "Повышенная температура"
✅ "Головокружение"
✅ "Потеря аппетита"

ПРАВИЛА:
1. Симптомы должны быть КОРОТКИМИ (2-4 слова)
2. Только симптомы, НЕ названия болезней
3. Релевантные основным жалобам
4. Разнообразные (не повторяться)
5. ПРОВЕРЬ: каждое слово на русском языке!

Формат ответа: JSON массив строк ТОЛЬКО на русском языке
["симптом 1", "симптом 2", ..., "симптом 8"]"""

        user_message = f"""Основные симптомы: {main_symptoms}
Давность: {duration}

Предложи 8-10 дополнительных симптомов для уточнения НА РУССКОМ ЯЗЫКЕ (не украинском, не английском)."""

        try:
            response = self._call_ai(system_prompt, user_message, temperature=0.7)

            # Используем безопасный парсер для массива
            symptoms = safe_parse_json_array(response, default=[])

            if not symptoms:
                logger.warning("AI returned empty symptoms list")
                return []

            # Фильтруем и очищаем симптомы
            filtered = self._filter_symptoms(symptoms)
            logger.info(f"Generated {len(filtered)} additional symptoms")
            return filtered

        except Exception as e:
            logger.error(f"Error in generate_additional_symptoms: {e}")
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

        try:
            response = self._call_ai(system_prompt, user_message, temperature=0.3)

            # Используем безопасный парсер
            result = safe_parse_json_object(response, default={
                'specialist': 'Терапевт',
                'urgency': 'medium',
                'reasoning': 'Рекомендуется консультация терапевта для первичного осмотра.'
            })

            # Валидируем структуру
            if not validate_json_structure(result, ['specialist', 'urgency', 'reasoning']):
                logger.warning("AI returned incomplete doctor recommendation")
                return {
                    'specialist': 'Терапевт',
                    'urgency': 'medium',
                    'reasoning': 'Рекомендуется консультация терапевта для первичного осмотра.'
                }

            # Проверяем что специалист из списка
            specialist = result.get('specialist', 'Терапевт')
            if specialist not in specialists:
                logger.warning(f"AI recommended unknown specialist: {specialist}")
                specialist = 'Терапевт'

            # Проверяем что urgency корректный
            urgency = result.get('urgency', 'medium')
            if urgency not in ['emergency', 'high', 'medium', 'low']:
                logger.warning(f"AI returned invalid urgency: {urgency}")
                urgency = 'medium'

            logger.info(f"Recommended {specialist} with urgency {urgency}")

            return {
                'specialist': specialist,
                'urgency': urgency,
                'reasoning': result.get('reasoning', '')
            }

        except Exception as e:
            logger.error(f"Error in recommend_doctor: {e}")
            return {
                'specialist': 'Терапевт',
                'urgency': 'medium',
                'reasoning': 'Рекомендуется консультация терапевта для первичного осмотра.'
            }
