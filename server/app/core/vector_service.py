import os
from typing import List, Optional
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

async def generate_embedding(text: str, api_key: Optional[str] = None) -> List[float]:
    """
    Generates a vector embedding for the given text using Gemini.
    """
    try:
        if not text or not text.strip():
            return []
            
        # Ensure API key is present (it should be set in environment by the caller or globally)
        if not api_key and not os.environ.get("GEMINI_API_KEY"):
             logger.warning("GEMINI_API_KEY not set. Cannot generate embedding.")
             return []
             
        kwargs = {
            "model": EMBEDDING_MODEL,
            "input": [text],
        }
        
        if api_key:
            kwargs["api_key"] = api_key
            
        # Only pass dimensions if the model supports it (gemini-embedding-001 does not support it via litellm in some versions)
        # But since we are using gemini-embedding-001 which is fixed 768, we can omit it or keep it if we upgrade.
        # For safety, we omit it for now as 001 is fixed.
        # kwargs["dimensions"] = 768
        
        # Update: It seems we are getting 3072 dimensions, so we MUST request 768 if supported, 
        # or we are using a model that defaults to 3072.
        # Let's try forcing 768.
        kwargs["dimensions"] = 768

        response = await aembedding(**kwargs)
        return response.data[0]["embedding"]
    except Exception as e:
        logger.error(f"Error generating embedding: {e}")
        return []
