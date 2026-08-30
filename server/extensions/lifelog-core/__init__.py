"""
LifeLog Core Extension

This extension registers the built-in core actors (timeline-enricher, test-processor)
to ensure they are persisted to the database.

The actual actor implementations are in lifelog.actors.enrichers and lifelog.actors.processors.
This extension just provides the manifest for database persistence.
"""

# No additional actor registration needed - actors are already registered
# in lifelog.actors.enrichers and lifelog.actors.processors via @actor_registry.register
