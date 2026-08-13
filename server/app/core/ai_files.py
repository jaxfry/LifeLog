import base64
import io
import json
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import get_logger
from app.services.ai import call_llm

logger = get_logger(__name__)

try:
    from PIL import Image

    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

try:
    from pypdf import PdfReader

    _HAS_PYPDF = True
except ImportError:
    _HAS_PYPDF = False


async def analyze_file_content(
    file_path: Path,
    mime_type: str,
    original_filename: str,
    tags: list[str] = [],
    category: str | None = None,
    db_session: AsyncSession | None = None,
) -> dict[str, Any]:
    """
    Analyzes a file using the configured LLM provider to extract structured metadata.
    Handles Images and PDFs.
    """
    if not file_path.exists():
        logger.error("File not found: %s", file_path)
        return {}

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

    content_parts: list[dict[str, Any]] = []

    if mime_type.startswith("image/"):
        image_data = _process_image(file_path)
        if not image_data:
            return {}
        content_parts.append({"type": "text", "text": user_message})
        content_parts.append(
            {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_data}"}}
        )

    elif mime_type == "application/pdf":
        pdf_text = _extract_pdf_text(file_path)
        if not pdf_text:
            return {}
        if len(pdf_text) > 100000:
            pdf_text = pdf_text[:100000] + "...(truncated)"
        content_parts.append({"type": "text", "text": f"{user_message}\n\nFile Content:\n{pdf_text}"})

    else:
        try:
            with open(file_path, encoding="utf-8", errors="ignore") as f:
                text_content = f.read()
                if len(text_content) > 100000:
                    text_content = text_content[:100000] + "...(truncated)"
                content_parts.append(
                    {"type": "text", "text": f"{user_message}\n\nFile Content:\n{text_content}"}
                )
        except Exception as e:
            logger.warning("Could not read file as text: %s", e)
            return {}

    if not content_parts:
        return {}

    try:
        content = await call_llm(
            db_session=db_session,
            system_prompt=system_prompt,
            user_prompt=content_parts,
        )
    except RuntimeError as e:
        error_str = str(e).lower()
        if "rate limit" in error_str or "429" in error_str:
            logger.warning("Rate limit hit for file %s: %s", file_path, e)
            raise e
        logger.error("Error analyzing file %s: %s", file_path, e)
        return {}

    try:
        content = content.removeprefix("```json")
        content = content.removesuffix("```")

        data = json.loads(content.strip())
        data["version"] = "1.0"
        return data
    except json.JSONDecodeError:
        logger.error("Failed to parse JSON response: %s", content)
        return {}


def _process_image(file_path: Path) -> str | None:
    """
    Resizes image to max 2048px dimension and returns base64 string.
    """
    if not _HAS_PIL:
        logger.warning("PIL not installed, cannot process image")
        return None
    try:
        with Image.open(file_path) as img:
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            max_size = 2048
            if max(img.size) > max_size:
                img.thumbnail((max_size, max_size))

            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=85)
            return base64.b64encode(buffer.getvalue()).decode("utf-8")
    except Exception as e:
        logger.error("Error processing image %s: %s", file_path, e)
        return None


def _extract_pdf_text(file_path: Path) -> str | None:
    """
    Extracts text from a PDF file.
    """
    if not _HAS_PYPDF:
        logger.warning("pypdf not installed, cannot extract PDF text")
        return None
    try:
        reader = PdfReader(file_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text
    except Exception as e:
        logger.error("Error extracting PDF text %s: %s", file_path, e)
        return None
