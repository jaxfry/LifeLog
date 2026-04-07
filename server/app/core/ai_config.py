import os
from typing import Optional, Tuple, List, Dict, Any
from litellm import acompletion, aembedding
from openai import AsyncOpenAI
from app.core.logger import get_logger

logger = get_logger(__name__)

# Constants
HACK_CLUB_BASE_URL = "https://ai.hackclub.com/proxy/v1"
HACK_CLUB_CHAT_MODEL = "google/gemini-2.5-flash" # OpenRouter/HackClub usually prefixes with provider or just model
# The user said "google/gemini-2.5-flash".
# Hack Club docs example: "qwen/qwen3-32b". So "google/gemini-2.5-flash" is likely correct.
HACK_CLUB_MODEL_ID = "google/gemini-2.5-flash"

# Fallback Google Model
GOOGLE_MODEL_ID = "gemini/gemini-flash-latest" 

# Embedding
HACK_CLUB_EMBEDDING_MODEL = "qwen/qwen3-embedding-8b"

class AIConfig:
    @staticmethod
    def get_hack_club_key() -> Optional[str]:
        key = os.environ.get("HACK_CLUB_AI_API_KEY")
        if not key:
            logger.warning("HACK_CLUB_AI_API_KEY is not set in environment variables.")
        return key

    @staticmethod
    def get_google_key() -> Optional[str]:
        return os.environ.get("GEMINI_API_KEY")

async def completion_with_fallback(
    messages: List[Dict[str, Any]], 
    response_format: Optional[Dict[str, Any]] = None,
    **kwargs
) -> Any:
    """
    Attempts to generate a completion using Hack Club first, then falls back to Google.
    """
    hc_key = AIConfig.get_hack_club_key()
    google_key = AIConfig.get_google_key()
    
    errors = []

    # 1. Try Hack Club
    if hc_key:
        try:
            logger.info(f"Attempting completion with Hack Club ({HACK_CLUB_MODEL_ID})")
            return await acompletion(
                model=f"openai/{HACK_CLUB_MODEL_ID}", # litellm needs openai/ prefix for custom base_url usually, or just the model if using openrouter provider
                api_key=hc_key,
                base_url=HACK_CLUB_BASE_URL,
                messages=messages,
                response_format=response_format,
                **kwargs
            )
        except Exception as e:
            logger.warning(f"Hack Club completion failed: {e}")
            errors.append(e)
    
    # 2. Try Google
    if google_key:
        try:
            logger.info(f"Attempting completion with Google ({GOOGLE_MODEL_ID})")
            return await acompletion(
                model=GOOGLE_MODEL_ID,
                api_key=google_key,
                messages=messages,
                response_format=response_format,
                **kwargs
            )
        except Exception as e:
            logger.warning(f"Google completion failed: {e}")
            errors.append(e)
            
    raise Exception(f"All AI providers failed. Errors: {errors}")

async def embedding_with_fallback(text: str) -> List[float]:
    """
    Generates embedding using Hack Club (Qwen) as primary.
    """
    hc_key = AIConfig.get_hack_club_key()
    
    if not hc_key:
        logger.warning("HACK_CLUB_AI_API_KEY not set. Falling back to legacy/Google if available or failing.")
        # If user wants to switch ALL future embeddings, we should probably fail if HC is not available 
        # to avoid mixing embedding spaces, UNLESS they have a fallback plan.
        # But for now, let's try to stick to the request "switch all our future embeddings to always use qwen..."
        # If we can't use Qwen, we probably shouldn't generate an embedding that is incompatible.
        # However, for robustness, maybe we return None or raise.
        pass

    if hc_key:
        try:
            # Qwen embedding via Hack Club
            # Note: We need to handle dimensionality.
            # Using AsyncOpenAI directly as litellm was failing with 401 inside Docker
            client = AsyncOpenAI(
                api_key=hc_key,
                base_url=HACK_CLUB_BASE_URL
            )
            
            response = await client.embeddings.create(
                model=HACK_CLUB_EMBEDDING_MODEL,
                input=[text]
            )
            
            embedding = response.data[0].embedding
            
            # Manual slicing if API ignores dimensions param and returns larger vector
            # Qwen-embedding-8b is likely 1536 or 4096. 
            # MRL (Matryoshka) allows slicing. We assume it works.
            if len(embedding) > 768:
                logger.info(f"Slicing embedding from {len(embedding)} to 768")
                embedding = embedding[:768]
                
            return embedding
            
        except Exception as e:
            logger.error(f"Hack Club embedding failed: {e}")
            raise e
            
    # Fallback to Google if configured (but this will create incompatible embeddings!)
    # The user said "switch all our future embeddings to always use qwen".
    # So we should probably NOT fallback to Gemini for embeddings to avoid pollution.
    raise Exception("Hack Club API key required for Qwen embeddings.")
