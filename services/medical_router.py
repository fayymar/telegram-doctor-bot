from typing import Dict, List, Any

from services.symptom_parser import parse_symptoms
from services.red_flags import detect_red_flags
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

            red_flag_result = detect_red_flags(
                parsed=parsed,
                additional_symptoms=additional_symptoms
            )

            specialists = self._build_specialist_scores(
                parsed=parsed,
                duration=duration,
                user_profile=user_profile,
                additional_symptoms=additional_symptoms,
                red_flag_result=red_flag_result
            )

            urgency, urgency_reason = self._determine_urgency(
                parsed=parsed,
                duration=duration,
                additional_symptoms=additional_symptoms,
                red_flag_result=red_flag_result
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
                "Medical routing complete | primary_cluster=%s | top_specialist=%s | urgency=%s | red_flags=%s",
                parsed.get("primary_cluster"),
                specialists[0]["name"] if specialists else "N/A",
                urgency,
                red_flag_result.get("matched_flags", [])
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
        additional_symptoms: List[str],
        red_flag_result: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        cluster_scores = parsed.get("cluster_scores", {})
        primary_cluster = parsed.get("primary_cluster", "general")
        secondary_clusters = parsed.get("secondary_clusters", [])
        confidence = parsed.get("confidence", "low")
        normalized_symptoms = parsed.get("normalized_symptoms", [])
        red_flag_cluster_boosts = red_flag_result.get("cluster_boosts", {})

        doctor_scores: Dict[str, Dict[str, Any]] = {}

        # 1. Основной кластер
        self._apply_cluster_to_doctors(
            doctor_scores=doctor_scores,
            cluster=primary_cluster,
            cluster_weight=1.0,
            parsed_cluster_score=cluster_scores.get(primary_cluster, 0)
        )

        # 2. Вторичные кластеры
        for cluster in secondary_clusters[:2]:
            self._apply_cluster_to_doctors(
                doctor_scores=doctor_scores,
                cluster=cluster,
                cluster_weight=0.55,
                parsed_cluster_score=cluster_scores.get(cluster, 0)
            )

        # 3. Усиление кластеров из red flags
        for boosted_cluster, boost_value in red_flag_cluster_boosts.items():
            self._apply_cluster_to_doctors(
                doctor_scores=doctor_scores,
                cluster=boosted_cluster,
                cluster_weight=0.35,
                parsed_cluster_score=boost_value
            )

        # 4. Confidence
        if confidence == "high":
            self._boost_primary_doctors(doctor_scores, primary_cluster, +8)
        elif confidence == "low":
            self._boost_generalists(doctor_scores, +6)

        # 5. Поправки по red flags
        self._apply_red_flag_doctor_adjustments(
            doctor_scores=doctor_scores,
            red_flag_result=red_flag_result,
            primary_cluster=primary_cluster
        )

        # 6. Поправки по длительности
        self._apply_duration_adjustments(
            doctor_scores=doctor_scores,
            duration=duration,
            primary_cluster=primary_cluster,
            normalized_symptoms=normalized_symptoms
        )

        # 7. Поправки по профилю
        self._apply_profile_adjustments(
            doctor_scores=doctor_scores,
            user_profile=user_profile,
            parsed=parsed
        )

        ranked = self._normalize_doctor_scores(doctor_scores)
        return ranked[:5]

    def _apply_cluster_to_doctors(
        self,
        doctor_scores: Dict[str, Dict[str, Any]],
        cluster: str,
        cluster_weight: float,
        parsed_cluster_score: int
    ):
        doctor_templates = CLUSTER_TO_SPECIALISTS.get(cluster, CLUSTER_TO_SPECIALISTS["general"])

        for item in doctor_templates:
            name = item["name"]
            base_score = item["base_score"]
            reason = item["reason"]

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
        doctor_templates = CLUSTER_TO_SPECIALISTS.get(primary_cluster, [])
        primary_names = {item["name"] for item in doctor_templates}

        for name in primary_names:
            if name in doctor_scores:
                doctor_scores[name]["score"] += bonus

    def _boost_generalists(self, doctor_scores: Dict[str, Dict[str, Any]], bonus: int):
        if "Терапевт" in doctor_scores:
            doctor_scores["Терапевт"]["score"] += bonus

    def _apply_red_flag_doctor_adjustments(
        self,
        doctor_scores: Dict[str, Dict[str, Any]],
        red_flag_result: Dict[str, Any],
        primary_cluster: str
    ):
        if not red_flag_result.get("has_red_flags"):
            return

        matched_flags = {flag.lower() for flag in red_flag_result.get("matched_flags", [])}
        urgency = red_flag_result.get("urgency", "high")

        if any(flag in matched_flags for flag in ["ампутация", "кровотечение", "открытая рана", "перелом", "рана + кровотечение", "открытая рана + кровотечение"]):
            for name in ["Травматолог", "Хирург"]:
                if name in doctor_scores:
                    doctor_scores[name]["score"] += 20

        if any(flag in matched_flags for flag in ["боль в груди", "давление в груди", "одышка", "боль в груди + одышка"]):
            if "Кардиолог" in doctor_scores:
                doctor_scores["Кардиолог"]["score"] += 12
            if "Пульмонолог" in doctor_scores:
                doctor_scores["Пульмонолог"]["score"] += 6

        if any(flag in matched_flags for flag in ["судороги", "потеря сознания", "головная боль + онемение", "головная боль + нарушение речи", "слабость в руке или ноге + нарушение речи"]):
            if "Невролог" in doctor_scores:
                doctor_scores["Невролог"]["score"] += 16

        if urgency == "emergency" and primary_cluster in ["trauma", "cardio", "neuro"] and "Терапевт" in doctor_scores:
            doctor_scores["Терапевт"]["score"] -= 8

    def _apply_duration_adjustments(
        self,
        doctor_scores: Dict[str, Dict[str, Any]],
        duration: str,
        primary_cluster: str,
        normalized_symptoms: List[str]
    ):
        duration_text = (duration or "").lower()

        if "меньше 24 часов" in duration_text:
            if primary_cluster in ["cardio", "trauma", "neuro"]:
                self._boost_primary_doctors(doctor_scores, primary_cluster, +8)
            if "Терапевт" in doctor_scores:
                doctor_scores["Терапевт"]["score"] += 2

        if "1-3 дня" in duration_text or "3-7 дней" in duration_text:
            if primary_cluster in ["respiratory", "ent", "gastro", "urinary"]:
                self._boost_primary_doctors(doctor_scores, primary_cluster, +3)

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
        if not doctor_scores:
            return []

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
            reason = self._compress_reasons(data["reasons"])

            result.append({
                "name": name,
                "match_percent": max(1, min(99, match_percent)),
                "reason": reason
            })

        current_sum = sum(item["match_percent"] for item in result)
        if result and current_sum != 100:
            diff = 100 - current_sum
            result[0]["match_percent"] = max(1, min(99, result[0]["match_percent"] + diff))

        return result

    def _compress_reasons(self, reasons: List[str]) -> str:
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
        additional_symptoms: List[str],
        red_flag_result: Dict[str, Any]
    ) -> tuple[str, str]:
        normalized_symptoms = parsed.get("normalized_symptoms", [])
        primary_cluster = parsed.get("primary_cluster", "general")
        duration_text = (duration or "").lower()

        # 1. Новый red flag engine — самый сильный приоритет
        if red_flag_result.get("has_red_flags"):
            reasons = red_flag_result.get("reasons", [])
            urgency = red_flag_result.get("urgency", "high")

            if reasons:
                return urgency, reasons[0]

            if urgency == "emergency":
                return "emergency", "Есть опасные признаки, требуется немедленная медицинская помощь."

            return urgency, "Есть признаки более серьезного состояния, рекомендуется обратиться срочно."

        # 2. Длительность + кластер
        if primary_cluster == "cardio":
            if "меньше 24 часов" in duration_text:
                return "high", "Симптомы со стороны сердечно-сосудистой системы лучше оценить в течение 24 часов."
            return "medium", "Рекомендуется консультация кардиологического профиля в ближайшие дни."

        if primary_cluster == "neuro":
            if "меньше 24 часов" in duration_text:
                return "high", "Неврологические жалобы при недавнем начале лучше оценить в течение 24 часов."
            return "medium", "Рекомендуется консультация невролога в ближайшие дни."

        if primary_cluster == "trauma":
            return "high", "При травме рекомендуется обратиться к врачу в ближайшее время."

        if primary_cluster == "respiratory":
            if "температура" in normalized_symptoms and "меньше 24 часов" in duration_text:
                return "medium", "Рекомендуется консультация в ближайшие дни."
            return "medium", "Рекомендуется консультация терапевта или профильного специалиста."

        if primary_cluster in ["gastro", "ent", "urinary", "gyn"]:
            return "medium", "Рекомендуется консультация в ближайшие дни."

        if primary_cluster == "derm":
            if "больше недели" in duration_text or "давно" in duration_text:
                return "low", "Ситуация похожа на плановый прием, если состояние стабильное."
            return "medium", "Рекомендуется консультация в ближайшие дни."

        return "medium", "Рекомендуется консультация в ближайшее время."
