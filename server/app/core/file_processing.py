import io
from typing import Dict, Any, Optional
from pathlib import Path
from PIL import Image, ExifTags
from pypdf import PdfReader
from app.core.logger import get_logger

logger = get_logger(__name__)

def _sanitize_metadata_value(value: Any) -> Any:
    """
    Recursively sanitizes metadata values to ensure they are JSON serializable.
    Handles PIL IFDRational, bytes, and other non-standard types.
    """
    if isinstance(value, str):
        return value.replace('\x00', '').strip()
    if isinstance(value, (int, float, bool, type(None))):
        return value
    if isinstance(value, bytes):
        try:
            return value.decode('utf-8', errors='replace').strip('\x00')
        except:
            return str(value)
    if isinstance(value, (list, tuple)):
        return [_sanitize_metadata_value(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _sanitize_metadata_value(v) for k, v in value.items()}
    
    # Handle PIL IFDRational and similar types
    if hasattr(value, 'numerator') and hasattr(value, 'denominator'):
        try:
            return float(value)
        except:
            return str(value)
            
    # Fallback to string representation for any other objects
    return str(value)

def extract_image_metadata(file_path: Path) -> Dict[str, Any]:
    """
    Extracts EXIF and other metadata from an image file.
    """
    metadata = {}
    try:
        with Image.open(file_path) as img:
            metadata["width"] = img.width
            metadata["height"] = img.height
            metadata["format"] = img.format
            metadata["mode"] = img.mode
            
            # Extract EXIF
            exif_data = img._getexif()
            if exif_data:
                for tag_id, value in exif_data.items():
                    tag_name = ExifTags.TAGS.get(tag_id, tag_id)
                    
                    sanitized_value = _sanitize_metadata_value(value)
                            
                    # Skip long binary data or strings (like maker notes)
                    if isinstance(sanitized_value, str) and len(sanitized_value) > 500:
                        continue
                        
                    metadata[str(tag_name)] = sanitized_value
                    
            # Normalize common fields
            if "DateTimeOriginal" in metadata:
                metadata["date_taken"] = metadata["DateTimeOriginal"]
            elif "DateTime" in metadata:
                metadata["date_taken"] = metadata["DateTime"]
                
            if "Make" in metadata:
                metadata["camera_make"] = metadata["Make"]
            if "Model" in metadata:
                metadata["camera_model"] = metadata["Model"]
                
    except Exception as e:
        logger.error(f"Error extracting image metadata from {file_path}: {e}")
        
    return metadata

def extract_pdf_metadata(file_path: Path) -> Dict[str, Any]:
    """
    Extracts metadata from a PDF file.
    """
    metadata = {}
    try:
        reader = PdfReader(str(file_path))
        metadata["page_count"] = len(reader.pages)
        
        if reader.metadata:
            for key, value in reader.metadata.items():
                # Strip the leading slash from PDF keys (e.g., /Title -> Title)
                clean_key = key.lstrip('/') if isinstance(key, str) else str(key)
                
                # Handle potential PyPDF2 objects
                if hasattr(value, "getObject"):
                    value = value.getObject()
                    
                metadata[clean_key] = _sanitize_metadata_value(value)
                
    except Exception as e:
        logger.error(f"Error extracting PDF metadata from {file_path}: {e}")
        
    return metadata

async def extract_metadata(file_path: Path, mime_type: str) -> Dict[str, Any]:
    """
    Router function to extract metadata based on file type.
    """
    if not file_path.exists():
        return {}
        
    if mime_type.startswith("image/"):
        return extract_image_metadata(file_path)
    elif mime_type == "application/pdf":
        return extract_pdf_metadata(file_path)
        
    return {}
