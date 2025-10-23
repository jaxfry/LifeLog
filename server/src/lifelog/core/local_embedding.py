from typing import List
from sentence_transformers import SentenceTransformer
from .config import settings

class LocalEmbeddingProvider:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model = SentenceTransformer(model_name)
        self.target_dim = getattr(settings, "DEFAULT_EMBEDDING_DIM", 1536)

    def _pad_or_truncate(self, vec: List[float]) -> List[float]:
        # Adjust vector to match configured DB dimension
        d = len(vec)
        if d == self.target_dim:
            return vec
        if d > self.target_dim:
            return vec[: self.target_dim]
        # pad with zeros
        return vec + [0.0] * (self.target_dim - d)

    def embed(self, texts: List[str]) -> List[List[float]]:
        arr = self.model.encode(texts, normalize_embeddings=False)
        # Convert to python lists and pad/truncate to target_dim
        vectors: List[List[float]] = []
        for row in arr.tolist():
            vectors.append(self._pad_or_truncate(row))
        return vectors

# Example usage:
# provider = LocalEmbeddingProvider()
# embeddings = provider.embed(["Hello world", "LifeLog modular AI"])
