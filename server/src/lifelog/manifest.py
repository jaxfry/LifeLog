"""
Extension Manifest Schema Models

Pydantic models for parsing and validating manifest.json files
that define extensions with server-side actors, event types, and client components.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# ===== Server-Side Components =====

class ManifestActor(BaseModel):
    """An actor definition in the manifest."""
    slug: str
    type: str = Field(..., description="Actor type: SOURCE, PROCESSOR, ENRICHER, BATCH_WORKER, AGENT")
    version: str
    description: Optional[str] = None


class ManagedSchemaColumn(BaseModel):
    """Column definition for a managed details table."""
    name: str
    type: str  # SQL type like TEXT, INT, TIMESTAMPTZ, etc.
    nullable: Optional[bool] = True
    default: Optional[str] = None


class ManagedSchemaTable(BaseModel):
    """Table definition for managed schemas."""
    columns: List[ManagedSchemaColumn]


class ManagedSchemas(BaseModel):
    """Managed database schemas that the extension requires."""
    schema_version: int = 1
    tables: Dict[str, ManagedSchemaTable] = Field(default_factory=dict)


class ManifestEventType(BaseModel):
    """Event type definition in the manifest."""
    slug: str
    description: Optional[str] = None


class ManifestPromptTemplate(BaseModel):
    """Prompt template definition in the manifest."""
    slug: str
    description: Optional[str] = None
    template_text: str
    version: int = 1


class ServerSideManifest(BaseModel):
    """Server-side components of an extension."""
    actors: List[ManifestActor] = Field(default_factory=list)
    event_types: List[ManifestEventType] = Field(default_factory=list)
    prompt_templates: List[ManifestPromptTemplate] = Field(default_factory=list)
    managed_schemas: Optional[ManagedSchemas] = None


# ===== Client-Side Components =====

class PermissionsManifest(BaseModel):
    """Permissions requested by a UI component."""
    data_read: List[str] = Field(default_factory=list)
    network_access: List[str] = Field(default_factory=list)


class UIComponentManifest(BaseModel):
    """A UI component definition."""
    slug: str
    type: str  # e.g., "dashboard-widget"
    name: str
    component: str  # path to component file
    permissions: Optional[PermissionsManifest] = None


class CollectorManifest(BaseModel):
    """A data collector definition."""
    slug: str
    entrypoint: str


class PlatformManifest(BaseModel):
    """Client components for a specific platform."""
    collectors: List[CollectorManifest] = Field(default_factory=list)
    ui_components: List[UIComponentManifest] = Field(default_factory=list)


class ClientSideManifest(BaseModel):
    """Client-side components of an extension."""
    platforms: Dict[str, PlatformManifest] = Field(default_factory=dict)


# ===== Root Manifest =====

class ExtensionManifest(BaseModel):
    """
    The complete manifest.json schema for a LifeLog extension.
    
    Follows the architecture v3.3 specification for extension-first design.
    """
    slug: str
    name: str
    version: str
    description: Optional[str] = None
    author: Optional[str] = None
    server_side: Optional[ServerSideManifest] = None
    client_side: Optional[ClientSideManifest] = None
    config: Optional[Dict[str, Any]] = Field(default_factory=dict)

    class Config:
        json_schema_extra = {
            "example": {
                "slug": "activitywatch-connector",
                "name": "ActivityWatch Connector",
                "version": "1.1.0",
                "description": "Connects to ActivityWatch for computer activity tracking",
                "author": "LifeLog Team",
                "server_side": {
                    "actors": [
                        {
                            "slug": "aw-processor",
                            "type": "PROCESSOR",
                            "version": "1.1.0",
                            "description": "Processes raw AW data into computer activity events"
                        }
                    ],
                    "event_types": [
                        {
                            "slug": "computer-activity",
                            "description": "Computer usage activity event"
                        }
                    ]
                },
                "client_side": {
                    "platforms": {
                        "macos": {
                            "collectors": [
                                {
                                    "slug": "mac-collector",
                                    "entrypoint": "collector.js"
                                }
                            ]
                        }
                    }
                }
            }
        }
