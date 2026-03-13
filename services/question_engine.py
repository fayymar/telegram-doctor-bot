from typing import Dict, List, Any


# ---------------------------------------------------------
# 1. Наборы симптомов для ЭТАПА 2
# Этап 2 = профильные уточнения
# ---------------------------------------------------------

CLUSTER_STAGE2_QUESTIONS = {
    "general": [
        "температура",
        "слабость",
        "озноб",
        "ломота",
        "головокружение",
        "тошнота",
    ],
    "respiratory": [
        "одышка",
        "мокрота",
        "боль в груди",
        "температура",
        "слабость",
        "осиплость",
    ],
    "ent": [
        "насморк",
        "заложенность носа",
        "боль в горле",
        "осиплость",
        "боль в ухе",
        "боль при глотании",
    ],
    "cardio": [
        "боль в груди",
        "давление в груди",
        "учащенное сердцебиение",
        "одышка",
        "головокружение",
        "слабость",
    ],
    "neuro": [
        "головокружение",
        "онемение",
        "тошнота",
        "слабость",
        "нарушение зрения",
        "нарушение речи",
    ],
    "gastro": [
        "тошнота",
        "рвота",
        "диарея",
        "запор",
        "вздутие живота",
        "изжога",
    ],
    "derm": [
        "зуд",
        "сыпь",
        "покраснение кожи",
        "отек",
        "жжение кожи",
        "шелушение",
    ],
    "urinary": [
        "частое мочеиспускание",
        "жжение при мочеиспускании",
        "боль в пояснице",
        "температура",
        "слабость",
        "боль внизу живота",
    ],
    "gyn": [
        "боль внизу живота",
        "кровянистые выделения",
        "задержка месячных",
        "слабость",
        "тошнота",
        "температура",
    ],
    "trauma": [
        "кровотечение",
        "отек",
        "резкая боль",
        "онемение",
        "невозможность двигать",
        "деформация конечности",
    ],
}


# ---------------------------------------------------------
# 2. Наборы симптомов для ЭТАПА 3
# Этап 3 = срочность / red flags / тяжесть
# ---------------------------------------------------------

CLUSTER_STAGE3_QUESTIONS = {
    "general": [
        "высокая температура",
        "сильная слабость",
        "потеря сознания",
        "резкое ухудшение",
        "судороги",
        "обезвоживание",
    ],
    "respiratory": [
        "трудно дышать",
        "боль в груди",
        "синюшность губ",
        "высокая температура",
        "кашель с кровью",
        "одышка в покое",
    ],
    "ent": [
        "трудно глотать",
        "трудно дышать",
        "высокая температура",
        "сильная боль",
        "гнойные выделения",
        "выраженный отек",
    ],
    "cardio": [
        "сильная боль в груди",
        "одышка в покое",
        "холодный пот",
        "потеря сознания",
        "онемение руки",
        "сильная слабость",
    ],
    "neuro": [
        "нарушение речи",
        "слабость в руке или ноге",
        "судороги",
        "потеря сознания",
        "нарушение зрения",
        "сильная головная боль",
    ],
    "gastro": [
        "резкая боль в животе",
        "многократная рвота",
        "кровь в стуле",
        "обезвоживание",
        "высокая температура",
        "напряжение живота",
    ],
    "derm": [
        "быстрое распространение сыпи",
        "отек лица",
        "трудно дышать",
        "высокая температура",
        "пузыри на коже",
        "сильный зуд",
    ],
    "urinary": [
        "кровь в моче",
        "высокая температура",
        "сильная боль в пояснице",
        "озноб",
        "задержка мочи",
        "сильная слабость",
    ],
    "gyn": [
        "обильное кровотечение",
        "сильная боль внизу живота",
        "потеря сознания",
        "слабость",
        "высокая температура",
        "головокружение",
    ],
    "trauma": [
        "сильное кровотечение",
        "невозможность двигать",
        "потеря чувствительности",
        "деформация конечности",
        "потеря сознания",
        "очень сильная боль",
    ],
}


# ---------------------------------------------------------
# 3. Дополнительные объединяющие наборы для mixed cases
# ---------------------------------------------------------

