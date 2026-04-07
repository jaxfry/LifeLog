import os
from typing import List, Optional
from app.core.logger import get_logger
from app.core.ai_config import embedding_with_fallback, HACK_CLUB_EMBEDDING_MODEL

logger = get_logger(__name__)

# Using Hack Club's Qwen embedding model
EMBEDDING_MODEL = HACK_CLUB_EMBEDDING_MODEL
EMBEDDING_VERSION = "2.0"  # Increment this when changing models

def get_embedding_model_info():
    """Returns current embedding model and version."""
    return {
        "model": EMBEDDING_MODEL,
        "version": EMBEDDING_VERSION
    }

async def generate_embedding(text: str, api_key: Optional[str] = None) -> List[float]:
    """
    Generates a vector embedding for the given text using Hack Club (Qwen).
    """
    try:
        if not text or not text.strip():
            return []
            
        return await embedding_with_fallback(text)

    except Exception as e:
        logger.error(f"Error generating embedding: {e}")
        return []
