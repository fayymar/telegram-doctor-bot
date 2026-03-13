import re
from typing import Dict, List, Tuple, Any


CLUSTERS = [
    "general",
    "respiratory",
    "ent",
    "cardio",
    "neuro",
    "gastro",
    "derm",
    "urinary",
    "gyn",
    "trauma",
]


# ---------------------------------------------------------
# 1. Нормализация пользовательских формулировок
# ---------------------------------------------------------

SYMPTOM_NORMALIZATION_RULES = [
    # Голова / невро
    (r"\bболит голова\b", "головная боль"),
    (r"\bголова болит\b", "головная боль"),
    (r"\bголовные боли\b", "головная боль"),
    (r"\bмигрень\b", "головная боль"),
    (r"\bкружится голова\b", "головокружение"),
    (r"\bголова кружится\b", "головокружение"),
    (r"\bонемела\b", "онемение"),
    (r"\bонемело\b", "онемение"),
    (r"\bонемение\b", "онемение"),
    (r"\bсудороги\b", "судороги"),
    (r"\bобморок\b", "потеря сознания"),
    (r"\bпотерял сознание\b", "потеря сознания"),
    (r"\bпотеря сознания\b", "потеря сознания"),

    # Дыхание / простуда / ЛОР
    (r"\bкашляю\b", "кашель"),
    (r"\bкашель\b", "кашель"),
    (r"\bнасморк\b", "насморк"),
    (r"\bзаложен нос\b", "заложенность носа"),
    (r"\bнос заложен\b", "заложенность носа"),
    (r"\bболит горло\b", "боль в горле"),
    (r"\bгорло болит\b", "боль в горле"),
    (r"\bпершит в горле\b", "боль в горле"),
    (r"\bосиплость\b", "осиплость"),
    (r"\bтрудно дышать\b", "одышка"),
    (r"\bнехватка воздуха\b", "одышка"),
    (r"\bодышка\b", "одышка"),
    (r"\bмокрота\b", "мокрота"),
    (r"\bчихаю\b", "чихание"),
    (r"\bчихание\b", "чихание"),

    # Температура / общее
    (r"\bтемпа\b", "температура"),
    (r"\bтемпература\b", "температура"),
    (r"\bжар\b", "температура"),
    (r"\bозноб\b", "озноб"),
    (r"\bслабость\b", "слабость"),
    (r"\bломота\b", "ломота"),
    (r"\bломит\b", "ломота"),
    (r"\bусталость\b", "слабость"),

    # Сердце / грудь
    (r"\bболит сердце\b", "боль в груди"),
    (r"\bболь в груди\b", "боль в груди"),
    (r"\bдавит в груди\b", "давление в груди"),
    (r"\bдавление в груди\b", "давление в груди"),
    (r"\bсердцебиение\b", "учащенное сердцебиение"),
    (r"\bсильное сердцебиение\b", "учащенное сердцебиение"),
    (r"\bучащенное сердцебиение\b", "учащенное сердцебиение"),
    (r"\bаритмия\b", "нарушение сердечного ритма"),
    (r"\bперебои в сердце\b", "нарушение сердечного ритма"),

    # ЖКТ
    (r"\bболит живот\b", "боль в животе"),
    (r"\bживот болит\b", "боль в животе"),
    (r"\bболь в животе\b", "боль в животе"),
    (r"\bтошнит\b", "тошнота"),
    (r"\bтошнота\b", "тошнота"),
    (r"\bрвет\b", "рвота"),
    (r"\bрвота\b", "рвота"),
    (r"\bпонос\b", "диарея"),
    (r"\bдиарея\b", "диарея"),
    (r"\bжидкий стул\b", "диарея"),
    (r"\bзапор\b", "запор"),
    (r"\bвздутие\b", "вздутие живота"),
    (r"\bизжога\b", "изжога"),

    # Кожа
    (r"\bсыпь\b", "сыпь"),
    (r"\bвысыпания\b", "сыпь"),
    (r"\bзуд\b", "зуд"),
    (r"\bпокраснение\b", "покраснение кожи"),
    (r"\bпятна на коже\b", "сыпь"),
    (r"\bотек\b", "отек"),

    # Мочевыделительная система
    (r"\bчасто хожу в туалет\b", "частое мочеиспускание"),
    (r"\bчастое мочеиспускание\b", "частое мочеиспускание"),
    (r"\bжжение при мочеиспускании\b", "жжение при мочеиспускании"),
    (r"\bбольно мочиться\b", "жжение при мочеиспускании"),
    (r"\bболь в пояснице\b", "боль в пояснице"),

    # Гинекология
    (r"\bболь внизу живота\b", "боль внизу живота"),
    (r"\bзадержка месячных\b", "задержка месячных"),
    (r"\bкровянистые выделения\b", "кровянистые выделения"),

    # Травма
    (r"\bрана\b", "рана"),
    (r"\bоткрытая рана\b", "открытая рана"),
    (r"\bкровотечение\b", "кровотечение"),
    (r"\bидет кровь\b", "кровотечение"),
    (r"\bтравма\b", "травма"),
    (r"\bушиб\b", "ушиб"),
    (r"\bперелом\b", "перелом"),
    (r"\bвывих\b", "вывих"),
    (r"\bоторвана\b", "ампутация"),
    (r"\bоторвало\b", "ампутация"),
    (r"\bампутация\b", "ампутация"),
]