MIXED_CLUSTER_BRIDGE_RULES = {
    frozenset(["respiratory", "ent"]): [
        "насморк",
        "боль в горле",
        "осиплость",
        "мокрота",
        "одышка",
        "боль при глотании",
    ],
    frozenset(["cardio", "respiratory"]): [
        "боль в груди",
        "одышка",
        "давление в груди",
        "кашель с кровью",
        "одышка в покое",
        "учащенное сердцебиение",
    ],
    frozenset(["neuro", "general"]): [
        "головокружение",
        "онемение",
        "нарушение зрения",
        "слабость",
        "тошнота",
        "нарушение речи",
    ],
    frozenset(["gastro", "general"]): [
        "тошнота",
        "рвота",
        "диарея",
        "температура",
        "слабость",
        "вздутие живота",
    ],
    frozenset(["gastro", "urinary"]): [
        "боль внизу живота",
        "температура",
        "тошнота",
        "жжение при мочеиспускании",
        "боль в пояснице",
        "рвота",
    ],
    frozenset(["gyn", "gastro"]): [
        "боль внизу живота",
        "тошнота",
        "температура",
        "кровянистые выделения",
        "рвота",
        "слабость",
    ],
}


# ---------------------------------------------------------
# 4. Синонимы/почти дубли
# Чтобы не показывать похожие симптомы повторно
# ---------------------------------------------------------

SYMPTOM_EQUIVALENTS = {
    "кашель": {"кашель"},
    "головная боль": {"головная боль", "сильная головная боль"},
    "температура": {"температура", "высокая температура"},
    "одышка": {"одышка", "трудно дышать", "одышка в покое"},
    "боль в груди": {"боль в груди", "сильная боль в груди", "давление в груди"},
    "тошнота": {"тошнота"},
    "рвота": {"рвота", "многократная рвота"},
    "слабость": {"слабость", "сильная слабость"},
    "кровотечение": {"кровотечение", "сильное кровотечение"},
    "потеря сознания": {"потеря сознания"},
    "судороги": {"судороги"},
    "отек": {"отек", "выраженный отек", "отек лица"},
    "боль внизу живота": {"боль внизу живота", "сильная боль внизу живота"},
    "боль в животе": {"боль в животе", "резкая боль в животе"},
    "боль в пояснице": {"боль в пояснице", "сильная боль в пояснице"},
    "нарушение зрения": {"нарушение зрения"},
    "нарушение речи": {"нарушение речи"},
    "онемение": {"онемение", "онемение руки", "слабость в руке или ноге"},
}


# ---------------------------------------------------------
# 5. Вспомогательные функции
# ---------------------------------------------------------

def _normalize_symptom_key(symptom: str) -> str:
    return (symptom or "").strip().lower()


def _expand_equivalents(symptoms: List[str]) -> set:
    """
    Расширяет список симптомов через словарь эквивалентов,
    чтобы не показывать повторы и почти повторы
    """
    expanded = set()

    for symptom in symptoms:
        key = _normalize_symptom_key(symptom)
        expanded.add(key)

        if key in SYMPTOM_EQUIVALENTS:
            expanded.update(item.lower() for item in SYMPTOM_EQUIVALENTS[key])

        for canonical, variants in SYMPTOM_EQUIVALENTS.items():
            if key in {v.lower() for v in variants}:
                expanded.add(canonical.lower())
                expanded.update(item.lower() for item in variants)

    return expanded


def _deduplicate_preserve_order(items: List[str]) -> List[str]:
    seen = set()
    result = []

    for item in items:
        key = _normalize_symptom_key(item)
        if not key:
            continue
        if key in seen:
            continue
        seen.add(key)
        result.append(item)

    return result


def _filter_already_used(candidates: List[str], used_symptoms: List[str]) -> List[str]:
    """
    Убирает симптомы, которые пользователь уже указывал или которые почти совпадают по смыслу
    """
    expanded_used = _expand_equivalents(used_symptoms)
    filtered = []

    for symptom in candidates:
        key = _normalize_symptom_key(symptom)
        if key in expanded_used:
            continue
        filtered.append(symptom)

    return _deduplicate_preserve_order(filtered)


