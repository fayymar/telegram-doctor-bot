import os
from typing import List, Optional

from huggingface_hub import InferenceClient

from config import HF_TOKEN, PRIMARY_AI_MODEL, FALLBACK_AI_MODELS
from utils.logger import setup_logger
from utils.json_parser import safe_parse_json_object, safe_parse_json_array, validate_json_structure
from utils.retry import retry_on_failure

logger = setup_logger(__name__)


class AIService:
    """Сервис для работы с медицинскими LLM через Hugging Face"""

    def __init__(self):
        self.api_key = HF_TOKEN
        self.primary_model = PRIMARY_AI_MODEL
        self.fallback_models = FALLBACK_AI_MODELS
        self.models = [self.primary_model] + self.fallback_models

        self.client = InferenceClient(
            api_key=self.api_key
        )

        logger.info("AIService initialized")
        logger.info(f"Primary model: {self.primary_model}")
        logger.info(f"Fallback models: {self.fallback_models if self.fallback_models else 'none'}")

    def _build_prompt(self, system_prompt: str, user_message: str) -> str:
        """
        Универсальный prompt для text-generation моделей.
        Он более устойчив для разных open-weight моделей, чем chat-only формат.
        """
        return (
            "### SYSTEM INSTRUCTION ###\n"
            f"{system_prompt.strip()}\n\n"
            "### USER MESSAGE ###\n"
            f"{user_message.strip()}\n\n"
            "### ASSISTANT RESPONSE ###\n"
        )

    @retry_on_failure(max_attempts=2, delay=1.0, exceptions=(Exception,))
    def _call_model_once(
        self,
        model_name: str,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.3,
        max_tokens: int = 1024
    ) -> str:
        """
        Один вызов конкретной модели
        """
        prompt = self._build_prompt(system_prompt, user_message)

        logger.info(f"Trying model: {model_name}")

        response = self.client.text_generation(
            prompt,
            model=model_name,
            max_new_tokens=max_tokens,
            temperature=temperature,
            do_sample=temperature > 0,
            return_full_text=False
        )

        if not response:
            raise RuntimeError(f"Empty response from model: {model_name}")

        result = str(response).strip()

        if not result:
            raise RuntimeError(f"Blank response from model: {model_name}")

        logger.info(f"Model success: {model_name} | response length={len(result)}")
        return result

    def _call_ai(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.3,
        max_tokens: int = 1024
    ) -> str:
        """
        Вызывает primary модель, при ошибке идет по fallback цепочке
        """
        last_error: Optional[Exception] = None

        for model_name in self.models:
            try:
                return self._call_model_once(
                    model_name=model_name,
                    system_prompt=system_prompt,
                    user_message=user_message,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
            except Exception as e:
                last_error = e
                logger.error(f"Model failed: {model_name} | {type(e).__name__}: {e}", exc_info=True)

        raise RuntimeError(f"All AI models failed. Last error: {last_error}")

    def validate_symptoms(self, text: str) -> dict:
        """
        Проверяет, описывает ли текст медицинские симптомы
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
    "is_valid": true,
    "symptoms": "краткое описание симптомов",
    "reason": ""
}

или

{
    "is_valid": false,
    "symptoms": "",
    "reason": "почему невалидно"
}

Никакого текста вне JSON."""

        user_message = f"Проверь, описывает ли это симптомы:\n\n{text}"

        try:
            response = self._call_ai(system_prompt, user_message, temperature=0.1, max_tokens=500)

            result = safe_parse_json_object(response, default={
                "is_valid": False,
                "symptoms": "",
                "reason": "Не удалось распознать формат ответа"
            })

            if not validate_json_structure(result, ["is_valid", "symptoms", "reason"]):
                logger.warning("AI returned incomplete validation result")
                return {
                    "is_valid": False,
                    "symptoms": "",
                    "reason": "Некорректный ответ от AI"
                }

            logger.info(f"Symptom validation: valid={result['is_valid']}")
            return result

        except Exception as e:
            logger.error(f"Error in validate_symptoms: {e}", exc_info=True)
            return {
                "is_valid": False,
                "symptoms": "",
                "reason": "Ошибка при проверке. Попробуйте ещё раз"
            }

    def improve_symptoms_text(self, text: str) -> str:
        """
        Улучшает и структурирует описание симптомов
        """
        system_prompt = """Ты медицинский редактор. Твоя задача - улучшить и структурировать описание симптомов от пациента, сохраняя всю важную информацию.

ПРАВИЛА:
1. Исправь грамматические и орфографические ошибки
2. Структурируй информацию логично
3. Используй правильные медицинские формулировки
4. Сохрани ВСЮ важную информацию
5. Убери лишние слова
6. Сделай текст понятным для врача
7. НЕ добавляй информацию, которой нет в оригинале
8. НЕ ставь диагнозы

ФОРМАТ ОТВЕТА:
Только улучшенный текст, без комментариев, без пояснений, без вступления."""

        user_message = f"Улучши описание симптомов:\n\n{text}"

        try:
            response = self._call_ai(system_prompt, user_message, temperature=0.2, max_tokens=400)

            improved = response.strip()

            phrases_to_remove = [
                "Улучшенный текст:",
                "Улучшено:",
                "Вот улучшенный вариант:",
                "Исправленный текст:",
            ]

            for phrase in phrases_to_remove:
                if improved.startswith(phrase):
                    improved = improved[len(phrase):].strip()

            if not improved:
                logger.warning("AI returned empty improvement, using original text")
                return text

            logger.info("Symptoms text improved successfully")
            return improved

        except Exception as e:
            logger.error(f"Error in improve_symptoms_text: {e}. Using original text", exc_info=True)
            return text

    def generate_additional_symptoms(self, main_symptoms: str, duration: str) -> List[str]:
        """
        Генерирует список дополнительных симптомов для уточнения
        """
        system_prompt = """Ты опытный русскоязычный врач-диагност. На основе основных симптомов пациента предложи 8-10 дополнительных симптомов для уточнения.

ПРАВИЛА:
1. Симптомы должны быть КОРОТКИМИ (2-4 слова)
2. Только симптомы, НЕ названия болезней
3. Симптомы должны быть релевантны жалобам
4. Не дублируй варианты
5. Используй ТОЛЬКО русский язык
6. Ответь СТРОГО JSON-массивом строк

Пример:
["головокружение", "тошнота", "озноб", "боль при глотании"]

Никакого текста вне JSON."""

        user_message = (
            f"Основные симптомы: {main_symptoms}\n"
            f"Давность: {duration if duration else 'не указана'}\n\n"
            f"Предложи 8-10 дополнительных симптомов."
        )

        try:
            response = self._call_ai(system_prompt, user_message, temperature=0.3, max_tokens=500)

            symptoms = safe_parse_json_array(response, default=[])

            if not symptoms:
                logger.warning("AI returned empty symptoms list")
                return []

            filtered = self._filter_symptoms(symptoms)
            logger.info(f"Generated {len(filtered)} additional symptoms")
            return filtered

        except Exception as e:
            logger.error(f"Error in generate_additional_symptoms: {e}", exc_info=True)
            return []

    def _filter_symptoms(self, symptoms: List[str]) -> List[str]:
        """
        Фильтрует список симптомов
        """
        filtered = []
        seen = set()

        disease_keywords = [
            "инфаркт", "инсульт", "диабет", "рак", "грипп", "ковид",
            "пневмония", "гастрит", "язва", "артрит", "астма"
        ]

        for symptom in symptoms:
            if not isinstance(symptom, str):
                continue

            clean = symptom.strip().strip('"').strip("'").lower()

            if (
                not clean or
                clean in seen or
                len(clean) > 50 or
                any(disease in clean for disease in disease_keywords)
            ):
                continue

            seen.add(clean)
            filtered.append(symptom.strip().strip('"').strip("'"))

        return filtered[:10]

    def recommend_doctor(
        self,
        main_symptoms: str,
        duration: str,
        additional_symptoms: List[str],
        user_profile: dict
    ) -> dict:
        """
        Рекомендует врачей с рейтингом соответствия
        """
        system_prompt = """Ты опытный врач первичного звена. Твоя задача - по симптомам пациента предложить наиболее подходящих специалистов.

ПРАВИЛА:
1. Определи наиболее подходящих специалистов
2. Для каждого укажи процент соответствия (0-100)
3. Кратко объясни, почему специалист подходит
4. Оцени срочность обращения

УРОВНИ СРОЧНОСТИ:
- emergency: немедленная помощь
- high: в течение 24 часов
- medium: в течение недели
- low: планово

ВАЖНО:
- Не ставь окончательный диагноз
- Если симптомы смешанные, можешь ставить терапевта первым
- Если есть травма, кровотечение, острый живот, выраженная боль в груди, потеря сознания — учитывай высокую или emergency срочность
- Выдавай до 5 специалистов
- Список сортируй по вероятности
- Используй русский язык

Ответь СТРОГО в JSON:
{
    "specialists": [
        {
            "name": "Название специалиста",
            "match_percent": 90,
            "reason": "Почему подходит"
        }
    ],
    "urgency": "high",
    "urgency_reason": "Почему такая срочность"
}

Никакого текста вне JSON."""

        age = user_profile.get("age", "не указан")
        gender = "мужчина" if user_profile.get("gender") == "male" else "женщина"

        user_message = f"""ДАННЫЕ ПАЦИЕНТА:
Пол: {gender}
Возраст: {age} лет

ОСНОВНЫЕ СИМПТОМЫ:
{main_symptoms}

ДАВНОСТЬ:
{duration}

ДОПОЛНИТЕЛЬНЫЕ СИМПТОМЫ:
{', '.join(additional_symptoms) if additional_symptoms else 'нет'}

Определи наиболее подходящих специалистов и срочность."""

        try:
            response = self._call_ai(system_prompt, user_message, temperature=0.1, max_tokens=900)

            result = safe_parse_json_object(response, default={
                "specialists": [
                    {
                        "name": "Терапевт",
                        "match_percent": 80,
                        "reason": "Рекомендуется для первичного осмотра и определения дальнейшей тактики."
                    }
                ],
                "urgency": "medium",
                "urgency_reason": "Рекомендуется консультация в ближайшее время."
            })

            if not validate_json_structure(result, ["specialists", "urgency"]):
                logger.warning("AI returned incomplete doctor recommendation")
                return {
                    "specialists": [
                        {
                            "name": "Терапевт",
                            "match_percent": 80,
                            "reason": "Рекомендуется для первичного осмотра."
                        }
                    ],
                    "urgency": "medium",
                    "urgency_reason": "Рекомендуется консультация в ближайшее время."
                }

            valid_specialists = []
            for spec in result.get("specialists", [])[:5]:
                if not isinstance(spec, dict):
                    continue

                name = str(spec.get("name", "")).strip()
                if not name:
                    continue

                match_percent = spec.get("match_percent", 50)
                if not isinstance(match_percent, (int, float)) or match_percent < 0 or match_percent > 100:
                    match_percent = 50

                valid_specialists.append({
                    "name": name,
                    "match_percent": int(match_percent),
                    "reason": str(spec.get("reason", "Рекомендуется консультация.")).strip()
                })

            if not valid_specialists:
                valid_specialists = [{
                    "name": "Терапевт",
                    "match_percent": 80,
                    "reason": "Рекомендуется для первичного осмотра."
                }]

            valid_specialists.sort(key=lambda x: x["match_percent"], reverse=True)

            urgency = result.get("urgency", "medium")
            if urgency not in ["emergency", "high", "medium", "low"]:
                urgency = "medium"

            logger.info(
                f"Recommended {len(valid_specialists)} specialists, top: "
                f"{valid_specialists[0]['name']} ({valid_specialists[0]['match_percent']}%)"
            )

            return {
                "specialists": valid_specialists,
                "urgency": urgency,
                "urgency_reason": result.get("urgency_reason", "Рекомендуется консультация.")
            }

        except Exception as e:
            logger.error(f"Error in recommend_doctor: {e}", exc_info=True)
            return {
                "specialists": [
                    {
                        "name": "Терапевт",
                        "match_percent": 80,
                        "reason": "Рекомендуется для первичного осмотра."
                    }
                ],
                "urgency": "medium",
                "urgency_reason": "Рекомендуется консультация в ближайшее время."
            }
