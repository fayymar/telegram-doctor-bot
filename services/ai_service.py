import re
from typing import List, Optional

import anthropic

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from utils.logger import setup_logger
from utils.json_parser import safe_parse_json_object, safe_parse_json_array, validate_json_structure

logger = setup_logger(__name__)


class AIService:
    """Сервис для работы с Anthropic Claude"""

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        self.model_name = CLAUDE_MODEL
        logger.info("AIService initialized")
        logger.info(f"Model: {self.model_name}")

    def _call_ai(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.3,
        max_tokens: int = 1024
    ) -> str:
        logger.info(f"Calling model: {self.model_name}")

        response = self.client.messages.create(
            model=self.model_name,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )

        result = response.content[0].text.strip()

        if not result:
            raise RuntimeError(f"Empty response from model: {self.model_name}")

        logger.info(f"Model success: {self.model_name} | response length={len(result)}")
        return result

    def _extract_json_block(self, text: str) -> str:
        """
        Пытается вытащить JSON даже если модель вернула лишний текст
        """
        if not text:
            return text

        text = text.strip()

        fenced = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", text, re.DOTALL)
        if fenced:
            return fenced.group(1).strip()

        obj_match = re.search(r"\{.*\}", text, re.DOTALL)
        if obj_match:
            return obj_match.group(0).strip()

        arr_match = re.search(r"\[.*\]", text, re.DOTALL)
        if arr_match:
            return arr_match.group(0).strip()

        return text

    def _local_symptom_validation(self, text: str) -> dict:
        """
        Локальная проверка симптомов, если AI ответил криво или недоступен
        """
        raw = (text or "").strip()
        clean = raw.lower()

        if len(clean) < 3:
            return {
                "is_valid": False,
                "symptoms": "",
                "reason": "Слишком короткое описание"
            }

        medical_keywords = [
            "бол", "голов", "каш", "темпера", "тошнот", "рвот", "слабост",
            "озноб", "насмор", "горл", "давлен", "сердц", "одыш", "живот",
            "спин", "груд", "ухо", "нос", "глаз", "сып", "зуд", "жж", "понос",
            "запор", "головокруж", "обмор", "судорог", "онемен", "покраснен",
            "отек", "кров", "ран", "травм", "ломит", "беспокоит", "жар",
            "озноб", "хрип", "простуд", "мокрот", "чих", "сустав", "мышц"
        ]

        non_medical_patterns = [
            "привет",
            "как дела",
            "напиши",
            "сделай",
            "переведи",
            "рецепт",
            "погода",
            "анекдот",
            "стих",
            "сказка"
        ]

        if any(pattern in clean for pattern in non_medical_patterns):
            return {
                "is_valid": False,
                "symptoms": "",
                "reason": "Текст не похож на описание симптомов"
            }

        if any(keyword in clean for keyword in medical_keywords):
            return {
                "is_valid": True,
                "symptoms": raw,
                "reason": ""
            }

        if len(clean.split()) >= 2 and ("," in clean or " и " in clean):
            return {
                "is_valid": True,
                "symptoms": raw,
                "reason": ""
            }

        return {
            "is_valid": False,
            "symptoms": "",
            "reason": "Не удалось распознать медицинские симптомы"
        }

    def _local_improve_text(self, text: str) -> str:
        """
        Простой локальный fallback для улучшения текста
        """
        if not text:
            return text

        improved = text.strip()
        improved = re.sub(r"\s+", " ", improved)
        improved = improved.replace(" ,", ",")
        improved = improved.replace(" .", ".")
        improved = improved.strip(" -")

        if improved and improved[0].islower():
            improved = improved[0].upper() + improved[1:]

        return improved

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
            response = self._call_ai(
                system_prompt,
                user_message,
                temperature=0.1,
                max_tokens=500
            )

            cleaned_response = self._extract_json_block(response)

            result = safe_parse_json_object(cleaned_response, default={
                "is_valid": False,
                "symptoms": "",
                "reason": "Не удалось распознать формат ответа"
            })

            if validate_json_structure(result, ["is_valid", "symptoms", "reason"]):
                logger.info(f"Symptom validation via AI: valid={result['is_valid']}")
                return result

            logger.warning("AI returned incomplete validation result, using local fallback")
            return self._local_symptom_validation(text)

        except Exception as e:
            logger.error(f"Error in validate_symptoms: {e}", exc_info=True)
            logger.warning("Using local symptom validation fallback")
            return self._local_symptom_validation(text)

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
            response = self._call_ai(
                system_prompt,
                user_message,
                temperature=0.2,
                max_tokens=400
            )

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
                logger.warning("AI returned empty improvement, using local fallback")
                return self._local_improve_text(text)

            logger.info("Symptoms text improved successfully")
            return improved

        except Exception as e:
            logger.error(f"Error in improve_symptoms_text: {e}. Using local fallback", exc_info=True)
            return self._local_improve_text(text)

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
            response = self._call_ai(
                system_prompt,
                user_message,
                temperature=0.3,
                max_tokens=500
            )

            cleaned_response = self._extract_json_block(response)
            symptoms = safe_parse_json_array(cleaned_response, default=[])

            if not symptoms:
                logger.warning("AI returned empty symptoms list, using fallback list")
                return self._fallback_additional_symptoms(main_symptoms)

            filtered = self._filter_symptoms(symptoms)
            if not filtered:
                return self._fallback_additional_symptoms(main_symptoms)

            logger.info(f"Generated {len(filtered)} additional symptoms")
            return filtered

        except Exception as e:
            logger.error(f"Error in generate_additional_symptoms: {e}", exc_info=True)
            return self._fallback_additional_symptoms(main_symptoms)

    def _fallback_additional_symptoms(self, main_symptoms: str) -> List[str]:
        """
        Простой fallback-список, если AI не сработал
        """
        text = (main_symptoms or "").lower()

        if any(word in text for word in ["каш", "горл", "насмор", "темпера", "простуд"]):
            return [
                "боль в горле",
                "насморк",
                "озноб",
                "слабость",
                "температура",
                "одышка",
                "боль в груди",
                "осиплость"
            ]

        if any(word in text for word in ["голов", "головокруж", "давлен", "слабост"]):
            return [
                "головокружение",
                "тошнота",
                "слабость",
                "шум в ушах",
                "нарушение зрения",
                "онемение",
                "сонливость",
                "температура"
            ]

        if any(word in text for word in ["живот", "тошнот", "рвот", "понос", "стул"]):
            return [
                "рвота",
                "тошнота",
                "диарея",
                "запор",
                "вздутие живота",
                "температура",
                "слабость",
                "боль после еды"
            ]

        return [
            "слабость",
            "температура",
            "тошнота",
            "головокружение",
            "озноб",
            "боль",
            "онемение",
            "одышка"
        ]

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
            response = self._call_ai(
                system_prompt,
                user_message,
                temperature=0.1,
                max_tokens=900
            )

            cleaned_response = self._extract_json_block(response)

            result = safe_parse_json_object(cleaned_response, default={
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
                logger.warning("AI returned incomplete doctor recommendation, using fallback")
                return self._fallback_recommendation(main_symptoms, additional_symptoms)

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
                return self._fallback_recommendation(main_symptoms, additional_symptoms)

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
            return self._fallback_recommendation(main_symptoms, additional_symptoms)

    def _fallback_recommendation(self, main_symptoms: str, additional_symptoms: List[str]) -> dict:
        """
        Простой локальный fallback, если AI не выдал корректный JSON
        """
        text = f"{main_symptoms} {' '.join(additional_symptoms)}".lower()

        if any(word in text for word in ["каш", "горл", "насмор", "ухо", "осипл", "глот"]):
            return {
                "specialists": [
                    {
                        "name": "ЛОР",
                        "match_percent": 75,
                        "reason": "Симптомы могут относиться к заболеваниям уха, горла или носа."
                    },
                    {
                        "name": "Терапевт",
                        "match_percent": 25,
                        "reason": "Подходит для первичного осмотра при общих симптомах простуды."
                    }
                ],
                "urgency": "medium",
                "urgency_reason": "Рекомендуется консультация в ближайшие дни."
            }

        if any(word in text for word in ["голов", "онемен", "головокруж", "судорог", "зрение"]):
            return {
                "specialists": [
                    {
                        "name": "Невролог",
                        "match_percent": 75,
                        "reason": "Симптомы могут относиться к неврологическому профилю."
                    },
                    {
                        "name": "Терапевт",
                        "match_percent": 25,
                        "reason": "Подходит для первичной оценки симптомов."
                    }
                ],
                "urgency": "medium",
                "urgency_reason": "Рекомендуется консультация в ближайшие дни."
            }

        if any(word in text for word in ["живот", "тошнот", "рвот", "понос", "стул", "вздут"]):
            return {
                "specialists": [
                    {
                        "name": "Гастроэнтеролог",
                        "match_percent": 75,
                        "reason": "Жалобы могут быть связаны с желудочно-кишечным трактом."
                    },
                    {
                        "name": "Терапевт",
                        "match_percent": 25,
                        "reason": "Подходит для первичного осмотра."
                    }
                ],
                "urgency": "medium",
                "urgency_reason": "Рекомендуется консультация в ближайшие дни."
            }

        if any(word in text for word in ["сердц", "давлен", "груд", "одыш", "аритм"]):
            return {
                "specialists": [
                    {
                        "name": "Кардиолог",
                        "match_percent": 75,
                        "reason": "Жалобы могут относиться к сердечно-сосудистой системе."
                    },
                    {
                        "name": "Терапевт",
                        "match_percent": 25,
                        "reason": "Подходит для первичной оценки состояния."
                    }
                ],
                "urgency": "high",
                "urgency_reason": "При боли в груди, одышке или сердцебиении лучше обратиться быстрее."
            }

        if any(word in text for word in ["сып", "зуд", "кож", "покраснен", "пятн"]):
            return {
                "specialists": [
                    {
                        "name": "Дерматолог",
                        "match_percent": 75,
                        "reason": "Симптомы могут относиться к кожным заболеваниям."
                    },
                    {
                        "name": "Терапевт",
                        "match_percent": 25,
                        "reason": "Подходит для первичной оценки состояния."
                    }
                ],
                "urgency": "medium",
                "urgency_reason": "Рекомендуется консультация в ближайшие дни."
            }

        return {
            "specialists": [
                {
                    "name": "Терапевт",
                    "match_percent": 80,
                    "reason": "Рекомендуется для первичного осмотра и определения дальнейшей тактики."
                }
            ],
            "urgency": "medium",
            "urgency_reason": "Рекомендуется консультация в ближайшее время."
        }
