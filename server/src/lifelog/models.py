"""
LifeLog Database Models

This module defines the SQLModel-based database models for the LifeLog application.
The models are organized into logical groups representing different aspects of the system:
- Extension and Actor management
- Data ingestion and processing
- Event tracking and metadata
- AI integration and usage tracking
- Data synthesis and reporting
"""

import enum
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import Column, UniqueConstraint
import sqlalchemy as sa
from sqlmodel import JSON, Field, Relationship, SQLModel
from pgvector.sqlalchemy import Vector


# Helper function for timezone-aware datetime defaults
def utcnow() -> datetime:
    """Return current UTC time as a timezone-aware datetime (for TIMESTAMPTZ columns)."""
    return datetime.now(timezone.utc)


# =================================================================
# ENUMS - Domain value objects for type safety
# =================================================================

class ActorType(str, enum.Enum):
    """Types of actors that can process data in the LifeLog system."""
    SOURCE = "SOURCE"
    PROCESSOR = "PROCESSOR"
    ENRICHER = "ENRICHER"
    BATCH_WORKER = "BATCH_WORKER"
    AGENT = "AGENT"


class AIProviderType(str, enum.Enum):
    """Types of AI providers for model inference."""
    REMOTE_API = "REMOTE_API"
    LOCAL_MANAGED = "LOCAL_MANAGED"
    LOCAL_DOCKERIZED = "LOCAL_DOCKERIZED"

# =================================================================
# ASSOCIATION TABLES - Many-to-Many relationship bridges
# =================================================================

class EventRawLogLink(SQLModel, table=True):
    """Association table linking Events to their source RawLogs."""
    event_id: Optional[int] = Field(
        default=None, 
        foreign_key="event.id", 
        primary_key=True
    )
    raw_log_id: Optional[int] = Field(
        default=None, 
        foreign_key="rawlog.id", 
        primary_key=True
    )


class SynthesisEventLink(SQLModel, table=True):
    """Association table linking SynthesisReports to Events they analyze."""
    report_id: Optional[int] = Field(
        default=None, 
        foreign_key="synthesisreport.id", 
        primary_key=True
    )
    event_id: Optional[int] = Field(
        default=None, 
        foreign_key="event.id", 
        primary_key=True
    )


class TimelineBlockEventLink(SQLModel, table=True):
    """Association table linking TimelineBlocks to Events they summarize."""
    timeline_block_id: Optional[int] = Field(
        default=None,
        foreign_key="timelineblock.id",
        primary_key=True
    )
    event_id: Optional[int] = Field(
        default=None,
        foreign_key="event.id",
        primary_key=True
    )

# =================================================================
# EXTENSION MANAGEMENT - Plugin system and actor definitions
# =================================================================

class Extension(SQLModel, table=True):
    """
    Represents a plugin/extension that adds functionality to LifeLog.
    Extensions can define actors, event types, and prompt templates.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    slug: str = Field(unique=True, index=True, nullable=False)
    name: str = Field(nullable=False)
    version: str = Field(nullable=False)
    is_active: bool = Field(default=True, nullable=False)
    config_schema: Optional[dict] = Field(
        default=None, 
        sa_column=Column(JSON),
        description="JSON Schema defining the structure of this extension's configuration"
    )
    config: Optional[dict] = Field(
        default=None, 
        sa_column=Column(JSON),
        description="Current configuration values for this extension"
    )

    # Relationships
    actors: List["Actor"] = Relationship(back_populates="extension")
    event_types: List["EventType"] = Relationship(back_populates="owner_extension")
    prompt_templates: List["PromptTemplate"] = Relationship(back_populates="owner_extension")
    health_checks: List["ExtensionHealth"] = Relationship(back_populates="extension")
    migrations: List["ExtensionMigration"] = Relationship(back_populates="extension")
    # Note: ExtensionLoadError doesn't have a relationship since it can exist before Extension record


class ExtensionHealth(SQLModel, table=True):
    """
    Tracks the health status of extensions.
    Extensions can implement a health_check() hook to report their status.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    extension_id: int = Field(foreign_key="extension.id", nullable=False, index=True)
    status: str = Field(
        nullable=False,
        description="Health status: 'healthy', 'degraded', or 'unhealthy'"
    )
    last_check: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(sa.DateTime(timezone=True), nullable=False),
        description="When this health check was performed"
    )
    errors: Optional[List[str]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="List of error messages"
    )
    warnings: Optional[List[str]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="List of warning messages"
    )
    details: Optional[dict] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Additional health check details"
    )

    # Relationships
    extension: Extension = Relationship(back_populates="health_checks")


