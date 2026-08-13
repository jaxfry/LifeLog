from datetime import datetime, timedelta

from app.core.config import settings
from app.models.files import Commitment


def reminder_time(commitment: Commitment) -> datetime | None:
    """Apply the base reminder policy while respecting an action's availability."""
    if commitment.due_at is None:
        return None
    scheduled = commitment.due_at - timedelta(minutes=settings.DEFAULT_REMINDER_LEAD_MINUTES)
    if commitment.not_before is not None:
        scheduled = max(scheduled, commitment.not_before)
    return scheduled
