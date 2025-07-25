# central_server/processing_service/db_models.py
import uuid
import enum
from sqlalchemy import (
    Column, DateTime, ForeignKey, Text, String, Enum as SQLAlchemyEnum,
    PrimaryKeyConstraint, JSON, Date, Double, LargeBinary, Table, Index, Float,
    Boolean, Computed
)
from sqlalchemy.dialects.postgresql import UUID, CITEXT
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func

# Use pgvector if available, otherwise a placeholder
try:
    from pgvector.sqlalchemy import Vector
    PGVECTOR_AVAILABLE = True
except ImportError:
    PGVECTOR_AVAILABLE = False
    Vector = LargeBinary  # Placeholder

Base = declarative_base()

# Define a proper Python enum for event kinds
class EventKind(enum.Enum):
    DIGITAL_ACTIVITY = 'digital_activity'
    HEALTH_METRIC = 'health_metric'
    LOCATION_VISIT = 'location_visit'
    MEDIA_NOTE = 'media_note'
    PHOTO = 'photo'

# --- Junction table for many-to-many relationship ---
timeline_source_events_table = Table('timeline_source_events', Base.metadata,
    Column('entry_id', UUID(as_uuid=True), ForeignKey('timeline_entries.id', ondelete="CASCADE"), primary_key=True),
    Column('event_id', UUID(as_uuid=True), ForeignKey('events.id', ondelete="CASCADE"), primary_key=True)
)

class Event(Base):
    __tablename__ = 'events'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type = Column(SQLAlchemyEnum(EventKind, name='eventkind', values_callable=lambda x: [e.value for e in x]), nullable=False)
    source = Column(Text, nullable=False)
    start_time = Column(DateTime(timezone=True), nullable=False, index=True)
    end_time = Column(DateTime(timezone=True), nullable=True)
    payload_hash = Column(Text, unique=True, nullable=False)
    details = Column(JSON, nullable=True)
    local_day = Column(Date, Computed("(start_time AT TIME ZONE 'America/Vancouver')::date", persisted=True))

    digital_activity = relationship("DigitalActivityData", back_populates="event", uselist=False, cascade="all, delete-orphan")
    # Add other relationships (photo_data, location_data) here as you implement them

class DigitalActivityData(Base):
    __tablename__ = 'digital_activity_data'

    event_id = Column(UUID(as_uuid=True), ForeignKey('events.id', ondelete="CASCADE"), primary_key=True)
    hostname = Column(Text, nullable=False)
    app = Column(Text)
    title = Column(Text)
    url = Column(Text)

    event = relationship("Event", back_populates="digital_activity")

class Project(Base):
    __tablename__ = "projects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(CITEXT, unique=True, nullable=False)
    embedding = Column(Vector(128)) if PGVECTOR_AVAILABLE else Column(Vector)
    manual_creation = Column(Boolean, nullable=False, default=False)

    timeline_entries = relationship("TimelineEntryOrm", back_populates="project")


class SuggestionStatus(enum.Enum):
    PENDING = 'pending'
    ACCEPTED = 'accepted'
    REJECTED = 'rejected'


class ProjectSuggestion(Base):
    __tablename__ = 'project_suggestions'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    suggested_name = Column(CITEXT, nullable=False)
    embedding = Column(Vector(128)) if PGVECTOR_AVAILABLE else Column(Vector)
    confidence_score = Column(Float, nullable=False)
    rationale = Column(JSON, nullable=True)
    status = Column(SQLAlchemyEnum(SuggestionStatus, name='suggestion_status', values_callable=lambda x: [e.value for e in x]), nullable=False, default=SuggestionStatus.PENDING)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class TimelineEntryOrm(Base):
    __tablename__ = "timeline_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    start_time = Column(DateTime(timezone=True), nullable=False, index=True)
    end_time = Column(DateTime(timezone=True), nullable=False)
    title = Column(Text, nullable=False)
    summary = Column(Text)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    local_day = Column(Date, Computed("(start_time AT TIME ZONE 'America/Vancouver')::date", persisted=True))

    project = relationship("Project", back_populates="timeline_entries")
    source_events = relationship(
        "Event",
        secondary=timeline_source_events_table,
        backref="timeline_entries"
    )

if not PGVECTOR_AVAILABLE:
    print("WARNING: pgvector.sqlalchemy not found. VECTOR type support in ORM is limited.")