class ExtensionMigration(SQLModel, table=True):
    """
    Tracks applied database migrations for extensions.
    Each migration file applied to an extension is recorded here.
    """
    __table_args__ = (
        UniqueConstraint("extension_id", "migration_name", name="uq_extension_migration"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    extension_id: int = Field(foreign_key="extension.id", nullable=False, index=True)
    migration_name: str = Field(
        nullable=False,
        description="Name of the migration file (e.g., '001_initial_schema.sql')"
    )
    applied_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(sa.DateTime(timezone=True), nullable=False),
        description="When this migration was applied"
    )
    from_version: Optional[str] = Field(
        default=None,
        description="Extension version before migration"
    )
    to_version: str = Field(
        nullable=False,
        description="Extension version after migration"
    )
    checksum: Optional[str] = Field(
        default=None,
        description="SHA256 checksum of migration file for integrity verification"
    )

    # Relationships
    extension: Extension = Relationship(back_populates="migrations")


class ExtensionLifecycleLog(SQLModel, table=True):
    """
    Tracks lifecycle hook executions for extensions.
    Provides audit trail and debugging information for lifecycle events.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    extension_id: int = Field(foreign_key="extension.id", nullable=False, index=True)
    hook_name: str = Field(
        nullable=False,
        description="Lifecycle hook name: 'on_install', 'on_activate', 'on_upgrade', 'on_deactivate', 'on_uninstall'"
    )
    executed_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(sa.DateTime(timezone=True), nullable=False),
        description="When this hook was executed"
    )
    success: bool = Field(
        nullable=False,
        description="Whether the hook completed successfully"
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Error message if hook failed"
    )
    context: Optional[dict] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Additional context (e.g., old_version/new_version for upgrades)"
    )
    execution_time_ms: Optional[int] = Field(
        default=None,
        description="Hook execution time in milliseconds"
    )


class ExtensionLoadError(SQLModel, table=True):
    """
    Tracks extension loading failures for debugging and monitoring.
    Records errors that occur during extension discovery, loading, or activation.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    extension_slug: str = Field(
        nullable=False,
        index=True,
        description="Extension slug (may not exist in Extension table if load failed early)"
    )
    error_type: str = Field(
        nullable=False,
        description="Type of error: 'discovery', 'manifest', 'dependency', 'import', 'activation'"
    )
    error_message: str = Field(
        nullable=False,
        description="Detailed error message"
    )
    stack_trace: Optional[str] = Field(
        default=None,
        description="Full stack trace if available"
    )
    occurred_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(sa.DateTime(timezone=True), nullable=False),
        description="When this error occurred"
    )
    resolved: bool = Field(
        default=False,
        nullable=False,
        description="Whether this error has been resolved (extension loaded successfully)"
    )
    error_context: Optional[dict] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Additional context about the error"
    )


