from typing import Dict, List, Any

from services.symptom_parser import parse_symptoms
from utils.logger import setup_logger

logger = setup_logger(__name__)


CLUSTER_TO_SPECIALISTS = {
    "general": [
        {
            "name": "Терапевт",
            "base_score": 80,
            "reason": "Подходит для первичного осмотра и общей оценки состояния."
        }
    ],
    "respiratory": [
        {
            "name": "Терапевт",
            "base_score": 75,
            "reason": "При кашле, температуре, мокроте и общих респираторных жалобах подходит для первичной оценки."
        },
        {
            "name": "Пульмонолог",
            "base_score": 65,
            "reason": "Подходит при выраженных симптомах со стороны дыхательной системы."
        },
        {
            "name": "ЛОР",
            "base_score": 40,
            "reason": "Часть респираторных жалоб может пересекаться с ЛОР-профилем."
        },
    ],
    "ent": [
        {
            "name": "ЛОР",
            "base_score": 80,
            "reason": "Жалобы больше относятся к заболеваниям уха, горла и носа."
        },
        {
            "name": "Терапевт",
            "base_score": 50,
            "reason": "Подходит для первичного осмотра при простудных и смешанных симптомах."
        },
    ],
    "cardio": [
        {
            "name": "Кардиолог",
            "base_score": 85,
            "reason": "Жалобы могут относиться к сердечно-сосудистой системе."
        },
        {
            "name": "Терапевт",
            "base_score": 45,
            "reason": "Подходит для первичной оценки состояния, если картина смешанная."
        },
        {
            "name": "Пульмонолог",
            "base_score": 25,
            "reason": "Некоторые симптомы, например одышка, могут пересекаться с дыхательной системой."
        },
    ],
    "neuro": [
        {
            "name": "Невролог",
            "base_score": 85,
            "reason": "Симптомы могут относиться к неврологическому профилю."
        },
        {
            "name": "Терапевт",
            "base_score": 45,
            "reason": "Подходит для первичного осмотра при смешанных или неясных жалобах."
        },
    ],
    "gastro": [
        {
            "name": "Гастроэнтеролог",
            "base_score": 80,
            "reason": "Жалобы больше связаны с желудочно-кишечным трактом."
        },
        {
            "name": "Терапевт",
            "base_score": 45,
            "reason": "Подходит для первичной оценки симптомов и определения дальнейшей тактики."
        },
        {
            "name": "Хирург",
            "base_score": 25,
            "reason": "При части симптомов со стороны живота может потребоваться хирургическая оценка."
        },
    ],
    "derm": [
        {
            "name": "Дерматолог",
            "base_score": 85,
            "reason": "Симптомы больше относятся к кожному профилю."
        },
        {
            "name": "Терапевт",
            "base_score": 35,
            "reason": "Подходит для первичной оценки состояния при смешанных жалобах."
        },
        {
            "name": "Аллерголог",
            "base_score": 30,
            "reason": "Часть кожных симптомов может быть связана с аллергической реакцией."
        },
    ],
    "urinary": [
        {
            "name": "Уролог",
            "base_score": 85,
            "reason": "Жалобы больше относятся к мочевыделительной системе."
        },
        {
            "name": "Терапевт",
            "base_score": 40,
            "reason": "Подходит для первичного осмотра и базовой диагностики."
        },
    ],
    "gyn": [
        {
            "name": "Гинеколог",
            "base_score": 85,
            "reason": "Жалобы больше соответствуют гинекологическому профилю."
        },
        {
            "name": "Терапевт",
            "base_score": 30,
            "reason": "Подходит как стартовая точка, если картина смешанная."
        },
    ],
    "trauma": [
        {
            "name": "Травматолог",
            "base_score": 90,
            "reason": "Жалобы относятся к травме, повреждению тканей или костно-суставной системе."
        },
        {
            "name": "Хирург",
            "base_score": 70,
            "reason": "Подходит при ранах, кровотечении и повреждении мягких тканей."
        },
        {
            "name": "Терапевт",
            "base_score": 15,
            "reason": "Может быть полезен только как промежуточный маршрут при очень неясной картине."
        },
    ],
}


RED_FLAG_URGENCY_RULES = {
    "ампутация": ("emergency", "Имеются признаки тяжелой травмы, требуется немедленная медицинская помощь."),
    "кровотечение": ("high", "Имеются признаки кровотечения, рекомендуется срочная медицинская оценка."),
    "открытая рана": ("high", "Открытая рана требует быстрой оценки врача."),
    "перелом": ("high", "Есть признаки значимой травмы, рекомендуется обратиться срочно."),
    "потеря сознания": ("emergency", "Потеря сознания требует немедленной медицинской помощи."),
    "судороги": ("emergency", "Судороги требуют срочной медицинской оценки."),
    "боль в груди": ("high", "Боль в груди требует ускоренной оценки состояния."),
    "давление в груди": ("high", "Давление в груди требует ускоренной оценки состояния."),
    "одышка": ("high", "Одышка может быть признаком серьезного состояния."),
}


