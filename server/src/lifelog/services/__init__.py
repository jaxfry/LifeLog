"""
Services Package

Contains services for timeline generation, chunking, and enrichment.
Also re-exports services from the legacy services module for backward compatibility.
"""

from .chunking import TimelineChunkingService, EventChunk, ChunkBudget
from .timeline_generation import TimelineGenerationService
from .timeline import TimelineService

# Re-export legacy services for backward compatibility
from ..services_legacy import (
    IngestionService,
    EventService,
    SynthesisService,
    ExtensionService,
    ProcessingService,
    ProcessingRoutingService,
    DeviceService,
    EmbeddingService,
    AIConfigService,
    ExtensionHealthService,
    ExtensionErrorService,
)

__all__ = [
    # New timeline services
    "TimelineChunkingService",
    "EventChunk",
    "ChunkBudget",
    "TimelineGenerationService",
    "TimelineService",
    # Legacy services (re-exported)
    "IngestionService",
    "EventService",
    "SynthesisService",
    "ExtensionService",
    "ProcessingService",
    "ProcessingRoutingService",
    "DeviceService",
    "EmbeddingService",
    "AIConfigService",
    "ExtensionHealthService",
    "ExtensionErrorService",
]