class ActorRouting(SQLModel, table=True):
    """
    DB-backed mapping from a SOURCE actor to its designated PROCESSOR actor.
    This replaces ad-hoc hardcoded routing maps in API code.
    """
    __table_args__ = (
        UniqueConstraint("source_actor_id", name="uq_actor_routing_source"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    source_actor_id: int = Field(foreign_key="actor.id", nullable=False, index=True)
    processor_actor_id: int = Field(foreign_key="actor.id", nullable=False)


# In your models.py file, replace the old Actor class with this one.

class Actor(SQLModel, table=True):
    """
    Represents a processing unit within an extension that performs specific tasks.
    Each actor has a type and version for tracking processing capabilities.
    """
    __table_args__ = (
        UniqueConstraint("extension_id", "slug", name="uq_actor_extension_slug"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    
    # --- THIS IS THE FIX ---
    # We change `int` to `Optional[int]` and add `default=None`.
    # `nullable=False` still ensures the database column cannot be NULL.
    extension_id: Optional[int] = Field(
        default=None, foreign_key="extension.id", nullable=False
    )
    # -----------------------

    slug: str = Field(nullable=False)
    actor_type: ActorType = Field(nullable=False)
    version: str = Field(nullable=False)

    # Relationships
    extension: Extension = Relationship(back_populates="actors")
    raw_logs: List["RawLog"] = Relationship(back_populates="source_actor")


class Device(SQLModel, table=True):
    """
    Represents a client device that can send data to LifeLog.
    Devices are authenticated via encrypted API keys.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True, nullable=False)
    type: Optional[str] = Field(default=None)
    encrypted_api_key: str = Field(unique=True, nullable=False)
    last_seen: Optional[datetime] = Field(
        default=None,
        sa_column=Column(sa.DateTime(timezone=True), nullable=True),
    )
    client_metadata: Optional[dict] = Field(default=None, sa_column=Column(JSON))

# =================================================================
# DATA INGESTION - Raw data capture and processing pipeline
# =================================================================

class RawLog(SQLModel, table=True):
    """
    Represents raw, unprocessed data ingested from external sources.
    This is the entry point for all data into the LifeLog system.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    source_actor_id: int = Field(foreign_key="actor.id", nullable=False)
    device_id: Optional[int] = Field(default=None, foreign_key="device.id")
    raw_data: dict = Field(sa_column=Column(JSON, nullable=False))
    ingested_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(sa.DateTime(timezone=True), nullable=False),
    )

    # Relationships
    events: List["Event"] = Relationship(
        back_populates="raw_logs", 
        link_model=EventRawLogLink
    )
    source_actor: "Actor" = Relationship(back_populates="raw_logs")


class EventType(SQLModel, table=True):
    """
    Defines the schema and metadata for different types of events.
    Each event type is owned by an extension and identified by a unique slug.
    """
    __table_args__ = (
        UniqueConstraint("owner_extension_id", "slug", name="uq_event_type_owner_slug"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    owner_extension_id: int = Field(foreign_key="extension.id", nullable=False)
    slug: str = Field(nullable=False)
    description: Optional[str] = Field(default=None)

    # Relationships
    owner_extension: Extension = Relationship(back_populates="event_types")

# =================================================================
# EVENT TRACKING - Processed events and enrichment data
# =================================================================

class Event(SQLModel, table=True):
    """
    Represents a processed event derived from raw logs.
    Events have time bounds and can be superseded by newer versions.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    processor_actor_id: int = Field(foreign_key="actor.id", nullable=False)
    start_time: datetime = Field(
        default=...,  # required
        sa_column=Column(sa.DateTime(timezone=True), nullable=False),
    )
    end_time: Optional[datetime] = Field(
        default=None,
        sa_column=Column(sa.DateTime(timezone=True), nullable=True),
    )
    event_type_id: int = Field(foreign_key="eventtype.id", nullable=False)
    summary: Optional[str] = Field(default=None)
    superseded_by_event_id: Optional[int] = Field(
        default=None, 
        foreign_key="event.id"
    )

    # Relationships
    raw_logs: List[RawLog] = Relationship(
        back_populates="events", 
        link_model=EventRawLogLink
    )
    synthesis_reports: List["SynthesisReport"] = Relationship(
        back_populates="events", 
        link_model=SynthesisEventLink
    )
    timeline_blocks: List["TimelineBlock"] = Relationship(
        back_populates="events",
        link_model=TimelineBlockEventLink
    )


class EventEmbedding(SQLModel, table=True):
    """
    Stores vector embeddings for events, generated by specific actors.
    Used for semantic search and similarity matching.
    """
    __table_args__ = (
        UniqueConstraint("event_id", "actor_id", name="uq_event_embedding_actor"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    event_id: int = Field(foreign_key="event.id", nullable=False)
    actor_id: int = Field(foreign_key="actor.id", nullable=False)
    ai_usage_log_id: Optional[int] = Field(
        default=None, 
        foreign_key="aiusagelog.id", 
        unique=True
    )
    
    # Vector embedding stored via pgvector (requires Postgres with pgvector extension)
    embedding: List[float] = Field(sa_column=Column(Vector(1536), nullable=False))


class EventMetadata(SQLModel, table=True):
    """
    Stores additional metadata about events, allowing for flexible enrichment.
    Each metadata entry has a type and structured data payload.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    event_id: int = Field(foreign_key="event.id", nullable=False)
    actor_id: Optional[int] = Field(default=None, foreign_key="actor.id")
    type: str = Field(nullable=False)
    data: dict = Field(sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(sa.DateTime(timezone=True), nullable=False),
    )


class TimelineBlock(SQLModel, table=True):
    """
    Enrichment artifact: AI-generated timeline blocks that summarize groups of events.
    
    Timeline blocks combine multiple raw events into concise, human-readable summaries
    with context. They track the model version used for generation and can be superseded
    when models/prompts improve.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    actor_id: int = Field(
        foreign_key="actor.id",
        nullable=False,
        description="The enricher actor that generated this timeline block"
    )
    start_time: datetime = Field(
        default=...,
        sa_column=Column(sa.DateTime(timezone=True), nullable=False),
        description="Start of the time period covered by this block"
    )
    end_time: datetime = Field(
        default=...,
        sa_column=Column(sa.DateTime(timezone=True), nullable=False),
        description="End of the time period covered by this block"
    )
    title: str = Field(
        nullable=False,
        description="Short title summarizing the main activity"
    )
    summary: str = Field(
        nullable=False,
        description="Human-readable narrative combining context from multiple events"
    )
    tags: Optional[List[str]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Metadata tags for search and categorization"
    )
    block_data: dict = Field(
        sa_column=Column(JSON, nullable=False),
        description="Full structured data including locations, activities, etc."
    )
    character_count: int = Field(
        nullable=False,
        description="Total character count of input events (for budget tracking)"
    )
    token_count: Optional[int] = Field(
        default=None,
        description="Total token count (if available from LLM)"
    )
    model_version: str = Field(
        nullable=False,
        description="LLM model identifier used for generation (e.g., 'gpt-4', 'llama-3')"
    )
    prompt_template_id: Optional[int] = Field(
        default=None,
        foreign_key="prompttemplate.id",
        description="Prompt template used for generation"
    )
    ai_usage_log_id: Optional[int] = Field(
        default=None,
        foreign_key="aiusagelog.id",
        unique=True,
        description="Link to AI usage/cost tracking"
    )
    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(sa.DateTime(timezone=True), nullable=False),
        description="When this block was generated"
    )
    superseded_by_block_id: Optional[int] = Field(
        default=None,
        foreign_key="timelineblock.id",
        description="If this block was regenerated with a new model/prompt"
    )
    
    # Relationships
    events: List["Event"] = Relationship(
        back_populates="timeline_blocks",
        link_model=TimelineBlockEventLink
    )

# =================================================================
# AI INTEGRATION - Provider management and usage tracking
# =================================================================

class AIProvider(SQLModel, table=True):
    """
    Represents an AI service provider for model inference.
    Can be either a remote API service or locally managed model.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(nullable=False)
    provider_slug: str = Field(unique=True, nullable=False)
    model_type: str = Field(nullable=False)
    provider_type: AIProviderType = Field(nullable=False)
    encrypted_credentials: Optional[str] = Field(default=None)
    model_path_or_uri: Optional[str] = Field(default=None)
    config: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    is_active: bool = Field(default=True, nullable=False)


class PromptTemplate(SQLModel, table=True):
    """
    Reusable prompt templates for AI model interactions.
    Templates are versioned and owned by extensions.
    """
    __table_args__ = (
        UniqueConstraint("owner_extension_id", "slug", name="uq_prompt_template_owner_slug"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    owner_extension_id: Optional[int] = Field(
        default=None, 
        foreign_key="extension.id"
    )
    slug: str = Field(nullable=False)
    description: Optional[str] = Field(default=None)
    template_text: str = Field(nullable=False)
    version: int = Field(default=1, nullable=False)

    # Relationships
    owner_extension: Optional[Extension] = Relationship(
        back_populates="prompt_templates"
    )


class AIUsageLog(SQLModel, table=True):
    """
    Tracks AI model usage for cost monitoring and audit purposes.
    Records token consumption and associated costs per model call.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    actor_id: Optional[int] = Field(default=None, foreign_key="actor.id")
    ai_provider_id: int = Field(foreign_key="aiprovider.id", nullable=False)
    event_id: Optional[int] = Field(default=None, foreign_key="event.id")
    call_type: str = Field(nullable=False)
    model_used: str = Field(nullable=False)
    prompt_tokens: Optional[int] = Field(default=None)
    completion_tokens: Optional[int] = Field(default=None)
    cost: Optional[float] = Field(default=None)
    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(sa.DateTime(timezone=True), nullable=False),
    )

# =================================================================
# AI SETTINGS - Defaults and configuration stored in DB
# =================================================================

class AISettings(SQLModel, table=True):
    """
    Singleton table to store AI configuration defaults used by the server.
    Allows runtime modification via internal API without rebuilding.
    """
    id: Optional[int] = Field(default=1, primary_key=True)
    default_embedding_provider_slug: Optional[str] = Field(default=None)
    default_embedding_model: Optional[str] = Field(default=None)
    default_embedding_dim: Optional[int] = Field(default=None)

# =================================================================
# SYNTHESIS & PROCESSING LOGS - Higher-level analysis and tracking
# =================================================================

class SynthesisReport(SQLModel, table=True):
    """
    Represents aggregated analysis reports generated from multiple events.
    Reports can be superseded by newer versions as analysis improves.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    actor_id: int = Field(foreign_key="actor.id", nullable=False)
    start_time: datetime = Field(default=..., sa_column=Column(sa.DateTime(timezone=True), nullable=False))
    end_time: datetime = Field(default=..., sa_column=Column(sa.DateTime(timezone=True), nullable=False))
    report_type: str = Field(nullable=False)
    report_data: dict = Field(sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(sa.DateTime(timezone=True), nullable=False),
    )
    ai_usage_log_id: Optional[int] = Field(
        default=None, 
        foreign_key="aiusagelog.id", 
        unique=True
    )
    superseded_by_report_id: Optional[int] = Field(
        default=None, 
        foreign_key="synthesisreport.id"
    )

    # Relationships
    events: List[Event] = Relationship(
        back_populates="synthesis_reports", 
        link_model=SynthesisEventLink
    )


class ActorProcessingLog(SQLModel, table=True):
    """
    Audit log for actor processing activities.
    Tracks processing status and maintains version history for debugging.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    actor_id: int = Field(foreign_key="actor.id", nullable=False)
    actor_version_at_processing: str = Field(nullable=False)
    raw_log_id: Optional[int] = Field(default=None, foreign_key="rawlog.id")
    event_id: Optional[int] = Field(default=None, foreign_key="event.id")
    status: str = Field(nullable=False)
    processed_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(sa.DateTime(timezone=True), nullable=False),
    )
    details: Optional[dict] = Field(default=None, sa_column=Column(JSON))