SEVERE_KEYWORDS = [
    "очень сильная боль",
    "сильная боль",
    "сильная слабость",
    "одышка в покое",
    "кашель с кровью",
    "кровь в стуле",
    "кровь в моче",
    "обильное кровотечение",
    "трудно дышать",
    "потеря сознания",
    "судороги",
]


class MedicalRouter:
    def __init__(self):
        logger.info("MedicalRouter initialized")

    def recommend_doctor(
        self,
        main_symptoms: str,
        duration: str,
        additional_symptoms: List[str],
        user_profile: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Главная функция рекомендации врача
        """
        try:
            full_symptom_text = self._merge_symptoms(main_symptoms, additional_symptoms)
            parsed = parse_symptoms(full_symptom_text)

            specialists = self._build_specialist_scores(
                parsed=parsed,
                duration=duration,
                user_profile=user_profile,
                additional_symptoms=additional_symptoms
            )

            urgency, urgency_reason = self._determine_urgency(
                parsed=parsed,
                duration=duration,
                additional_symptoms=additional_symptoms
            )

            if not specialists:
                specialists = [
                    {
                        "name": "Терапевт",
                        "match_percent": 80,
                        "reason": "Рекомендуется для первичного осмотра и определения дальнейшей тактики."
                    }
                ]

            logger.info(
                "Medical routing complete | primary_cluster=%s | top_specialist=%s | urgency=%s",
                parsed.get("primary_cluster"),
                specialists[0]["name"] if specialists else "N/A",
                urgency
            )

            return {
                "specialists": specialists,
                "urgency": urgency,
                "urgency_reason": urgency_reason
            }

        except Exception as e:
            logger.error(f"Error in recommend_doctor: {e}", exc_info=True)
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

    def _merge_symptoms(self, main_symptoms: str, additional_symptoms: List[str]) -> str:
        """
        Склеивает основные и выбранные уточняющие симптомы в один текст для повторного парсинга
        """
        parts = []

        if main_symptoms:
            parts.append(main_symptoms.strip())

        if additional_symptoms:
            parts.extend([sym.strip() for sym in additional_symptoms if sym and sym.strip()])

        return ". ".join(parts).strip()

    def _build_specialist_scores(
        self,
        parsed: Dict[str, Any],
        duration: str,
        user_profile: Dict[str, Any],
        additional_symptoms: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Строит список врачей на основе primary/secondary clusters и поправок
        """
        cluster_scores = parsed.get("cluster_scores", {})
        primary_cluster = parsed.get("primary_cluster", "general")
        secondary_clusters = parsed.get("secondary_clusters", [])
        confidence = parsed.get("confidence", "low")
        red_flags = parsed.get("red_flags", [])
        normalized_symptoms = parsed.get("normalized_symptoms", [])

        doctor_scores: Dict[str, Dict[str, Any]] = {}

        # 1. Базовые специалисты от primary cluster
        self._apply_cluster_to_doctors(
            doctor_scores=doctor_scores,
            cluster=primary_cluster,
            cluster_weight=1.0,
            parsed_cluster_score=cluster_scores.get(primary_cluster, 0)
        )

        # 2. Дополнительные специалисты от secondary clusters
        for cluster in secondary_clusters[:2]:
            self._apply_cluster_to_doctors(
                doctor_scores=doctor_scores,
                cluster=cluster,
                cluster_weight=0.55,
                parsed_cluster_score=cluster_scores.get(cluster, 0)
            )

        # 3. Поправки по confidence
        if confidence == "high":
            self._boost_primary_doctors(doctor_scores, primary_cluster, +8)
        elif confidence == "low":
            self._boost_generalists(doctor_scores, +6)

        # 4. Поправки по red flags
        self._apply_red_flag_doctor_adjustments(
            doctor_scores=doctor_scores,
            red_flags=red_flags,
            primary_cluster=primary_cluster
        )

        # 5. Поправки по длительности
        self._apply_duration_adjustments(
            doctor_scores=doctor_scores,
            duration=duration,
            primary_cluster=primary_cluster,
            normalized_symptoms=normalized_symptoms
        )

        # 6. Поправки по возрасту/полу
        self._apply_profile_adjustments(
            doctor_scores=doctor_scores,
            user_profile=user_profile,
            parsed=parsed
        )

        # 7. Превращаем в список
        ranked = self._normalize_doctor_scores(doctor_scores)

        return ranked[:5]

    def _apply_cluster_to_doctors(
        self,
        doctor_scores: Dict[str, Dict[str, Any]],
        cluster: str,
        cluster_weight: float,
        parsed_cluster_score: int
    ):
        """
        Добавляет врачей по кластеру
        """
        doctor_templates = CLUSTER_TO_SPECIALISTS.get(cluster, CLUSTER_TO_SPECIALISTS["general"])

        for item in doctor_templates:
            name = item["name"]
            base_score = item["base_score"]
            reason = item["reason"]

            # базовый скор от врача + влияние cluster score
            score = (base_score * cluster_weight) + (parsed_cluster_score * 4 * cluster_weight)

            if name not in doctor_scores:
                doctor_scores[name] = {
                    "score": 0.0,
                    "reasons": [],
                    "cluster_sources": set()
                }

            doctor_scores[name]["score"] += score
            doctor_scores[name]["reasons"].append(reason)
            doctor_scores[name]["cluster_sources"].add(cluster)

    def _boost_primary_doctors(self, doctor_scores: Dict[str, Dict[str, Any]], primary_cluster: str, bonus: int):
        """
        Усиливает врачей, пришедших из primary cluster
        """
        doctor_templates = CLUSTER_TO_SPECIALISTS.get(primary_cluster, [])
        primary_names = {item["name"] for item in doctor_templates}

        for name in primary_names:
            if name in doctor_scores:
                doctor_scores[name]["score"] += bonus

    def _boost_generalists(self, doctor_scores: Dict[str, Dict[str, Any]], bonus: int):
        """
        При низкой уверенности немного усиливаем терапевта
        """
        if "Терапевт" in doctor_scores:
            doctor_scores["Терапевт"]["score"] += bonus

    def _apply_red_flag_doctor_adjustments(
        self,
        doctor_scores: Dict[str, Dict[str, Any]],
        red_flags: List[str],
        primary_cluster: str
    ):
        """
        Если есть опасные признаки, усиливаем наиболее релевантных специалистов
        """
        if not red_flags:
            return

        red_flag_set = {flag.lower() for flag in red_flags}

        if any(flag in red_flag_set for flag in ["ампутация", "кровотечение", "открытая рана", "перелом"]):
            for name in ["Травматолог", "Хирург"]:
                if name in doctor_scores:
                    doctor_scores[name]["score"] += 20

        if any(flag in red_flag_set for flag in ["боль в груди", "давление в груди", "одышка"]):
            if "Кардиолог" in doctor_scores:
                doctor_scores["Кардиолог"]["score"] += 12
            if "Пульмонолог" in doctor_scores:
                doctor_scores["Пульмонолог"]["score"] += 6

        if any(flag in red_flag_set for flag in ["судороги", "потеря сознания"]):
            if "Невролог" in doctor_scores:
                doctor_scores["Невролог"]["score"] += 16

        # При red flags терапевта не убираем, но немного ослабляем,
        # если профиль уже явно специализированный
        if primary_cluster in ["trauma", "cardio", "neuro"] and "Терапевт" in doctor_scores:
            doctor_scores["Терапевт"]["score"] -= 6

    def _apply_duration_adjustments(
        self,
        doctor_scores: Dict[str, Dict[str, Any]],
        duration: str,
        primary_cluster: str,
        normalized_symptoms: List[str]
    ):
        """
        Длительность немного влияет на вес врачей
        """
        duration_text = (duration or "").lower()

        if "меньше 24 часов" in duration_text:
            if primary_cluster in ["cardio", "trauma", "neuro"]:
                self._boost_primary_doctors(doctor_scores, primary_cluster, +8)
            if "Терапевт" in doctor_scores:
                doctor_scores["Терапевт"]["score"] += 2

        if "больше недели" in duration_text:
            if primary_cluster in ["ent", "gastro", "derm", "urinary"]:
                self._boost_primary_doctors(doctor_scores, primary_cluster, +5)

        if "около месяца" in duration_text or "давно" in duration_text:
            if primary_cluster in ["derm", "gastro", "urinary", "gyn"]:
                self._boost_primary_doctors(doctor_scores, primary_cluster, +4)

    def _apply_profile_adjustments(
        self,
        doctor_scores: Dict[str, Dict[str, Any]],
        user_profile: Dict[str, Any],
        parsed: Dict[str, Any]
    ):
        """
        Возраст/пол могут слегка скорректировать выбор
        """
        gender = user_profile.get("gender")
        age = user_profile.get("age")
        normalized_symptoms = parsed.get("normalized_symptoms", [])

        if gender == "female":
            if any(sym in normalized_symptoms for sym in ["боль внизу живота", "кровянистые выделения", "задержка месячных"]):
                if "Гинеколог" in doctor_scores:
                    doctor_scores["Гинеколог"]["score"] += 12

        if isinstance(age, int):
            if age >= 60:
                if "Терапевт" in doctor_scores:
                    doctor_scores["Терапевт"]["score"] += 4
                if "Кардиолог" in doctor_scores and any(
                    sym in normalized_symptoms for sym in ["боль в груди", "давление в груди", "учащенное сердцебиение"]
                ):
                    doctor_scores["Кардиолог"]["score"] += 6

            if age < 18:
                if "Терапевт" in doctor_scores:
                    doctor_scores["Терапевт"]["score"] += 3

    def _normalize_doctor_scores(self, doctor_scores: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Нормализует баллы врачей в проценты
        """
        if not doctor_scores:
            return []

        # Убираем совсем слабые или ушедшие в минус
        cleaned = {
            name: data
            for name, data in doctor_scores.items()
            if data["score"] > 0
        }

        if not cleaned:
            return []

        sorted_items = sorted(
            cleaned.items(),
            key=lambda item: item[1]["score"],
            reverse=True
        )

        top_items = sorted_items[:5]
        total_score = sum(data["score"] for _, data in top_items)

        result = []

        for name, data in top_items:
            match_percent = round((data["score"] / total_score) * 100) if total_score > 0 else 0

            # собираем 1 краткую уникальную причину
            reason = self._compress_reasons(data["reasons"])

            result.append({
                "name": name,
                "match_percent": max(1, min(99, match_percent)),
                "reason": reason
            })

        # поправляем сумму до 100 при необходимости
        current_sum = sum(item["match_percent"] for item in result)
        if result and current_sum != 100:
            diff = 100 - current_sum
            result[0]["match_percent"] = max(1, min(99, result[0]["match_percent"] + diff))

        return result

    def _compress_reasons(self, reasons: List[str]) -> str:
        """
        Выбирает одну внятную причину
        """
        unique = []
        seen = set()

        for reason in reasons:
            key = reason.strip().lower()
            if key and key not in seen:
                seen.add(key)
                unique.append(reason.strip())

        if not unique:
            return "Рекомендуется консультация для уточнения диагноза."

        return unique[0]

    def _determine_urgency(
        self,
        parsed: Dict[str, Any],
        duration: str,
        additional_symptoms: List[str]
    ) -> tuple[str, str]:
        """
        Определение срочности
        """
        red_flags = parsed.get("red_flags", [])
        normalized_symptoms = parsed.get("normalized_symptoms", [])
        primary_cluster = parsed.get("primary_cluster", "general")
        duration_text = (duration or "").lower()

        # 1. Red flags — самый сильный приоритет
        highest_urgency = None
        highest_reason = None

        urgency_order = {
            "low": 1,
            "medium": 2,
            "high": 3,
            "emergency": 4
        }

        for flag in red_flags:
            rule = RED_FLAG_URGENCY_RULES.get(flag)
            if not rule:
                continue

            level, reason = rule
            if highest_urgency is None or urgency_order[level] > urgency_order[highest_urgency]:
                highest_urgency = level
                highest_reason = reason

        if highest_urgency:
            return highest_urgency, highest_reason

        # 2. Сильные симптомы из этапов 2/3
        additional_text = " ".join(additional_symptoms).lower()

        if any(keyword in additional_text for keyword in SEVERE_KEYWORDS):
            if primary_cluster in ["cardio", "neuro", "trauma"]:
                return "high", "Есть признаки возможного ухудшения состояния, лучше обратиться в течение 24 часов."
            return "high", "Есть признаки более тяжелого течения симптомов, рекомендуется обратиться быстрее."

        # 3. По кластерам и давности
        if primary_cluster == "cardio":
            if "меньше 24 часов" in duration_text or "сегодня" in duration_text:
                return "high", "Симптомы со стороны сердечно-сосудистой системы лучше оценить в течение 24 часов."
            return "medium", "Рекомендуется консультация кардиологического профиля в ближайшие дни."

        if primary_cluster == "neuro":
            if "меньше 24 часов" in duration_text or "сегодня" in duration_text:
                return "high", "Неврологические жалобы при недавнем начале лучше оценить в течение 24 часов."
            return "medium", "Рекомендуется консультация невролога в ближайшие дни."

        if primary_cluster == "trauma":
            return "high", "При травме рекомендуется обратиться к врачу в ближайшее время."

        if primary_cluster == "respiratory":
            if "меньше 24 часов" in duration_text and "температура" in normalized_symptoms:
                return "medium", "Рекомендуется консультация в ближайшие дни."
            return "medium", "Рекомендуется консультация терапевта или профильного специалиста."

        if primary_cluster in ["gastro", "ent", "urinary", "gyn"]:
            return "medium", "Рекомендуется консультация в ближайшие дни."

        if primary_cluster == "derm":
            if "больше недели" in duration_text or "около месяца" in duration_text or "давно" in duration_text:
                return "low", "Ситуация похожа на плановый прием, если состояние стабильное."
            return "medium", "Рекомендуется консультация в ближайшие дни."

        # default
        return "medium", "Рекомендуется консультация в ближайшее время."
