"""Embedding service for project names and descriptions."""

import logging
from typing import Optional, List, Any

try:
    import numpy as np
except ImportError:
    np = None

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None
    # The model will not be available if the package is missing

logger = logging.getLogger(__name__)

class EmbeddingService:
    """Service for generating embeddings for project names and descriptions."""
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self.model: Optional[Any] = None
        self.target_dimensions = 128  # Must match our database schema
        self._initialize_model()

    def _initialize_model(self):
        try:
            if SentenceTransformer is not None:
                self.model = SentenceTransformer(self.model_name)
                logger.info(f"Loaded embedding model: {self.model_name}")
            else:
                logger.warning("SentenceTransformer not available. Embedding model will not be loaded.")
                self.model = None
        except Exception as e:
            logger.error(f"Failed to load embedding model {self.model_name}: {e}")
            self.model = None

    def _resize_embedding(self, embedding) -> List[float]:
        if np is None:
            raise RuntimeError("Numpy is required for embedding resizing.")
        if len(embedding) == self.target_dimensions:
            return embedding.tolist()
        if len(embedding) > self.target_dimensions:
            resized = embedding[:self.target_dimensions]
        else:
            resized = np.pad(embedding, (0, self.target_dimensions - len(embedding)), 'constant')
        norm = np.linalg.norm(resized)
        if norm > 0:
            resized = resized / norm
        return resized.tolist()

    def generate_project_embedding(self, project_name: str, description: Optional[str] = None) -> List[float]:
        if not self.model or np is None or not hasattr(self.model, "encode"):
            logger.warning("Embedding model or numpy not available, generating fallback embedding")
            return self._generate_fallback_embedding(project_name)
        text_to_embed = project_name
        if description:
            text_to_embed = f"{project_name}: {description}"
        try:
            embedding = self.model.encode(text_to_embed, convert_to_numpy=True)
            resized_embedding = self._resize_embedding(embedding)
            logger.debug(f"Generated embedding for project '{project_name}' with {len(resized_embedding)} dimensions")
            return resized_embedding
        except Exception as e:
            logger.error(f"Failed to generate embedding for project '{project_name}': {e}")
            return self._generate_fallback_embedding(project_name)

    def _generate_fallback_embedding(self, project_name: str) -> List[float]:
        import hashlib
        hash_obj = hashlib.md5(project_name.lower().encode())
        hash_bytes = hash_obj.digest()
        embedding = []
        for i in range(self.target_dimensions):
            byte_val = hash_bytes[i % len(hash_bytes)]
            embedding.append((byte_val / 127.5) - 1.0)
        logger.debug(f"Generated fallback embedding for project '{project_name}'")
        return embedding

    def compute_similarity(self, embedding1: List[float], embedding2: List[float]) -> float:
        if np is None:
            logger.error("Numpy is required for similarity computation.")
            return 0.0
        try:
            vec1 = np.array(embedding1)
            vec2 = np.array(embedding2)
            dot_product = np.dot(vec1, vec2)
            norm1 = np.linalg.norm(vec1)
            norm2 = np.linalg.norm(vec2)
            if norm1 == 0 or norm2 == 0:
                return 0.0
            similarity = dot_product / (norm1 * norm2)
            return float(similarity)
        except Exception as e:
            logger.error(f"Failed to compute similarity: {e}")
            return 0.0

# Global instance - initialize once per application
_embedding_service: Optional[EmbeddingService] = None

def get_embedding_service() -> EmbeddingService:
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
