from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from uuid import UUID, uuid4
from sqlmodel import SQLModel, Field, Column
from sqlalchemy.dialects.postgresql import JSONB
from pgvector.sqlalchemy import Vector
import numpy as np
from pydantic import field_validator, field_serializer

class FileAttachment(SQLModel, table=True):
    __tablename__ = "file_attachments"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    
    # Core File Info
    filename: str
    stored_path: str # Relative path in storage, e.g., "ab/cd/abcdef1234..."
    mime_type: str
    size_bytes: int
    content_hash: str = Field(index=True) # SHA-256 hash for deduplication
    
    # Links to other entities
    event_id: Optional[UUID] = Field(default=None, index=True) # Link to a specific event
    timeline_id: Optional[UUID] = Field(default=None, index=True) # Link to a timeline entry
    
    # Categorization
    category: Optional[str] = Field(default=None, index=True) # e.g., "receipt", "photo", "document"
    tags: List[str] = Field(default=[], sa_column=Column(JSONB))
    
    # Rich Metadata
    description: Optional[str] = None # User provided description
    ai_metadata: Dict[str, Any] = Field(default={}, sa_column=Column(JSONB)) # OCR, captions, object detection
    user_metadata: Dict[str, Any] = Field(default={}, sa_column=Column(JSONB)) # Custom user fields
    technical_metadata: Dict[str, Any] = Field(default={}, sa_column=Column(JSONB)) # EXIF, PDF info, etc.
    
    # Vector Search
    # Pydantic doesn't know how to serialize numpy arrays returned by pgvector, so we need to be careful.
    # However, SQLModel/Pydantic should handle List[float] fine if the DB driver returns it as such.
    # The issue is likely that asyncpg/pgvector returns a numpy array or similar that Pydantic doesn't like.
    # We can use a validator or just ensure it's a list.
    embedding: Optional[List[float]] = Field(default=None, sa_column=Column(Vector(768)))
    embedding_model: Optional[str] = Field(default=None)
    
    class Config:
        arbitrary_types_allowed = True

    @field_validator("embedding", mode="before")
    @classmethod
    def parse_embedding(cls, v):
        if v is None:
            return None
        if isinstance(v, np.ndarray):
            return v.tolist()
        return v

    @field_serializer("embedding")
    def serialize_embedding(self, v, _info):
        if v is None:
            return None
        if isinstance(v, np.ndarray):
            return v.tolist()
        return v
    
    # Status
    is_processed: bool = Field(default=False) # Whether AI processing has run
    
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
