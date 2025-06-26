from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import String, Date, DateTime, Enum, ForeignKey, Uuid, text, Table, Column, Computed
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector
import enum
import uuid
from datetime import date, datetime
from typing import Dict, Any, Optional
from sqlalchemy import types

class Base(DeclarativeBase):
    pass


class EventKind(str, enum.Enum):
    digital_activity = "digital_activity"
    health_metric = "health_metric"
    location_visit = "location_visit"
    media_note = "media_note"
    photo = "photo"


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(128))

    aliases: Mapped[list["ProjectAlias"]] = relationship("ProjectAlias", back_populates="project")
    timeline_entries: Mapped[list["TimelineEntry"]] = relationship("TimelineEntry", back_populates="project")


class ProjectAlias(Base):
    __tablename__ = "project_aliases"

    alias: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    project: Mapped["Project"] = relationship("Project", back_populates="aliases")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String, nullable=False)
    event_type: Mapped[EventKind] = mapped_column(Enum(EventKind), nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload_hash: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    details: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=True)
    local_day: Mapped[date] = mapped_column(Date, Computed("((start_time AT TIME ZONE 'America/Vancouver')::date)"), nullable=False)


class TimelineEntry(Base):
    __tablename__ = "timeline_entries"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    summary: Mapped[str] = mapped_column(String)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=True)
    local_day: Mapped[date] = mapped_column(Date, Computed("((start_time AT TIME ZONE 'America/Vancouver')::date)"), nullable=False)

    project: Mapped["Project"] = relationship("Project", back_populates="timeline_entries")


class TimelineSourceEvent(Base):
    __tablename__ = "timeline_source_events"

    entry_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("timeline_entries.id"), primary_key=True)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id"), primary_key=True)


class DigitalActivityData(Base):
    __tablename__ = "digital_activity_data"

    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id"), primary_key=True)
    hostname: Mapped[str] = mapped_column(String, nullable=False)
    app: Mapped[Optional[str]] = mapped_column(String)
    title: Mapped[Optional[str]] = mapped_column(String)
    url: Mapped[Optional[str]] = mapped_column(String)


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)


event_state = Table(
    "event_state",
    Base.metadata,
    Column("event_id", Uuid, ForeignKey("events.id"), primary_key=True),
)
