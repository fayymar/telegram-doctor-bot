"""
Роутер для выбора источника медицинских рекомендаций
"""
from services.medical_knowledge import LocalMedicalDB
from services.ai_service import AIService
from utils.logger import setup_logger

logger = setup_logger(__name__)


class MedicalRouter:
    """
    Маршрутизатор запросов между локальной БД и AI

    Логика:
    1. Сначала проверяем локальную БД (быстро, ~100ms)
    2. Если уверенность > 80% - используем локальный результат
    3. Если уверенность < 80% или красные флаги - используем AI
    4. AI может дополнить результат локальной БД контекстом
    """

    # Порог уверенности для использования локальной БД
    CONFIDENCE_THRESHOLD = 0.8

    def __init__(self):
        self.local_db = LocalMedicalDB()
        self.ai_service = AIService()
        logger.info("MedicalRouter initialized")

    def recommend_doctor(
        self,
        main_symptoms: str,
        duration: str,
        additional_symptoms: list[str],
        user_profile: dict
    ) -> dict:
        """
        Рекомендует врачей используя гибридный подход

        Args:
            main_symptoms: Основные симптомы
            duration: Давность симптомов
            additional_symptoms: Дополнительные симптомы
            user_profile: Профиль пользователя

        Returns:
            {
                'specialists': [...],
                'urgency': 'low'|'medium'|'high'|'emergency',
                'urgency_reason': '...',
                'source': 'local_db' | 'ai' | 'hybrid'
            }
        """
        # Объединяем все симптомы для анализа
        all_symptoms = main_symptoms
        if additional_symptoms:
            all_symptoms += " " + " ".join(additional_symptoms)

        logger.info(f"Routing request for symptoms: {all_symptoms[:100]}...")

        # Шаг 1: Пробуем локальную БД
        local_result = self.local_db.search(all_symptoms)

        # Шаг 2: Принимаем решение
        if local_result and local_result['confidence'] >= self.CONFIDENCE_THRESHOLD:
            # Локальная БД уверена и нет красных флагов
            if not local_result.get('red_flags_found'):
                logger.info(
                    f"Using LOCAL_DB result (confidence: {local_result['confidence']:.2f})"
                )
                return self._format_local_result(local_result, duration)

        # Шаг 3: Используем AI (с контекстом из локальной БД если есть)
        logger.info("Using AI for recommendation")

        ai_result = self.ai_service.recommend_doctor(
            main_symptoms=main_symptoms,
            duration=duration,
            additional_symptoms=additional_symptoms,
            user_profile=user_profile
        )

        # Добавляем информацию об источнике
        if local_result and local_result['confidence'] < self.CONFIDENCE_THRESHOLD:
            ai_result['source'] = 'hybrid'
            ai_result['local_confidence'] = local_result['confidence']
            logger.info(f"Hybrid result: local confidence {local_result['confidence']:.2f}, using AI")
        else:
            ai_result['source'] = 'ai'

        return ai_result

    def _format_local_result(self, local_result: dict, duration: str) -> dict:
        """
        Форматирует результат из локальной БД в стандартный формат

        Args:
            local_result: Результат из локальной БД
            duration: Давность симптомов

        Returns:
            Результат в стандартном формате
        """
        # Определяем срочность на основе красных флагов и давности
        urgency = self._determine_urgency(local_result, duration)

        # Формируем причину срочности
        urgency_reason = self._get_urgency_reason(urgency, local_result)

        # Формируем список специалистов с причинами
        specialists = []
        for spec in local_result['specialists']:
            reason = self._generate_reason(spec['name'], local_result)
            specialists.append({
                'name': spec['name'],
                'match_percent': spec['percent'],
                'reason': reason
            })

        return {
            'specialists': specialists,
            'urgency': urgency,
            'urgency_reason': urgency_reason,
            'source': 'local_db',
            'confidence': local_result['confidence']
        }

    def _determine_urgency(self, local_result: dict, duration: str) -> str:
        """
        Определяет срочность обращения

        Args:
            local_result: Результат из локальной БД
            duration: Давность симптомов

        Returns:
            'emergency' | 'high' | 'medium' | 'low'
        """
        # Если есть красные флаги - высокая срочность
        if local_result.get('red_flags_found'):
            return 'high'

        # Проверяем давность
        duration_lower = duration.lower()

        if 'недел' in duration_lower or 'долго' in duration_lower:
            return 'medium'
        elif 'день' in duration_lower or 'дня' in duration_lower:
            return 'high'
        elif 'час' in duration_lower:
            return 'high'

        return 'medium'

    def _get_urgency_reason(self, urgency: str, local_result: dict) -> str:
        """Генерирует причину срочности"""
        reasons = {
            'emergency': 'Требуется немедленная медицинская помощь. Обратитесь в скорую помощь.',
            'high': 'Рекомендуется обратиться к врачу в течение 24 часов.',
            'medium': 'Рекомендуется консультация в течение недели.',
            'low': 'Плановая консультация. Можно записаться на удобное время.'
        }

        base_reason = reasons.get(urgency, reasons['medium'])

        # Добавляем информацию о красных флагах если есть
        if local_result.get('red_flags_found'):
            base_reason += ' Обнаружены признаки, требующие внимания.'

        return base_reason

    def _generate_reason(self, specialist_name: str, local_result: dict) -> str:
        """
        Генерирует причину для специалиста

        Args:
            specialist_name: Название специалиста
            local_result: Результат из локальной БД

        Returns:
            Текстовое объяснение
        """
        causes = local_result.get('common_causes', [])

        if causes:
            causes_text = ', '.join(causes[:2])  # Берем первые 2 причины
            return f"Специалист по данным симптомам. Возможные причины: {causes_text}."

        return "Рекомендуется консультация для диагностики и лечения."

    def get_stats(self) -> dict:
        """Возвращает статистику работы роутера"""
        return {
            'local_db_symptoms': len(self.local_db.get_all_symptoms()),
            'confidence_threshold': self.CONFIDENCE_THRESHOLD
        }