def _merge_cluster_stage2(primary_cluster: str, secondary_clusters: List[str]) -> List[str]:
    """
    Собирает кандидатов для ЭТАПА 2:
    сначала primary, потом secondary
    """
    result = []

    result.extend(CLUSTER_STAGE2_QUESTIONS.get(primary_cluster, []))

    for cluster in secondary_clusters[:2]:
        result.extend(CLUSTER_STAGE2_QUESTIONS.get(cluster, []))

    return _deduplicate_preserve_order(result)


def _merge_cluster_stage3(primary_cluster: str, secondary_clusters: List[str]) -> List[str]:
    """
    Собирает кандидатов для ЭТАПА 3:
    сначала primary, потом secondary
    """
    result = []

    result.extend(CLUSTER_STAGE3_QUESTIONS.get(primary_cluster, []))

    for cluster in secondary_clusters[:2]:
        result.extend(CLUSTER_STAGE3_QUESTIONS.get(cluster, []))

    return _deduplicate_preserve_order(result)


def _get_mixed_bridge_questions(primary_cluster: str, secondary_clusters: List[str]) -> List[str]:
    """
    Для mixed case возвращает вопросы, которые помогают развести 2 кластера
    """
    result = []

    for cluster in secondary_clusters[:2]:
        bridge_key = frozenset([primary_cluster, cluster])
        result.extend(MIXED_CLUSTER_BRIDGE_RULES.get(bridge_key, []))

    return _deduplicate_preserve_order(result)


# ---------------------------------------------------------
# 6. Основные функции
# ---------------------------------------------------------

def build_stage2_questions(parsed_symptoms: Dict[str, Any], limit: int = 6) -> List[str]:
    """
    Возвращает список симптомов для ЭТАПА 2:
    профильные уточнения

    Логика:
    - если confidence low -> добавляем bridge questions для mixed case
    - затем primary cluster
    - затем secondary clusters
    - убираем уже введенные симптомы
    """
    normalized_symptoms = parsed_symptoms.get("normalized_symptoms", [])
    primary_cluster = parsed_symptoms.get("primary_cluster", "general")
    secondary_clusters = parsed_symptoms.get("secondary_clusters", [])
    confidence = parsed_symptoms.get("confidence", "low")

    candidates = []

    if confidence == "low":
        candidates.extend(_get_mixed_bridge_questions(primary_cluster, secondary_clusters))

    candidates.extend(_merge_cluster_stage2(primary_cluster, secondary_clusters))
    candidates = _deduplicate_preserve_order(candidates)

    filtered = _filter_already_used(candidates, normalized_symptoms)

    return filtered[:limit]


def build_stage3_questions(
    parsed_symptoms: Dict[str, Any],
    selected_stage2_symptoms: List[str] | None = None,
    limit: int = 6
) -> List[str]:
    """
    Возвращает список симптомов для ЭТАПА 3:
    срочность / red flags / тяжесть

    Логика:
    - берем stage3 по primary + secondary
    - исключаем:
      - исходные симптомы
      - уже выбранные на 2 этапе
    """
    normalized_symptoms = parsed_symptoms.get("normalized_symptoms", [])
    primary_cluster = parsed_symptoms.get("primary_cluster", "general")
    secondary_clusters = parsed_symptoms.get("secondary_clusters", [])

    selected_stage2_symptoms = selected_stage2_symptoms or []

    candidates = _merge_cluster_stage3(primary_cluster, secondary_clusters)
    used = normalized_symptoms + selected_stage2_symptoms

    filtered = _filter_already_used(candidates, used)

    return filtered[:limit]


def build_question_plan(
    parsed_symptoms: Dict[str, Any],
    selected_stage2_symptoms: List[str] | None = None
) -> Dict[str, Any]:
    """
    Возвращает готовый план вопросов для этапов 2 и 3
    """
    stage2 = build_stage2_questions(parsed_symptoms, limit=6)
    stage3 = build_stage3_questions(parsed_symptoms, selected_stage2_symptoms or [], limit=6)

    return {
        "primary_cluster": parsed_symptoms.get("primary_cluster", "general"),
        "secondary_clusters": parsed_symptoms.get("secondary_clusters", []),
        "confidence": parsed_symptoms.get("confidence", "low"),
        "stage2_questions": stage2,
        "stage3_questions": stage3,
    }
