from typing import Dict, Any, List


URGENCY_ORDER = {
    "low": 1,
    "medium": 2,
    "high": 3,
    "emergency": 4
}


DIRECT_RED_FLAGS = {
    "ампутация": {
        "urgency": "emergency",
        "reason": "Есть признаки тяжелой травмы, требуется немедленная медицинская помощь.",
        "cluster_boosts": {
            "trauma": 8
        }
    },
    "потеря сознания": {
        "urgency": "emergency",
        "reason": "Потеря сознания требует немедленной медицинской помощи.",
        "cluster_boosts": {
            "neuro": 5,
            "cardio": 4
        }
    },
    "судороги": {
        "urgency": "emergency",
        "reason": "Судороги требуют срочной медицинской оценки.",
        "cluster_boosts": {
            "neuro": 6
        }
    },
    "кровотечение": {
        "urgency": "high",
        "reason": "Есть признаки кровотечения, требуется срочная медицинская оценка.",
        "cluster_boosts": {
            "trauma": 5
        }
    },
    "открытая рана": {
        "urgency": "high",
        "reason": "Открытая рана требует быстрой оценки врача.",
        "cluster_boosts": {
            "trauma": 5
        }
    },
    "перелом": {
        "urgency": "high",
        "reason": "Есть признаки значимой травмы, рекомендуется обратиться срочно.",
        "cluster_boosts": {
            "trauma": 6
        }
    },
    "боль в груди": {
        "urgency": "high",
        "reason": "Боль в груди требует ускоренной оценки состояния.",
        "cluster_boosts": {
            "cardio": 5
        }
    },
    "давление в груди": {
        "urgency": "high",
        "reason": "Давление в груди требует ускоренной оценки состояния.",
        "cluster_boosts": {
            "cardio": 5
        }
    },
    "одышка": {
        "urgency": "high",
        "reason": "Одышка может быть признаком серьезного состояния.",
        "cluster_boosts": {
            "respiratory": 4,
            "cardio": 3
        }
    }
}


SEVERE_TEXT_RULES = [
    {
        "keywords": ["очень сильная боль"],
        "urgency": "high",
        "reason": "Очень сильная боль требует более быстрой медицинской оценки."
    },
    {
        "keywords": ["сильная боль в груди"],
        "urgency": "emergency",
        "reason": "Сильная боль в груди требует немедленного обращения за медицинской помощью."
    },
    {
        "keywords": ["одышка в покое"],
        "urgency": "emergency",
        "reason": "Одышка в покое является опасным признаком и требует немедленной оценки."
    },
    {
        "keywords": ["кашель с кровью"],
        "urgency": "high",
        "reason": "Кашель с кровью требует срочной оценки врача."
    },
    {
        "keywords": ["кровь в стуле"],
        "urgency": "high",
        "reason": "Кровь в стуле требует ускоренной медицинской оценки."
    },
    {
        "keywords": ["кровь в моче"],
        "urgency": "high",
        "reason": "Кровь в моче требует ускоренной медицинской оценки."
    },
    {
        "keywords": ["обильное кровотечение"],
        "urgency": "emergency",
        "reason": "Обильное кровотечение требует немедленной медицинской помощи."
    },
    {
        "keywords": ["трудно дышать"],
        "urgency": "high",
        "reason": "Затрудненное дыхание требует срочной медицинской оценки."
    },
    {
        "keywords": ["сильная слабость"],
        "urgency": "high",
        "reason": "Выраженная слабость может быть признаком более серьезного состояния."
    },
    {
        "keywords": ["резкое ухудшение"],
        "urgency": "high",
        "reason": "Резкое ухудшение состояния требует срочной оценки врача."
    }
]


