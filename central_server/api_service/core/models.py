from sqlalchemy import (
    Column, String, DateTime, Text, UUID, ForeignKey, Date, 
    Enum, Index, UniqueConstraint, JSON
)
from sqlalchemy.dialects.postgresql import CITEXT, JSONB
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func
from datetime import datetime, date
from typing import Optional, Dict, Any
import uuid as uuid_pkg
import enum

from .database import Base

class EventKind(str, enum.Enum):
    DIGITAL_ACTIVITY = "digital_activity"
    HEALTH_METRIC = "health_metric"
    LOCATION_VISIT = "location_visit"
    MEDIA_NOTE = "media_note"
    PHOTO = "photo"

class User(Base):
    __tablename__ = "users"
    
    id: Mapped[uuid_pkg.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_pkg.uuid4)
    username: Mapped[str] = mapped_column(CITEXT, unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(Text, nullable=False)

class Project(Base):
    __tablename__ = "projects"
    
    id: Mapped[uuid_pkg.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_pkg.uuid4)
    name: Mapped[str] = mapped_column(CITEXT, unique=True, nullable=False)
    embedding: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    
    # Relationships
    timeline_entries = relationship("TimelineEntry", back_populates="project")
    aliases = relationship("ProjectAlias", back_populates="project", cascade="all, delete-orphan")

class ProjectAlias(Base):
    __tablename__ = "project_aliases"
    
    alias: Mapped[str] = mapped_column(CITEXT, primary_key=True)
    project_id: Mapped[uuid_pkg.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"))
    
    # Relationships
    project = relationship("Project", back_populates="aliases")

class Event(Base):
    __tablename__ = "events"
    
    id: Mapped[uuid_pkg.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_pkg.uuid4)
    user_id: Mapped[Optional[uuid_pkg.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    event_type: Mapped[EventKind] = mapped_column(Enum(EventKind), nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    payload_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    local_day: Mapped[date] = mapped_column(Date, nullable=False)  # Generated column in SQL
    
    # Relationships
    digital_activity = relationship("DigitalActivityData", back_populates="event", uselist=False)
    photo_data = relationship("PhotoData", back_populates="event", uselist=False)
    location_data = relationship("LocationData", back_populates="event", uselist=False)
    event_state = relationship("EventState", back_populates="event", uselist=False)
    
    # Indexes are defined in the SQL schema

class TimelineEntry(Base):
    __tablename__ = "timeline_entries"
    
    id: Mapped[uuid_pkg.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_pkg.uuid4)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    project_id: Mapped[Optional[uuid_pkg.UUID]] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("projects.id", ondelete="SET NULL"), 
        nullable=True
    )
    local_day: Mapped[date] = mapped_column(Date, nullable=False)  # Generated column in SQL
    
    # Relationships
    project = relationship("Project", back_populates="timeline_entries")
    source_events = relationship("TimelineSourceEvent", back_populates="timeline_entry", cascade="all, delete-orphan")

class TimelineSourceEvent(Base):
    __tablename__ = "timeline_source_events"
    
    entry_id: Mapped[uuid_pkg.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("timeline_entries.id", ondelete="CASCADE"), 
        primary_key=True
    )
    event_id: Mapped[uuid_pkg.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("events.id", ondelete="CASCADE"), 
        primary_key=True
    )
    
    # Relationships
    timeline_entry = relationship("TimelineEntry", back_populates="source_events")
    event = relationship("Event")

class DigitalActivityData(Base):
    __tablename__ = "digital_activity_data"
    
    event_id: Mapped[uuid_pkg.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("events.id", ondelete="CASCADE"), 
        primary_key=True
    )
    hostname: Mapped[str] = mapped_column(Text, nullable=False)
    app: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Relationships
    event = relationship("Event", back_populates="digital_activity")

class EventState(Base):
    __tablename__ = "event_state"
    
    event_id: Mapped[uuid_pkg.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("events.id", ondelete="CASCADE"), 
        primary_key=True
    )
    
    # Relationships
    event = relationship("Event", back_populates="event_state")

class PhotoData(Base):
    __tablename__ = "photo_data"
    
    event_id: Mapped[uuid_pkg.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("events.id", ondelete="CASCADE"), 
        primary_key=True
    )
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    caption: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    photo_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    
    # Relationships
    event = relationship("Event", back_populates="photo_data")

class LocationData(Base):
    __tablename__ = "location_data"
    
    event_id: Mapped[uuid_pkg.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("events.id", ondelete="CASCADE"), 
        primary_key=True
    )
    latitude: Mapped[float] = mapped_column(nullable=False)
    longitude: Mapped[float] = mapped_column(nullable=False)
    accuracy_m: Mapped[Optional[float]] = mapped_column(nullable=True)
    place_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Relationships
    event = relationship("Event", back_populates="location_data")

class Meta(Base):
    __tablename__ = "meta"
    
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