# ---------------------------------------------------------
# 2. Вес симптома по кластерам
# ---------------------------------------------------------

SYMPTOM_CLUSTER_WEIGHTS: Dict[str, Dict[str, int]] = {
    "головная боль": {
        "neuro": 3,
        "general": 2,
        "ent": 1,
    },
    "головокружение": {
        "neuro": 3,
        "cardio": 2,
        "general": 1,
    },
    "онемение": {
        "neuro": 4,
    },
    "судороги": {
        "neuro": 5,
    },
    "потеря сознания": {
        "neuro": 4,
        "cardio": 3,
        "general": 1,
    },

    "кашель": {
        "respiratory": 3,
        "ent": 2,
        "general": 1,
    },
    "насморк": {
        "ent": 3,
        "respiratory": 2,
        "general": 1,
    },
    "заложенность носа": {
        "ent": 3,
        "respiratory": 1,
    },
    "боль в горле": {
        "ent": 3,
        "respiratory": 1,
        "general": 1,
    },
    "осиплость": {
        "ent": 3,
        "respiratory": 1,
    },
    "одышка": {
        "respiratory": 4,
        "cardio": 3,
    },
    "мокрота": {
        "respiratory": 3,
        "ent": 1,
    },
    "чихание": {
        "ent": 3,
        "respiratory": 1,
    },

    "температура": {
        "general": 2,
        "respiratory": 1,
        "ent": 1,
        "gastro": 1,
    },
    "озноб": {
        "general": 2,
        "respiratory": 1,
        "gastro": 1,
    },
    "слабость": {
        "general": 2,
        "cardio": 1,
        "neuro": 1,
        "respiratory": 1,
        "gastro": 1,
    },
    "ломота": {
        "general": 2,
        "respiratory": 1,
    },

    "боль в груди": {
        "cardio": 4,
        "respiratory": 2,
        "gastro": 1,
    },
    "давление в груди": {
        "cardio": 4,
        "respiratory": 1,
    },
    "учащенное сердцебиение": {
        "cardio": 3,
        "general": 1,
    },
    "нарушение сердечного ритма": {
        "cardio": 4,
    },

    "боль в животе": {
        "gastro": 3,
        "general": 1,
    },
    "тошнота": {
        "gastro": 3,
        "neuro": 2,
        "general": 1,
    },
    "рвота": {
        "gastro": 3,
        "general": 1,
    },
    "диарея": {
        "gastro": 3,
        "general": 1,
    },
    "запор": {
        "gastro": 3,
    },
    "вздутие живота": {
        "gastro": 3,
    },
    "изжога": {
        "gastro": 3,
        "cardio": 1,
    },

    "сыпь": {
        "derm": 4,
        "general": 1,
    },
    "зуд": {
        "derm": 4,
        "general": 1,
    },
    "покраснение кожи": {
        "derm": 4,
    },
    "отек": {
        "derm": 2,
        "trauma": 2,
        "general": 1,
    },

    "частое мочеиспускание": {
        "urinary": 4,
    },
    "жжение при мочеиспускании": {
        "urinary": 5,
    },
    "боль в пояснице": {
        "urinary": 2,
        "general": 1,
    },

    "боль внизу живота": {
        "gyn": 3,
        "gastro": 2,
        "urinary": 1,
    },
    "задержка месячных": {
        "gyn": 5,
    },
    "кровянистые выделения": {
        "gyn": 4,
    },

    "рана": {
        "trauma": 4,
    },
    "открытая рана": {
        "trauma": 5,
    },
    "кровотечение": {
        "trauma": 5,
    },
    "травма": {
        "trauma": 4,
    },
    "ушиб": {
        "trauma": 3,
    },
    "перелом": {
        "trauma": 5,
    },
    "вывих": {
        "trauma": 4,
    },
    "ампутация": {
        "trauma": 6,
    },
}


# ---------------------------------------------------------
# 3. Бонусы за сочетания симптомов
# ---------------------------------------------------------

