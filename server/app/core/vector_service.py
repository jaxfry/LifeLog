import os
from typing import List
from litellm import aembedding
from app.core.logger import get_logger

logger = get_logger(__name__)

# Using Gemini's embedding model which has 768 dimensions (configured via dimensions param)
EMBEDDING_MODEL = "gemini/gemini-embedding-001"
EMBEDDING_VERSION = "1.4"  # Increment this when changing models

def get_embedding_model_info():
    """Returns current embedding model and version."""
    return {
        "model": EMBEDDING_MODEL,
        "version": EMBEDDING_VERSION
    }

async def generate_embedding(text: str) -> List[float]:
    """
    Generates a vector embedding for the given text using Gemini.
    """
    try:
        if not text or not text.strip():
            return []
            
        # Ensure API key is present (it should be set in environment by the caller or globally)
        if not os.environ.get("GEMINI_API_KEY"):
             logger.warning("GEMINI_API_KEY not set. Cannot generate embedding.")
             return []

        response = await aembedding(
            model=EMBEDDING_MODEL,
            input=[text],
            dimensions=768
        )
        return response.data[0]["embedding"]
    except Exception as e:
        logger.error(f"Error generating embedding: {e}")
        return []
