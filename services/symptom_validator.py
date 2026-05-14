"""
Embedding-based symptom validator.
Uses paraphrase-multilingual-MiniLM-L12-v2 for Russian/Uzbek support.
Loaded once at bot startup, stays in memory.
"""
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_model = None
_symptom_vecs = None
_not_symptom_vecs = None
_initialized = False

EXAMPLES_PATH = Path(__file__).parent / "symptom_examples.json"
THRESHOLD = 0.35  # min similarity to symptom cluster
MARGIN = 0.05     # must be this much closer to symptoms than non-symptoms


def _load_model():
    """Lazy-load the model on first use."""
    global _model, _symptom_vecs, _not_symptom_vecs, _initialized
    if _initialized:
        return _model is not None

    try:
        from sentence_transformers import SentenceTransformer
        import numpy as np

        logger.info("Loading symptom embedding model...")
        _model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

        with open(EXAMPLES_PATH, encoding="utf-8") as f:
            examples = json.load(f)

        _symptom_vecs = _model.encode(
            examples["symptoms"], normalize_embeddings=True, show_progress_bar=False
        )
        _not_symptom_vecs = _model.encode(
            examples["not_symptoms"], normalize_embeddings=True, show_progress_bar=False
        )
        _initialized = True
        logger.info(
            f"Symptom validator ready: {len(examples['symptoms'])} symptoms, "
            f"{len(examples['not_symptoms'])} non-symptoms"
        )
        return True

    except ImportError:
        logger.warning("sentence-transformers not installed, symptom validator disabled")
        _initialized = True
        return False
    except Exception as e:
        logger.error(f"Symptom validator init failed: {e}")
        _initialized = True
        return False


def is_medical_symptom(text: str) -> tuple[bool, float]:
    """
    Returns (is_medical, confidence_score).
    Falls back to (True, 0.0) if model unavailable — safe default.
    """
    if not _load_model() or _model is None:
        return True, 0.0

    try:
        import numpy as np

        vec = _model.encode([text.strip()], normalize_embeddings=True)

        # Cosine similarity (vectors already normalized → dot product)
        sim_medical = float(np.dot(vec, _symptom_vecs.T).max())
        sim_not = float(np.dot(vec, _not_symptom_vecs.T).max())

        is_medical = (
            sim_medical >= THRESHOLD and
            sim_medical > sim_not + MARGIN
        )

        logger.debug(
            f"Symptom check: '{text[:50]}' "
            f"sim_medical={sim_medical:.3f} sim_not={sim_not:.3f} → {'YES' if is_medical else 'NO'}"
        )

        return is_medical, sim_medical

    except Exception as e:
        logger.error(f"Symptom check error: {e}")
        return True, 0.0  # safe default
