from typing import Dict, List, Any, Tuple

from services.symptom_parser import parse_symptoms
from services.red_flags import detect_red_flags
from utils.logger import setup_logger

logger = setup_logger(__name__)


# Здесь уже НЕ делаем терапевта главной фигурой почти в каждом кластере.
# Наоборот: сначала узкий специалист, терапевт только как fallback/backup.
CLUSTER_TO_SPECIALISTS = {
    "general": [
        {
            "name": "Терапевт",
            "base_score": 80,
            "reason": "Симптомы пока слишком общие, поэтому нужен врач для первичной очной оценки."
        }
    ],
    "respiratory": [
        {
            "name": "Пульмонолог",
            "base_score": 86,
            "reason": "Основные жалобы больше относятся к дыхательной системе."
        },
        {
            "name": "ЛОР",
            "base_score": 58,
            "reason": "Часть симптомов может относиться к верхним дыхательным путям и ЛОР-профилю."
        },
        {
            "name": "Терапевт",
            "base_score": 22,
            "reason": "Может подойти только как резервный маршрут, если картина смешанная."
        },
    ],
    "ent": [
        {
            "name": "ЛОР",
            "base_score": 88,
            "reason": "Жалобы больше соответствуют заболеваниям уха, горла и носа."
        },
        {
            "name": "Пульмонолог",
            "base_score": 22,
            "reason": "Некоторые жалобы могут пересекаться с дыхательной системой."
        },
        {
            "name": "Терапевт",
            "base_score": 18,
            "reason": "Подходит как резервный вариант при смешанной картине."
        },
    ],
    "cardio": [
        {
            "name": "Кардиолог",
            "base_score": 92,
            "reason": "Симптомы больше относятся к сердечно-сосудистой системе."
        },
        {
            "name": "Пульмонолог",
            "base_score": 28,
            "reason": "Одышка и часть жалоб могут частично пересекаться с дыхательной системой."
        },
        {
            "name": "Терапевт",
            "base_score": 12,
            "reason": "Подходит только как резервный маршрут, если картина не полностью ясна."
        },
    ],
    "neuro": [
        {
            "name": "Невролог",
            "base_score": 92,
            "reason": "Симптомы больше соответствуют неврологическому профилю."
        },
        {
            "name": "Терапевт",
            "base_score": 12,
            "reason": "Подходит как резервный вариант при неясной картине."
        },
    ],
    "gastro": [
        {
            "name": "Гастроэнтеролог",
            "base_score": 90,
            "reason": "Жалобы больше связаны с желудочно-кишечным трактом."
        },
        {
            "name": "Хирург",
            "base_score": 34,
            "reason": "Часть симптомов со стороны живота иногда требует хирургической оценки."
        },
        {
            "name": "Терапевт",
            "base_score": 14,
            "reason": "Может подойти только как резервный маршрут."
        },
    ],
    "derm": [
        {
            "name": "Дерматолог",
            "base_score": 92,
            "reason": "Симптомы больше относятся к кожному профилю."
        },
        {
            "name": "Аллерголог",
            "base_score": 38,
            "reason": "Часть кожных проявлений может быть связана с аллергической реакцией."
        },
        {
            "name": "Терапевт",
            "base_score": 10,
            "reason": "Подходит только как резервный вариант."
        },
    ],
    "urinary": [
        {
            "name": "Уролог",
            "base_score": 92,
            "reason": "Жалобы больше соответствуют мочевыделительной системе."
        },
        {
            "name": "Нефролог",
            "base_score": 36,
            "reason": "Часть симптомов может указывать на вовлечение почек."
        },
        {
            "name": "Терапевт",
            "base_score": 10,
            "reason": "Подходит как резервный маршрут при неясной картине."
        },
    ],
    "gyn": [
        {
            "name": "Гинеколог",
            "base_score": 94,
            "reason": "Жалобы больше соответствуют гинекологическому профилю."
        },
        {
            "name": "Уролог",
            "base_score": 18,
            "reason": "Часть симптомов может пересекаться с мочевыделительной системой."
        },
        {
            "name": "Терапевт",
            "base_score": 8,
            "reason": "Подходит только как резервный маршрут."
        },
    ],
    "trauma": [
        {
            "name": "Травматолог",
            "base_score": 94,
            "reason": "Жалобы относятся к травме, повреждению тканей или костно-суставной системе."
        },
        {
            "name": "Хирург",
            "base_score": 76,
            "reason": "Подходит при ранах, кровотечении и повреждении мягких тканей."
        },
        {
            "name": "Терапевт",
            "base_score": 4,
            "reason": "Практически не является основным маршрутом при травме."
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
        Главная функция маршрутизации:
        1. объединяем симптомы
        2. парсим
        3. проверяем red flags
        4. выбираем профильного врача
        5. терапевта даём только когда случай реально неясный
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
                specialists = [self._fallback_specialist()]

            logger.info(
                "Medical routing complete | primary_cluster=%s | secondary_clusters=%s | confidence=%s | top_specialist=%s | urgency=%s",
                parsed.get("primary_cluster"),
                parsed.get("secondary_clusters", []),
                parsed.get("confidence"),
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
                "specialists": [self._fallback_specialist()],
                "urgency": "medium",
                "urgency_reason": "Рекомендуется консультация в ближайшее время."
            }

    def _fallback_specialist(self) -> Dict[str, Any]:
        return {
            "name": "Терапевт",
            "match_percent": 80,
            "reason": "Симптомы пока недостаточно специфичны, поэтому нужен врач для первичной очной оценки."
        }

    def _merge_symptoms(self, main_symptoms: str, additional_symptoms: List[str]) -> str:
        parts = []

        if main_symptoms and main_symptoms.strip():
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

        # 1. Основной кластер — главный источник
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
                cluster_weight=0.52,
                parsed_cluster_score=cluster_scores.get(cluster, 0)
            )

        # 3. Усиление из red flags
        for boosted_cluster, boost_value in red_flag_cluster_boosts.items():
            self._apply_cluster_to_doctors(
                doctor_scores=doctor_scores,
                cluster=boosted_cluster,
                cluster_weight=0.38,
                parsed_cluster_score=boost_value
            )

        # 4. Confidence / mixed-case
        self._apply_confidence_adjustments(
            doctor_scores=doctor_scores,
            primary_cluster=primary_cluster,
            confidence=confidence,
            parsed=parsed
        )

        # 5. Red flags doctor routing
        self._apply_red_flag_doctor_adjustments(
            doctor_scores=doctor_scores,
            red_flag_result=red_flag_result,
            primary_cluster=primary_cluster
        )

        # 6. Duration
        self._apply_duration_adjustments(
            doctor_scores=doctor_scores,
            duration=duration,
            primary_cluster=primary_cluster,
            normalized_symptoms=normalized_symptoms
        )

        # 7. Profile
        self._apply_profile_adjustments(
            doctor_scores=doctor_scores,
            user_profile=user_profile,
            parsed=parsed
        )

        # 8. Главная новая логика:
        # убираем доминирование терапевта, если случай уже достаточно понятен
        self._demote_therapist_if_case_is_specific(
            doctor_scores=doctor_scores,
            parsed=parsed,
            red_flag_result=red_flag_result
        )

        ranked = self._normalize_doctor_scores(doctor_scores)
        ranked = self._postprocess_ranked_specialists(
            ranked=ranked,
            parsed=parsed,
            red_flag_result=red_flag_result
        )

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

            score = (base_score * cluster_weight) + (parsed_cluster_score * 5 * cluster_weight)

            if name not in doctor_scores:
                doctor_scores[name] = {
                    "score": 0.0,
                    "reasons": [],
                    "cluster_sources": set()
                }

            doctor_scores[name]["score"] += score
            doctor_scores[name]["reasons"].append(reason)
            doctor_scores[name]["cluster_sources"].add(cluster)

    def _apply_confidence_adjustments(
        self,
        doctor_scores: Dict[str, Dict[str, Any]],
        primary_cluster: str,
        confidence: str,
        parsed: Dict[str, Any]
    ):
        if confidence == "high":
            self._boost_primary_doctors(doctor_scores, primary_cluster, +14)
            self._penalize_therapist(doctor_scores, -10)

        elif confidence == "medium":
            self._boost_primary_doctors(doctor_scores, primary_cluster, +7)
            self._penalize_therapist(doctor_scores, -5)

        else:
            # low confidence
            if self._is_mixed_case(parsed):
                self._boost_generalists(doctor_scores, +8)
            else:
                self._boost_generalists(doctor_scores, +4)

    def _boost_primary_doctors(self, doctor_scores: Dict[str, Dict[str, Any]], primary_cluster: str, bonus: int):
        doctor_templates = CLUSTER_TO_SPECIALISTS.get(primary_cluster, [])
        primary_names = {item["name"] for item in doctor_templates if item["name"] != "Терапевт"}

        for name in primary_names:
            if name in doctor_scores:
                doctor_scores[name]["score"] += bonus

    def _boost_generalists(self, doctor_scores: Dict[str, Dict[str, Any]], bonus: int):
        if "Терапевт" in doctor_scores:
            doctor_scores["Терапевт"]["score"] += bonus

    def _penalize_therapist(self, doctor_scores: Dict[str, Dict[str, Any]], penalty: int):
        if "Терапевт" in doctor_scores:
            doctor_scores["Терапевт"]["score"] += penalty

    def _is_mixed_case(self, parsed: Dict[str, Any]) -> bool:
        primary_cluster = parsed.get("primary_cluster", "general")
        secondary_clusters = parsed.get("secondary_clusters", [])
        confidence = parsed.get("confidence", "low")
        cluster_scores = parsed.get("cluster_scores", {})

        if primary_cluster == "general":
            return True

        if confidence != "low":
            return False

        if not secondary_clusters:
            return False

        primary_score = cluster_scores.get(primary_cluster, 0)
        second_score = cluster_scores.get(secondary_clusters[0], 0)

        return abs(primary_score - second_score) <= 1

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

        trauma_flags = {
            "ампутация",
            "кровотечение",
            "открытая рана",
            "перелом",
            "рана + кровотечение",
            "открытая рана + кровотечение",
        }

        cardio_flags = {
            "боль в груди",
            "давление в груди",
            "одышка",
            "боль в груди + одышка",
        }

        neuro_flags = {
            "судороги",
            "потеря сознания",
            "головная боль + онемение",
            "головная боль + нарушение речи",
            "слабость в руке или ноге + нарушение речи",
        }

        if matched_flags & trauma_flags:
            for name in ["Травматолог", "Хирург"]:
                if name in doctor_scores:
                    doctor_scores[name]["score"] += 28

        if matched_flags & cardio_flags:
            if "Кардиолог" in doctor_scores:
                doctor_scores["Кардиолог"]["score"] += 22
            if "Пульмонолог" in doctor_scores:
                doctor_scores["Пульмонолог"]["score"] += 8

        if matched_flags & neuro_flags:
            if "Невролог" in doctor_scores:
                doctor_scores["Невролог"]["score"] += 26

        if urgency == "emergency":
            self._penalize_therapist(doctor_scores, -14)

        if urgency == "emergency" and primary_cluster in ["trauma", "cardio", "neuro"]:
            self._boost_primary_doctors(doctor_scores, primary_cluster, +10)

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
                self._boost_primary_doctors(doctor_scores, primary_cluster, +10)

        if "1-3 дня" in duration_text or "3-7 дней" in duration_text:
            if primary_cluster in ["respiratory", "ent", "gastro", "urinary"]:
                self._boost_primary_doctors(doctor_scores, primary_cluster, +4)

        if "больше недели" in duration_text:
            if primary_cluster in ["ent", "gastro", "derm", "urinary", "gyn"]:
                self._boost_primary_doctors(doctor_scores, primary_cluster, +6)

        if "около месяца" in duration_text or "давно" in duration_text:
            if primary_cluster in ["derm", "gastro", "urinary", "gyn"]:
                self._boost_primary_doctors(doctor_scores, primary_cluster, +5)

        if (
            "температура" in normalized_symptoms and
            primary_cluster == "respiratory" and
            "больше недели" in duration_text
        ):
            if "Пульмонолог" in doctor_scores:
                doctor_scores["Пульмонолог"]["score"] += 6

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
                    doctor_scores["Гинеколог"]["score"] += 18

        if isinstance(age, int):
            if age >= 60:
                if "Кардиолог" in doctor_scores and any(
                    sym in normalized_symptoms
                    for sym in ["боль в груди", "давление в груди", "учащенное сердцебиение"]
                ):
                    doctor_scores["Кардиолог"]["score"] += 8

            if age < 18:
                # пока оставляем без отдельного педиатра,
                # но немного снижаем уверенность в слишком узком routing
                if "Терапевт" in doctor_scores:
                    doctor_scores["Терапевт"]["score"] += 3

    def _demote_therapist_if_case_is_specific(
        self,
        doctor_scores: Dict[str, Dict[str, Any]],
        parsed: Dict[str, Any],
        red_flag_result: Dict[str, Any]
    ):
        primary_cluster = parsed.get("primary_cluster", "general")
        confidence = parsed.get("confidence", "low")

        if "Терапевт" not in doctor_scores:
            return

        # Если случай уже достаточно понятен — терапевта сильно опускаем
        if primary_cluster != "general" and confidence in ["medium", "high"]:
            doctor_scores["Терапевт"]["score"] *= 0.45

        # При экстренных/опасных сценариях тоже не даём терапевту доминировать
        if red_flag_result.get("urgency") == "emergency":
            doctor_scores["Терапевт"]["score"] *= 0.35

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

    def _postprocess_ranked_specialists(
        self,
        ranked: List[Dict[str, Any]],
        parsed: Dict[str, Any],
        red_flag_result: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        if not ranked:
            return ranked

        primary_cluster = parsed.get("primary_cluster", "general")
        confidence = parsed.get("confidence", "low")
        has_red_flags = red_flag_result.get("has_red_flags", False)

        non_therapists = [item for item in ranked if item["name"] != "Терапевт"]
        therapists = [item for item in ranked if item["name"] == "Терапевт"]

        # Если кейс специфичный и есть хотя бы один узкий врач —
        # ставим узкого врача первым, а терапевта вниз.
        if primary_cluster != "general" and confidence in ["medium", "high"] and non_therapists:
            reordered = non_therapists + therapists
            return self._renormalize_percentages(reordered)

        # Если есть red flags и есть профильный врач — тоже терапевта вниз
        if has_red_flags and non_therapists:
            reordered = non_therapists + therapists
            return self._renormalize_percentages(reordered)

        return ranked

    def _renormalize_percentages(self, ranked: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not ranked:
            return ranked

        weights = []
        for idx, item in enumerate(ranked):
            # Чем выше место, тем чуть больше итоговый вес
            base = max(1, 100 - idx * 10)
            weights.append(base)

        total = sum(weights)
        result = []

        for item, weight in zip(ranked, weights):
            percent = round((weight / total) * 100)
            result.append({
                "name": item["name"],
                "match_percent": percent,
                "reason": item["reason"]
            })

        current_sum = sum(x["match_percent"] for x in result)
        if result and current_sum != 100:
            diff = 100 - current_sum
            result[0]["match_percent"] += diff

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
    ) -> Tuple[str, str]:
        normalized_symptoms = parsed.get("normalized_symptoms", [])
        primary_cluster = parsed.get("primary_cluster", "general")
        duration_text = (duration or "").lower()

        if red_flag_result.get("has_red_flags"):
            reasons = red_flag_result.get("reasons", [])
            urgency = red_flag_result.get("urgency", "high")

            if reasons:
                return urgency, reasons[0]

            if urgency == "emergency":
                return "emergency", "Есть опасные признаки, требуется немедленная медицинская помощь."

            return urgency, "Есть признаки более серьёзного состояния, рекомендуется обратиться срочно."

        if primary_cluster == "cardio":
            if "меньше 24 часов" in duration_text:
                return "high", "Симптомы со стороны сердечно-сосудистой системы лучше оценить в течение 24 часов."
            return "medium", "Рекомендуется консультация кардиолога в ближайшие дни."

        if primary_cluster == "neuro":
            if "меньше 24 часов" in duration_text:
                return "high", "Неврологические жалобы при недавнем начале лучше оценить в течение 24 часов."
            return "medium", "Рекомендуется консультация невролога в ближайшие дни."

        if primary_cluster == "trauma":
            return "high", "При травме рекомендуется обратиться к врачу в ближайшее время."

        if primary_cluster == "respiratory":
            if "температура" in normalized_symptoms and "больше недели" in duration_text:
                return "high", "Если температура и респираторные симптомы держатся долго, лучше обратиться к врачу как можно скорее."
            return "medium", "Рекомендуется консультация профильного врача в ближайшие дни."

        if primary_cluster in ["gastro", "ent", "urinary", "gyn"]:
            return "medium", "Рекомендуется консультация профильного врача в ближайшие дни."

        if primary_cluster == "derm":
            if "больше недели" in duration_text or "давно" in duration_text:
                return "low", "Похоже на плановый приём, если состояние стабильное."
            return "medium", "Рекомендуется консультация в ближайшие дни."

        return "medium", "Симптомы требуют очной консультации для уточнения причины."
