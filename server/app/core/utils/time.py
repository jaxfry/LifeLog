from datetime import UTC, datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

def parse_offset(offset_str: str) -> timezone | None:
    """
    Parses a timezone offset string (e.g. "-0500", "+05:30") into a timezone object.
    """
    if not offset_str:
        return None
    try:
        # Remove colon if present for strptime compatibility with %z
        clean_offset = offset_str.replace(":", "")
        # %z expects +HHMM or -HHMM
        dummy = datetime.strptime(f"20000101120000{clean_offset}", "%Y%m%d%H%M%S%z")
        return dummy.tzinfo
    except ValueError:
        return None

def get_timezone_obj(timezone_str: str) -> timezone:
    """
    Returns a timezone object from a string (IANA name or offset).
    Defaults to UTC if invalid.
    """
    if not timezone_str or timezone_str == "UTC":
        return UTC

    try:
        return ZoneInfo(timezone_str)
    except Exception:
        # Try parsing as offset
        tz = parse_offset(timezone_str)
        return tz if tz else UTC

def to_local_time(dt: datetime, timezone_str: str) -> datetime:
    """
    Converts a UTC datetime to local time based on the timezone string.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)

    tz = get_timezone_obj(timezone_str)
    return dt.astimezone(tz)

def get_day_bounds_utc(date_obj: datetime, timezone_str: str) -> tuple[datetime, datetime]:
    """
    Returns the start and end of a day in UTC, given a local date and timezone.
        Args:
        date_obj: The date (can be datetime, will use .date())
        timezone_str: The local timezone
            Returns:
        (start_utc, end_utc)
    """
    tz = get_timezone_obj(timezone_str)

    # Create local start of day
    # We use the year, month, day from date_obj
    local_start = datetime(
        date_obj.year,
        date_obj.month,
        date_obj.day,
        0, 0, 0, 0,
        tzinfo=tz
    )

    # Create local end of day
    local_end = datetime(
        date_obj.year,
        date_obj.month,
        date_obj.day,
        23, 59, 59, 999999,
        tzinfo=tz
    )

    # Convert to UTC
    start_utc = local_start.astimezone(UTC).replace(tzinfo=None)
    end_utc = local_end.astimezone(UTC).replace(tzinfo=None)

    return start_utc, end_utc

def get_logical_date(dt_utc: datetime, iana_timezone: str, rollover_hour: int = 4) -> str:
    """
    Computes the 'logical day' string (YYYY-MM-DD) for a given UTC instant.
    For example, if rollover_hour=4, any local time before 4:00 AM belongs to the previous day.
    """
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=UTC)

    # Convert absolute instant to local time
    tz = get_timezone_obj(iana_timezone)
    local_dt = dt_utc.astimezone(tz)

    # Check if we should roll back
    if local_dt.hour < rollover_hour:
        local_dt = local_dt - timedelta(days=1)

    return local_dt.strftime("%Y-%m-%d")
