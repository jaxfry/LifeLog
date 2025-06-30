# central_server/processing_service/logic/embeddings.py
"""Embedding service for project names and descriptions."""
from typing import Optional, List, Any
import logging
import hashlib

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

# Import settings from the new location
from central_server.processing_service.logic.settings import settings as service_settings


class EmbeddingService:
    """Service for generating embeddings for project names and descriptions."""
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self.model: Optional[Any] = None
        # Use target_dimensions from service_settings
        self.target_dimensions = service_settings.PROJECT_EMBEDDING_SIZE
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
        
        current_length = len(embedding)
        if current_length == self.target_dimensions:
            return embedding.tolist()
        
        if current_length > self.target_dimensions:
            # Truncate
            resized = embedding[:self.target_dimensions]
        else:
            # Pad with zeros
            resized = np.pad(embedding, (0, self.target_dimensions - current_length), 'constant')
        
        # Normalize the resized embedding
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
        hash_obj = hashlib.md5(project_name.lower().encode())
        hash_bytes = hash_obj.digest()
        embedding_values = []
        for i in range(self.target_dimensions):
            # Cycle through hash_bytes if target_dimensions is larger
            byte_val = hash_bytes[i % len(hash_bytes)]
            # Normalize byte to [-1, 1] range
            embedding_values.append((byte_val / 127.5) - 1.0)
        logger.debug(f"Generated fallback embedding for project '{project_name}'")
        return embedding_values

    def compute_similarity(self, embedding1: List[float], embedding2: List[float]) -> float:
        if np is None:
            logger.error("Numpy is required for similarity computation.")
            return 0.0
        
        if not embedding1 or not embedding2:
            logger.warning("Cannot compute similarity with empty embeddings.")
            return 0.0
        
        if len(embedding1) != self.target_dimensions or len(embedding2) != self.target_dimensions:
            logger.warning(f"Embeddings have mismatched dimensions for similarity computation. Expected {self.target_dimensions}.")
            # Fallback or error, for now, return 0
            return 0.0

        try:
            vec1 = np.array(embedding1)
            vec2 = np.array(embedding2)
            
            dot_product = np.dot(vec1, vec2)
            norm1 = np.linalg.norm(vec1)
            norm2 = np.linalg.norm(vec2)
            
            if norm1 == 0 or norm2 == 0:
                return 0.0 # Avoid division by zero
                
            similarity = dot_product / (norm1 * norm2)
            return float(similarity)
        except Exception as e:
            logger.error(f"Failed to compute similarity: {e}")
            return 0.0

# Global instance - initialize once per application/service
_embedding_service_instance: Optional[EmbeddingService] = None

def get_embedding_service() -> EmbeddingService:
    """
    Returns a singleton instance of the EmbeddingService.

    Returns:
        An instance of the EmbeddingService.
    """
    global _embedding_service_instance
    if _embedding_service_instance is None:
        _embedding_service_instance = EmbeddingService()
    return _embedding_service_instance

if __name__ == "__main__":
    # Example Usage (for testing this module directly)
    logging.basicConfig(level=logging.INFO)
    service = get_embedding_service()
    
    # Test with service_settings
    print(f"Embedding dimensions from settings: {service_settings.PROJECT_EMBEDDING_SIZE}")

    if service.model:
        emb1 = service.generate_project_embedding("LifeLog Development")
        emb2 = service.generate_project_embedding("LifeLog Core Dev")
        emb3 = service.generate_project_embedding("Recipe App Frontend")

        print(f"Embedding for 'LifeLog Development' (first 5 dims): {emb1[:5]}")
        print(f"Similarity (LifeLog Dev vs LifeLog Core Dev): {service.compute_similarity(emb1, emb2)}")
        print(f"Similarity (LifeLog Dev vs Recipe App): {service.compute_similarity(emb1, emb3)}")
    else:
        print("Embedding model not loaded, cannot run full example.")

    fallback_emb = service._generate_fallback_embedding("Test Project")
    print(f"Fallback embedding for 'Test Project' (first 5 dims): {fallback_emb[:5]}")
