"""Query interpretation and bounded conversational context for LifeLog chat."""

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True)
class TemporalScope:
    """A user-requested time range, represented in both local and UTC time."""

    label: str
    logical_from: str
    logical_until: str
    occurred_from: datetime
    occurred_until: datetime
    search_query: str


def _timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def _scope(
    *,
    label: str,
    start: date,
    until: date,
    query: str,
    matched: str,
    timezone_name: str,
) -> TemporalScope:
    zone = _timezone(timezone_name)
    local_start = datetime.combine(start, time.min, tzinfo=zone)
    local_until = datetime.combine(until, time.min, tzinfo=zone)
    cleaned = re.sub(re.escape(matched), " ", query, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,?.")
    return TemporalScope(
        label=label,
        logical_from=start.isoformat(),
        logical_until=until.isoformat(),
        occurred_from=local_start.astimezone(UTC).replace(tzinfo=None),
        occurred_until=local_until.astimezone(UTC).replace(tzinfo=None),
        search_query=cleaned or query,
    )


def parse_temporal_scope(
    query: str,
    *,
    timezone_name: str = "UTC",
    now: datetime | None = None,
) -> TemporalScope | None:
    """Parse common natural-language date scopes without asking the LLM."""
    zone = _timezone(timezone_name)
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    today = current.astimezone(zone).date()

    patterns: list[tuple[str, date, date]] = [
        (r"\byesterday\b", today - timedelta(days=1), today),
        (r"\btoday\b", today, today + timedelta(days=1)),
    ]
    week_start = today - timedelta(days=today.weekday())
    patterns.extend(
        [
            (r"\bthis week\b", week_start, week_start + timedelta(days=7)),
            (r"\blast week\b", week_start - timedelta(days=7), week_start),
            (r"\bthis month\b", today.replace(day=1), _next_month(today.replace(day=1))),
            (
                r"\blast month\b",
                _previous_month(today.replace(day=1)),
                today.replace(day=1),
            ),
        ]
    )
    for pattern, start, until in patterns:
        match = re.search(pattern, query, flags=re.IGNORECASE)
        if match:
            return _scope(
                label=match.group(0).lower(),
                start=start,
                until=until,
                query=query,
                matched=match.group(0),
                timezone_name=timezone_name,
            )

    relative = re.search(
        r"\b(?:the\s+)?(?:last|past)\s+(\d{1,3})\s+(day|week|month)s?\b",
        query,
        flags=re.IGNORECASE,
    )
    if relative:
        amount = min(int(relative.group(1)), 3660)
        unit = relative.group(2).lower()
        days = amount * {"day": 1, "week": 7, "month": 30}[unit]
        until = today + timedelta(days=1)
        return _scope(
            label=relative.group(0).lower(),
            start=until - timedelta(days=days),
            until=until,
            query=query,
            matched=relative.group(0),
            timezone_name=timezone_name,
        )

    explicit = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", query)
    if explicit:
        try:
            requested = date.fromisoformat(explicit.group(1))
        except ValueError:
            return None
        return _scope(
            label=requested.isoformat(),
            start=requested,
            until=requested + timedelta(days=1),
            query=query,
            matched=explicit.group(0),
            timezone_name=timezone_name,
        )
    return None


def needs_tool_planning(query: str) -> bool:
    """Avoid a planner LLM call unless deterministic work may be required."""
    return bool(
        re.search(
            r"\b(how (?:much|many|long)|total|count|average|sum|compare|"
            r"deadline|due|unfinished|open commitments?|progress|conflict|"
            r"schedule|plan|what should i (?:do|work|focus)|remind|create|"
            r"add|change|update|move|cancel|mark|history of)\b",
            query,
            flags=re.IGNORECASE,
        )
    )


def format_conversation_history(history: list[tuple[str, str]]) -> str:
    """Bound history by turns and characters; it is continuity, not evidence."""
    kept: list[str] = []
    remaining = 12_000
    for role, content in reversed(history[-12:]):
        normalized = re.sub(r"\s+", " ", content).strip()
        if not normalized:
            continue
        clipped = normalized[-min(len(normalized), remaining) :]
        kept.append(f"{role.title()}: {clipped}")
        remaining -= len(clipped)
        if remaining <= 0:
            break
    return "\n".join(reversed(kept))


def _next_month(value: date) -> date:
    return (value.replace(day=28) + timedelta(days=4)).replace(day=1)


def _previous_month(value: date) -> date:
    return (value - timedelta(days=1)).replace(day=1)
