from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.config import settings
from app.core.logger import get_logger
from app.models.ingest import Event
from app.models.processing import Session

logger = get_logger(__name__)


def _logical_date(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


async def run_sessionizer(session: AsyncSession) -> int:
    """
    Find un-sessioned events and group them into sessions.
    Returns the number of sessions created.
    """
    statement = (
        select(Event)
        .where(Event.is_superseded == False)
        .where(Event.session_id.is_(None))
        .order_by(Event.start_time.asc())
    )
    result = await session.execute(statement)
    events = result.scalars().all()

    if not events:
        return 0

    groups: list[list[Event]] = []
    idle_groups: list[list[Event]] = []
    by_owner: dict[object, list[Event]] = {}
    for event in events:
        by_owner.setdefault(event.owner_user_id, []).append(event)
    for owner_events in by_owner.values():
        owner_groups, owner_idle_groups = _partition_session_groups(owner_events)
        groups.extend(owner_groups)
        idle_groups.extend(owner_idle_groups)

    sessions_created = 0
    for group, kind in [*((group, "activity") for group in groups), *((group, "idle") for group in idle_groups)]:
        start_time = min(e.start_time for e in group)
        end_time = max((e.end_time or e.start_time) for e in group)

        ses = Session(
            owner_user_id=group[0].owner_user_id,
            start_time=start_time,
            end_time=end_time,
            status="pending" if kind == "activity" else "completed",
            processing_status="ready" if kind == "activity" else "completed",
            kind=kind,
            logical_date=group[0].logical_date or _logical_date(start_time),
        )
        session.add(ses)
        await session.flush()

        for evt in group:
            evt.session_id = ses.id
            evt.logical_date = evt.logical_date or _logical_date(evt.start_time)
            session.add(evt)

        sessions_created += 1

    await session.commit()
    logger.info(
        "Sessionizer: %d events -> %d sessions", len(events), sessions_created
    )
    return sessions_created


def _group_into_sessions(events: list[Event]) -> list[list[Event]]:
    groups, _idle_groups = _partition_session_groups(events)
    return groups


def _partition_session_groups(
    events: list[Event],
) -> tuple[list[list[Event]], list[list[Event]]]:
    """Split active episodes and quarantine watcher noise recorded while AFK."""
    gap_minutes = settings.SESSION_GAP_MINUTES
    max_minutes = settings.SESSION_MAX_MINUTES
    afk_seconds = settings.SESSION_AFK_GAP_MINUTES * 60
    afk_windows = sorted(
        (
            event.start_time,
            event.end_time or event.start_time,
        )
        for event in events
        if event.event_type == "device_status"
        and (event.data or {}).get("status") == "afk"
        and ((event.end_time or event.start_time) - event.start_time).total_seconds()
        >= afk_seconds
    )

    active_events: list[Event] = []
    idle_groups: list[list[Event]] = [[] for _window in afk_windows]
    for event in events:
        idle_index = next(
            (
                index
                for index, (start, end) in enumerate(afk_windows)
                if start <= event.start_time < end
            ),
            None,
        )
        if idle_index is None:
            active_events.append(event)
        else:
            idle_groups[idle_index].append(event)

    groups: list[list[Event]] = []
    current: list[Event] = []

    for evt in active_events:
        if not current:
            current.append(evt)
            continue

        prev_end = current[-1].end_time or current[-1].start_time
        curr_start = evt.start_time

        gap = (curr_start - prev_end).total_seconds() / 60
        span = (curr_start - current[0].start_time).total_seconds() / 60
        crossed_afk = any(
            prev_end <= afk_start and curr_start >= afk_end
            for afk_start, afk_end in afk_windows
        )

        if (
            gap > gap_minutes
            or crossed_afk
            or span >= max_minutes
            or _crosses_logical_date(current[-1], evt)
            or len(current) >= settings.SESSION_MAX_EVENTS
        ):
            groups.append(current)
            current = [evt]
        else:
            current.append(evt)

    if current:
        groups.append(current)

    groups = _merge_short_tails(groups, afk_windows, max_minutes)
    return groups, [group for group in idle_groups if group]


def _merge_short_tails(
    groups: list[list[Event]],
    afk_windows: list[tuple[datetime, datetime]],
    max_minutes: int,
) -> list[list[Event]]:
    """Avoid tiny episodes created just before a natural AFK boundary."""
    merged: list[list[Event]] = []
    for group in groups:
        duration = (
            max((event.end_time or event.start_time) for event in group)
            - min(event.start_time for event in group)
        ).total_seconds() / 60
        if merged and duration < 15:
            previous = merged[-1]
            previous_end = max(event.end_time or event.start_time for event in previous)
            group_start = min(event.start_time for event in group)
            combined_start = min(event.start_time for event in previous)
            combined_end = max(event.end_time or event.start_time for event in group)
            combined_minutes = (combined_end - combined_start).total_seconds() / 60
            same_logical_date = not _crosses_logical_date(previous[-1], group[0])
            crossed_afk = any(
                previous_end <= afk_start and group_start >= afk_end
                for afk_start, afk_end in afk_windows
            )
            if same_logical_date and not crossed_afk and combined_minutes <= max_minutes + 15:
                previous.extend(group)
                continue
        merged.append(group)
    return merged


def _crosses_logical_date(a: Event, b: Event) -> bool:
    a_date = a.logical_date or _logical_date(a.start_time)
    b_date = b.logical_date or _logical_date(b.start_time)
    return a_date != b_date