COMBINATION_RED_FLAGS = [
    {
        "if_all": ["боль в груди", "одышка"],
        "urgency": "emergency",
        "reason": "Сочетание боли в груди и одышки требует немедленной медицинской оценки.",
        "cluster_boosts": {
            "cardio": 6,
            "respiratory": 2
        }
    },
    {
        "if_all": ["головная боль", "онемение"],
        "urgency": "high",
        "reason": "Сочетание головной боли и онемения требует ускоренной неврологической оценки.",
        "cluster_boosts": {
            "neuro": 6
        }
    },
    {
        "if_all": ["головная боль", "нарушение речи"],
        "urgency": "emergency",
        "reason": "Нарушение речи на фоне головной боли требует немедленной оценки.",
        "cluster_boosts": {
            "neuro": 7
        }
    },
    {
        "if_all": ["слабость в руке или ноге", "нарушение речи"],
        "urgency": "emergency",
        "reason": "Такое сочетание симптомов требует немедленной медицинской помощи.",
        "cluster_boosts": {
            "neuro": 8
        }
    },
    {
        "if_all": ["рана", "кровотечение"],
        "urgency": "high",
        "reason": "Рана с кровотечением требует срочной оценки.",
        "cluster_boosts": {
            "trauma": 5
        }
    },
    {
        "if_all": ["открытая рана", "кровотечение"],
        "urgency": "emergency",
        "reason": "Открытая рана с кровотечением требует немедленной медицинской помощи.",
        "cluster_boosts": {
            "trauma": 7
        }
    },
    {
        "if_all": ["боль в животе", "рвота", "высокая температура"],
        "urgency": "high",
        "reason": "Сочетание боли в животе, рвоты и высокой температуры требует ускоренной оценки.",
        "cluster_boosts": {
            "gastro": 4
        }
    }
]


def _max_urgency(current: str, new: str) -> str:
    if URGENCY_ORDER[new] > URGENCY_ORDER[current]:
        return new
    return current


def detect_red_flags(parsed: Dict[str, Any], additional_symptoms: List[str] | None = None) -> Dict[str, Any]:
    """
    Возвращает:
    {
        "has_red_flags": bool,
        "urgency": "low|medium|high|emergency",
        "reasons": [...],
        "cluster_boosts": {...},
        "matched_flags": [...]
    }
    """
    normalized_symptoms = parsed.get("normalized_symptoms", [])
    additional_symptoms = additional_symptoms or []

    symptom_set = {sym.lower() for sym in normalized_symptoms}
    additional_text = " ".join(additional_symptoms).lower()

    urgency = "low"
    reasons = []
    matched_flags = []
    cluster_boosts: Dict[str, int] = {}

    # 1. Прямые red flags
    for symptom in normalized_symptoms:
        rule = DIRECT_RED_FLAGS.get(symptom)
        if not rule:
            continue

        urgency = _max_urgency(urgency, rule["urgency"])
        reasons.append(rule["reason"])
        matched_flags.append(symptom)

        for cluster, boost in rule.get("cluster_boosts", {}).items():
            cluster_boosts[cluster] = cluster_boosts.get(cluster, 0) + boost

    # 2. Комбинации
    for combo in COMBINATION_RED_FLAGS:
        required = {item.lower() for item in combo["if_all"]}
        if required.issubset(symptom_set):
            urgency = _max_urgency(urgency, combo["urgency"])
            reasons.append(combo["reason"])
            matched_flags.append(" + ".join(combo["if_all"]))

            for cluster, boost in combo.get("cluster_boosts", {}).items():
                cluster_boosts[cluster] = cluster_boosts.get(cluster, 0) + boost

    # 3. Тяжелые текстовые маркеры из этапов 2–3
    for rule in SEVERE_TEXT_RULES:
        if any(keyword.lower() in additional_text for keyword in rule["keywords"]):
            urgency = _max_urgency(urgency, rule["urgency"])
            reasons.append(rule["reason"])
            matched_flags.extend(rule["keywords"])

    unique_reasons = []
    seen_reasons = set()
    for reason in reasons:
        key = reason.strip().lower()
        if key and key not in seen_reasons:
            seen_reasons.add(key)
            unique_reasons.append(reason.strip())

    unique_flags = []
    seen_flags = set()
    for flag in matched_flags:
        key = flag.strip().lower()
        if key and key not in seen_flags:
            seen_flags.add(key)
            unique_flags.append(flag.strip())

    return {
        "has_red_flags": urgency in ["high", "emergency"],
        "urgency": urgency,
        "reasons": unique_reasons,
        "cluster_boosts": cluster_boosts,
        "matched_flags": unique_flags
    }