COMBINATION_BONUSES = [
    {
        "if_all": ["кашель", "температура"],
        "add": {"respiratory": 2},
    },
    {
        "if_all": ["кашель", "насморк"],
        "add": {"ent": 1, "respiratory": 1},
    },
    {
        "if_all": ["боль в горле", "насморк"],
        "add": {"ent": 2},
    },
    {
        "if_all": ["головная боль", "головокружение"],
        "add": {"neuro": 2},
    },
    {
        "if_all": ["головная боль", "онемение"],
        "add": {"neuro": 4},
    },
    {
        "if_all": ["боль в груди", "одышка"],
        "add": {"cardio": 3, "respiratory": 1},
    },
    {
        "if_all": ["учащенное сердцебиение", "одышка"],
        "add": {"cardio": 2},
    },
    {
        "if_all": ["боль в животе", "тошнота"],
        "add": {"gastro": 2},
    },
    {
        "if_all": ["боль в животе", "рвота"],
        "add": {"gastro": 2},
    },
    {
        "if_all": ["сыпь", "зуд"],
        "add": {"derm": 3},
    },
    {
        "if_all": ["рана", "кровотечение"],
        "add": {"trauma": 3},
    },
    {
        "if_all": ["открытая рана", "кровотечение"],
        "add": {"trauma": 4},
    },
]


# ---------------------------------------------------------
# 4. Red flags
# Пока здесь просто список - позже можно вынести отдельно
# ---------------------------------------------------------

RED_FLAG_SYMPTOMS = {
    "потеря сознания",
    "судороги",
    "одышка",
    "боль в груди",
    "давление в груди",
    "кровотечение",
    "открытая рана",
    "ампутация",
    "перелом",
}


# ---------------------------------------------------------
# 5. Вспомогательные функции
# ---------------------------------------------------------

