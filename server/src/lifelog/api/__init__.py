"""API package exports routers for import convenience."""
from . import auth, timeline, timeline_blocks, ingestion, devices, extensions, event_types, processing
try:
    from . import search
except ImportError:
    search = None  # type: ignore
try:
    from . import synthesis
except ImportError:
    synthesis = None  # type: ignore

__all__ = [
    "auth",
    "timeline",
    "timeline_blocks",
    "ingestion",
    "devices",
    "extensions",
    "event_types",
    "processing",
    "search",
    "synthesis",
]
