from sentence_transformers import SentenceTransformer
from database.connection import supabase_client
from utils.logger import setup_logger

logger = setup_logger(__name__)

_model = None


def get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def find_relevant_diseases(symptoms_text: str, limit: int = 5) -> str:
    """
    Находит релевантные болезни по симптомам через pgvector.
    Возвращает строку для вставки в промпт.
    """
    try:
        model = get_model()
        embedding = model.encode(symptoms_text).tolist()

        result = supabase_client.rpc(
            "match_medical_embeddings",
            {
                "query_embedding": embedding,
                "match_threshold": 0.3,
                "match_count": limit
            }
        ).execute()

        if not result.data:
            return ""

        diseases = result.data
        lines = ["Возможные диагнозы по симптомам:"]
        for d in diseases:
            line = f"- {d['disease_name']} ({d['code']})"
            if d.get('specialist'):
                line += f" → {d['specialist']}"
            lines.append(line)

        return "\n".join(lines)

    except Exception as e:
        logger.error(f"RAG search failed: {e}")
        return ""
