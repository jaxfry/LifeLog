import base64
import io
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from PIL import Image
from pypdf import PdfReader
from litellm import acompletion
from app.core.logger import get_logger

logger = get_logger(__name__)

from app.core.ai_config import completion_with_fallback

async def analyze_file_content(
    file_path: Path, 
    mime_type: str, 
    original_filename: str,
    tags: List[str] = [],
    category: Optional[str] = None
) -> Dict[str, Any]:
    """
    Analyzes a file using Gemini Flash (via Hack Club or Google) to extract structured metadata.
    Handles Images and PDFs.
    """
    if not file_path.exists():
        logger.error(f"File not found: {file_path}")
        return {}

    content_parts = []
    
    # Prepare the prompt
    system_prompt = """
    You are an advanced file analysis AI. Your goal is to extract structured metadata from the provided file.
    
    Return a valid JSON object with the following fields:
    - "description": A detailed visual or content description of the file.
    - "summary": A concise 1-2 sentence summary.
    - "keywords": A list of relevant keywords/tags.
    - "entities": A list of named entities (people, organizations, locations, dates) found in the content.
    - "categories": A list of suggested categories for this file.
    
    Do not include markdown formatting (like ```json). Just return the raw JSON.
    """
    
    user_message = f"Analyze this file.\nFilename: {original_filename}\n"
    if category:
        user_message += f"Category: {category}\n"
    if tags:
        user_message += f"Tags: {', '.join(tags)}\n"

    try:
        if mime_type.startswith("image/"):
            # Process Image
            image_data = _process_image(file_path)
            if image_data:
                content_parts.append({
                    "type": "text",
                    "text": user_message
                })
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{image_data}"}
                })
            else:
                return {}
                
        elif mime_type == "application/pdf":
            # Process PDF
            pdf_text = _extract_pdf_text(file_path)
            if pdf_text:
                # Truncate if too long
                if len(pdf_text) > 100000:
                    pdf_text = pdf_text[:100000] + "...(truncated)"
                
                content_parts.append({
                    "type": "text",
                    "text": f"{user_message}\n\nFile Content:\n{pdf_text}"
                })
            else:
                return {}
        
        else:
            # Text or other supported formats
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    text_content = f.read()
                    if len(text_content) > 100000:
                        text_content = text_content[:100000] + "...(truncated)"
                    
                    content_parts.append({
                        "type": "text",
                        "text": f"{user_message}\n\nFile Content:\n{text_content}"
                    })
            except Exception as e:
                logger.warning(f"Could not read file as text: {e}")
                return {}

        if not content_parts:
            return {}

        # Call AI with fallback
        response = await completion_with_fallback(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content_parts}
            ],
            response_format={"type": "json_object"} 
        )
        
        content = response.choices[0].message.content
        
        # Parse JSON
        try:
            # Clean up potential markdown code blocks
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
            
            data = json.loads(content.strip())
            
            # Add versioning
            data["version"] = "1.0"
            return data
            
        except json.JSONDecodeError:
            logger.error(f"Failed to parse JSON response: {content}")
            return {}

    except Exception as e:
        # Check for rate limit errors
        error_str = str(e).lower()
        if "rate limit" in error_str or "429" in error_str:
            logger.warning(f"Rate limit hit for file {file_path}: {e}")
            raise e  # Re-raise to allow retry by worker
            
        logger.error(f"Error analyzing file {file_path}: {e}")
        return {}

def _process_image(file_path: Path) -> Optional[str]:
    """
    Resizes image to max 2048px dimension and returns base64 string.
    """
    try:
        with Image.open(file_path) as img:
            # Convert to RGB if needed (e.g. RGBA to JPEG)
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
                
            # Resize if too large
            max_size = 2048
            if max(img.size) > max_size:
                img.thumbnail((max_size, max_size))
            
            # Save to buffer
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=85)
            return base64.b64encode(buffer.getvalue()).decode('utf-8')
    except Exception as e:
        logger.error(f"Error processing image {file_path}: {e}")
        return None

def _extract_pdf_text(file_path: Path) -> Optional[str]:
    """
    Extracts text from a PDF file.
    """
    try:
        reader = PdfReader(file_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text
    except Exception as e:
        logger.error(f"Error extracting PDF text {file_path}: {e}")
        return None