def _clean_text(text: str) -> str:
    text = (text or "").lower().strip()
    text = re.sub(r"[;\n]+", ", ", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _split_into_chunks(text: str) -> List[str]:
    """
    Делим текст на куски по запятым, точкам, 'и' и т.д.
    """
    if not text:
        return []

    chunks = re.split(r"[,.]| и | а также | также |;|\n", text)
    result = []

    for chunk in chunks:
        chunk = chunk.strip()
        if chunk:
            result.append(chunk)

    return result


def _normalize_chunk(chunk: str) -> str:
    """
    Преобразует кусок текста в нормализованный симптом, если нашлось совпадение.
    Иначе возвращает исходный очищенный кусок.
    """
    chunk = chunk.strip().lower()

    for pattern, normalized in SYMPTOM_NORMALIZATION_RULES:
        if re.search(pattern, chunk):
            return normalized

    return chunk


def _deduplicate_preserve_order(items: List[str]) -> List[str]:
    seen = set()
    result = []

    for item in items:
        key = item.strip().lower()
        if not key:
            continue
        if key in seen:
            continue
        seen.add(key)
        result.append(item.strip())

    return result


def _detect_body_areas(normalized_symptoms: List[str], raw_text: str) -> List[str]:
    text = f"{raw_text.lower()} " + " ".join(s.lower() for s in normalized_symptoms)

    areas = []

    mapping = {
        "голова": ["голов", "затыл", "висок"],
        "горло": ["горл"],
        "нос": ["нос"],
        "ухо": ["ухо"],
        "грудь": ["груд"],
        "живот": ["живот"],
        "поясница": ["поясниц"],
        "кожа": ["кож", "сып", "зуд", "покраснен"],
        "нога": ["ног"],
        "рука": ["рук"],
    }

    for area, keywords in mapping.items():
        if any(keyword in text for keyword in keywords):
            areas.append(area)

    return areas


def _extract_duration(raw_text: str) -> str | None:
    text = raw_text.lower()

    duration_patterns = [
        (r"меньше 24 часов", "Меньше 24 часов"),
        (r"сегодня", "Сегодня"),
        (r"со вчера", "Со вчера"),
        (r"второй день|2 дня|два дня", "2 дня"),
        (r"третий день|3 дня|три дня", "3 дня"),
        (r"несколько дней", "Несколько дней"),
        (r"неделю|7 дней", "Около недели"),
        (r"две недели|2 недели", "2 недели"),
        (r"месяц", "Около месяца"),
        (r"давно", "Давно"),
    ]

    for pattern, value in duration_patterns:
        if re.search(pattern, text):
            return value

    return None


def _get_empty_scores() -> Dict[str, int]:
    return {cluster: 0 for cluster in CLUSTERS}


def _apply_symptom_scores(normalized_symptoms: List[str]) -> Dict[str, int]:
    scores = _get_empty_scores()

    for symptom in normalized_symptoms:
        weights = SYMPTOM_CLUSTER_WEIGHTS.get(symptom, {})
        for cluster, score in weights.items():
            scores[cluster] += score

    return scores


def _apply_combination_bonuses(normalized_symptoms: List[str], scores: Dict[str, int]) -> Dict[str, int]:
    symptom_set = {s.lower() for s in normalized_symptoms}

    for combo in COMBINATION_BONUSES:
        required = {item.lower() for item in combo["if_all"]}
        if required.issubset(symptom_set):
            for cluster, bonus in combo["add"].items():
                scores[cluster] += bonus

    return scores


def _apply_context_adjustments(
    normalized_symptoms: List[str],
    raw_text: str,
    scores: Dict[str, int]
) -> Dict[str, int]:
    text = raw_text.lower()

    # Боль внизу живота у женщин
    if "боль внизу живота" in normalized_symptoms:
        scores["gyn"] += 1

    # Кашель + мокрота усиливает respiratory
    if "кашель" in normalized_symptoms and "мокрота" in normalized_symptoms:
        scores["respiratory"] += 2

    # Температура + насморк + боль в горле
    if (
        "температура" in normalized_symptoms and
        "насморк" in normalized_symptoms and
        "боль в горле" in normalized_symptoms
    ):
        scores["ent"] += 1
        scores["respiratory"] += 1

    # Боль в груди + давление в груди
    if "боль в груди" in normalized_symptoms and "давление в груди" in normalized_symptoms:
        scores["cardio"] += 2

    # Тошнота + головная боль
    if "тошнота" in normalized_symptoms and "головная боль" in normalized_symptoms:
        scores["neuro"] += 1

    # Рана/кровотечение/ампутация - усиливаем trauma
    if any(s in normalized_symptoms for s in ["рана", "открытая рана", "кровотечение", "ампутация", "перелом"]):
        scores["trauma"] += 1

    # Если текст содержит "после еды", усиливаем gastro
    if "после еды" in text:
        scores["gastro"] += 2

    return scores


def _detect_red_flags(normalized_symptoms: List[str]) -> List[str]:
    return [symptom for symptom in normalized_symptoms if symptom in RED_FLAG_SYMPTOMS]


def _rank_clusters(scores: Dict[str, int]) -> List[Tuple[str, int]]:
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return ranked


def _determine_confidence(ranked_clusters: List[Tuple[str, int]]) -> str:
    if not ranked_clusters:
        return "low"

    top1_score = ranked_clusters[0][1]
    top2_score = ranked_clusters[1][1] if len(ranked_clusters) > 1 else 0

    diff = top1_score - top2_score

    if top1_score <= 0:
        return "low"

    if diff >= 3:
        return "high"
    if diff >= 1:
        return "medium"

    return "low"


# ---------------------------------------------------------
# 6. Главная функция
# ---------------------------------------------------------

def parse_symptoms(raw_text: str) -> Dict[str, Any]:
    """
    Главная функция парсинга симптомов.

    Возвращает структуру:
    {
        "raw_text": "...",
        "normalized_symptoms": [...],
        "body_areas": [...],
        "duration": "...",
        "cluster_scores": {...},
        "primary_cluster": "...",
        "secondary_clusters": [...],
        "confidence": "low|medium|high",
        "red_flags": [...]
    }
    """
    cleaned_text = _clean_text(raw_text)
    chunks = _split_into_chunks(cleaned_text)

    normalized_chunks = [_normalize_chunk(chunk) for chunk in chunks]
    normalized_symptoms = _deduplicate_preserve_order(normalized_chunks)

    body_areas = _detect_body_areas(normalized_symptoms, cleaned_text)
    duration = _extract_duration(cleaned_text)

    scores = _apply_symptom_scores(normalized_symptoms)
    scores = _apply_combination_bonuses(normalized_symptoms, scores)
    scores = _apply_context_adjustments(normalized_symptoms, cleaned_text, scores)

    ranked_clusters = _rank_clusters(scores)

    primary_cluster = ranked_clusters[0][0] if ranked_clusters and ranked_clusters[0][1] > 0 else "general"

    secondary_clusters = [
        cluster
        for cluster, score in ranked_clusters[1:3]
        if score > 0
    ]

    confidence = _determine_confidence(ranked_clusters)
    red_flags = _detect_red_flags(normalized_symptoms)

    return {
        "raw_text": raw_text,
        "normalized_symptoms": normalized_symptoms,
        "body_areas": body_areas,
        "duration": duration,
        "cluster_scores": scores,
        "primary_cluster": primary_cluster,
        "secondary_clusters": secondary_clusters,
        "confidence": confidence,
        "red_flags": red_flags,
    }
