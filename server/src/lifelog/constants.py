"""
Constants for LifeLog application.

Centralizes magic strings and status values to avoid drift and typos.
"""

from enum import Enum


class ProcessingStatus(str, Enum):
    """Status values for actor_processing_log entries."""
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    SKIPPED = "SKIPPED"
    BATCH_SUBMITTED = "BATCH_SUBMITTED"
    BATCH_PROCESSING = "BATCH_PROCESSING"
    PENDING = "PENDING"
