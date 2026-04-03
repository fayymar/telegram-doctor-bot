import os
import httpx
from database.connection import supabase_client
from utils.logger import setup_logger

logger = setup_logger(__name__)

HF_API_URL = "https://router.huggingface.co/hf-inference/models/sentence-transformers/all-MiniLM-L6-v2/pipeline/feature-extraction"
HF_TOKEN = os.getenv("HF_TOKEN", "")


def get_embedding(text: str) -> list:
    headers = {
        "Authorization": f"Bearer {HF_TOKEN}",
        "Content-Type": "application/json"
    }
    response = httpx.post(
        HF_API_URL,
        headers=headers,
        json={"inputs": text, "normalize": True},
        timeout=30.0
    )
    if response.status_code == 200:
        result = response.json()
        if isinstance(result, list) and isinstance(result[0], list):
            return result[0]
        return result
    return []


def find_relevant_diseases(symptoms_text: str, limit: int = 5) -> str:
    """
    Находит релевантные болезни по симптомам через pgvector.
    Возвращает строку для вставки в промпт.
    """
    try:
        embedding = get_embedding(symptoms_text)
        if not embedding:
            return ""

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
