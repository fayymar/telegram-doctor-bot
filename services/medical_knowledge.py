"""
Локальная база медицинских знаний для быстрого поиска типовых случаев
"""
import json
import os
from typing import Optional
from utils.logger import setup_logger

logger = setup_logger(__name__)


class LocalMedicalDB:
    """Быстрая локальная база для типовых случаев симптомов"""

    def __init__(self):
        self.symptoms_db = self._load_database()
        logger.info(f"LocalMedicalDB initialized with {len(self.symptoms_db)} symptoms")

    def _load_database(self) -> dict:
        """Загружает базу данных из JSON файла"""
        db_path = os.path.join(
            os.path.dirname(__file__),
            'data',
            'symptoms_db.json'
        )

        try:
            with open(db_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logger.info(f"Loaded symptoms database from {db_path}")
                return data
        except FileNotFoundError:
            logger.error(f"Symptoms database not found at {db_path}")
            return {}
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse symptoms database: {e}")
            return {}

    def search(self, symptoms_text: str) -> Optional[dict]:
        """
        Поиск по симптомам в локальной базе

        Args:
            symptoms_text: Текст симптомов от пользователя

        Returns:
            {
                'specialists': [{'name': 'Невролог', 'percent': 70}, ...],
                'confidence': 0.85,  # Уверенность в рекомендации (0-1)
                'red_flags': [...],  # Тревожные признаки
                'common_causes': [...],  # Типичные причины
                'source': 'local_db'
            }
            или None если не найдено
        """
        symptoms_lower = symptoms_text.lower()

        # Извлекаем ключевые слова
        keywords = self._extract_keywords(symptoms_lower)

        if not keywords:
            logger.debug("No keywords found in symptoms")
            return None

        # Ищем совпадения в базе
        best_match = None
        best_confidence = 0

        for keyword in keywords:
            if keyword in self.symptoms_db:
                symptom_data = self.symptoms_db[keyword]
                confidence = symptom_data.get('confidence', 0.5)

                # Проверяем наличие красных флагов
                red_flag_boost = self._check_red_flags(
                    symptoms_lower,
                    symptom_data.get('red_flags', [])
                )

                # Если есть красные флаги - снижаем уверенность (нужен AI)
                if red_flag_boost:
                    confidence *= 0.7
                    logger.info(f"Red flags detected for '{keyword}', reducing confidence to {confidence}")

                # Выбираем лучшее совпадение
                if confidence > best_confidence:
                    best_confidence = confidence
                    best_match = {
                        'specialists': symptom_data['specialists'],
                        'confidence': confidence,
                        'red_flags_found': red_flag_boost,
                        'red_flags': symptom_data.get('red_flags', []),
                        'common_causes': symptom_data.get('common_causes', []),
                        'source': 'local_db',
                        'matched_keyword': keyword
                    }

        if best_match:
            logger.info(
                f"Found match: '{best_match['matched_keyword']}' "
                f"with confidence {best_match['confidence']:.2f}"
            )

        return best_match

    def _extract_keywords(self, text: str) -> list[str]:
        """
        Извлекает ключевые слова из текста симптомов

        Args:
            text: Текст в нижнем регистре

        Returns:
            Список ключевых слов для поиска
        """
        # Словарь синонимов для нормализации
        synonyms = {
            'голова': ['головная_боль', 'голова'],
            'болит': ['боль'],
            'живот': ['боль_в_животе', 'живот'],
            'температура': ['температура', 'жар', 'лихорадка'],
            'кашель': ['кашель', 'кашляю'],
            'горло': ['боль_в_горле', 'горло'],
            'насморк': ['насморк', 'заложен нос'],
            'слабость': ['слабость', 'усталость', 'упадок сил'],
            'головокружение': ['головокружение', 'кружится'],
            'грудь': ['боль_в_груди', 'грудь', 'грудная клетка'],
            'спина': ['боль_в_спине', 'спина', 'поясница'],
            'суставы': ['боль_в_суставах', 'суставы'],
            'тошнота': ['тошнота', 'тошнит'],
            'диарея': ['диарея', 'понос', 'жидкий стул'],
            'мочеиспускание': ['боль_при_мочеиспускании', 'мочеиспускание'],
            'сыпь': ['сыпь_на_коже', 'сыпь', 'высыпания'],
            'сердце': ['боль_в_сердце', 'сердце'],
            'одышка': ['одышка', 'тяжело дышать'],
            'ухо': ['боль_в_ухе', 'ухо'],
            'зуб': ['зубная_боль', 'зуб'],
            'бессонница': ['бессонница', 'не могу уснуть']
        }

        keywords = set()

        # Проверяем каждый синоним
        for key, variants in synonyms.items():
            for variant in variants:
                if variant.replace('_', ' ') in text or variant.replace('_', '') in text:
                    # Добавляем все варианты для этого ключа
                    for v in variants:
                        if v in self.symptoms_db:
                            keywords.add(v)

        return list(keywords)

    def _check_red_flags(self, text: str, red_flags: list[str]) -> bool:
        """
        Проверяет наличие тревожных признаков

        Args:
            text: Текст симптомов
            red_flags: Список красных флагов

        Returns:
            True если найдены красные флаги
        """
        for flag in red_flags:
            if flag.lower() in text:
                logger.warning(f"Red flag detected: '{flag}'")
                return True
        return False

    def get_symptom_info(self, keyword: str) -> Optional[dict]:
        """Получить информацию о конкретном симптоме"""
        return self.symptoms_db.get(keyword)

    def get_all_symptoms(self) -> list[str]:
        """Получить список всех симптомов в базе"""
        return list(self.symptoms_db.keys())
