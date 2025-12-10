import io
from typing import Dict, Any, Optional
from pathlib import Path
from PIL import Image, ExifTags
from pypdf import PdfReader
from app.core.logger import get_logger

logger = get_logger(__name__)

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
                    
                    # Decode bytes to string if needed
                    if isinstance(value, bytes):
                        try:
                            value = value.decode()
                        except:
                            value = str(value)
                            
                    # Skip long binary data (like maker notes)
                    if isinstance(value, str) and len(value) > 500:
                        continue
                        
                    metadata[str(tag_name)] = value
                    
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
                    
                metadata[clean_key] = str(value)
                
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
