"""
Local embedding provider using sentence-transformers.

Fixes and improvements:
- Cache model instances by name to avoid reloading on each construction.
- Optional normalization (defaults to True for cosine/L2 compatibility).
- Batch size configurable via settings when available.
- Gracefully handle empty inputs.
- Warn once when padding/truncating to match configured DB dimension.
"""

from typing import List, Optional, Dict
import logging
from sentence_transformers import SentenceTransformer
from .config import settings

logger = logging.getLogger(__name__)

# Simple in-process cache to avoid repeatedly loading the same model
_MODEL_CACHE: Dict[str, SentenceTransformer] = {}

class LocalEmbeddingProvider:
    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        *,
    normalize: Optional[bool] = None,
    ):
        # Reuse a cached model if available
        if model_name in _MODEL_CACHE:
            self.model = _MODEL_CACHE[model_name]
        else:
            self.model = SentenceTransformer(model_name)
            _MODEL_CACHE[model_name] = self.model

        # Target dimension for DB vectors (pgvector expects fixed length)
        self.target_dim: int = int(getattr(settings, "DEFAULT_EMBEDDING_DIM", 1536))

        # Whether to return normalized embeddings; default to True for better L2/cosine behavior
        if normalize is None:
            self.normalize = bool(getattr(settings, "DEFAULT_EMBEDDING_NORMALIZE", True))
        else:
            self.normalize = normalize

        # Batch size hint (optional)
        self.batch_size: int = int(getattr(settings, "DEFAULT_EMBEDDING_BATCH_SIZE", 32))

        # Track whether we've already warned about dimension mismatch to avoid log spam
        self._dim_warned: bool = False

    def _pad_or_truncate(self, vec: List[float]) -> List[float]:
        """Adjust a vector to match the configured DB dimension.

        - Truncates if the produced vector is larger than target_dim (information loss!)
        - Pads with zeros if smaller than target_dim
        Logs a one-time warning when a mismatch is detected.
        """
        d = len(vec)
        if d == self.target_dim:
            return vec
        if not self._dim_warned:
            logger.warning(
                "Embedding dimension %s differs from target %s; output will be %s.",
                d,
                self.target_dim,
                "truncated" if d > self.target_dim else "zero-padded",
            )
            self._dim_warned = True
        if d > self.target_dim:
            return vec[: self.target_dim]
        # pad with zeros
        return vec + [0.0] * (self.target_dim - d)

    def embed(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of texts into fixed-dimension vectors.

        Returns a list of Python lists (float), each of length target_dim.
        """
        if not texts:
            return []

        # sentence-transformers handles internal batching, but batch_size can help for large inputs
        arr = self.model.encode(
            texts,
            normalize_embeddings=self.normalize,
            batch_size=self.batch_size,
            convert_to_numpy=True,
        )
        # Convert to python lists and pad/truncate to target_dim
        vectors: List[List[float]] = []
        for row in arr.tolist():
            vectors.append(self._pad_or_truncate(row))
        return vectors

# Example usage:
# provider = LocalEmbeddingProvider()
# embeddings = provider.embed(["Hello world", "LifeLog modular AI"])
