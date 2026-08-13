from datetime import UTC, datetime

from app.core.utils.time import get_day_bounds_utc, get_timezone_obj, to_local_time


def test_get_timezone_obj():
    assert get_timezone_obj("UTC") == UTC
    assert get_timezone_obj("America/New_York") is not None
    # Test offset parsing
    tz = get_timezone_obj("-0500")
    assert tz is not None
    dt = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
    assert dt.astimezone(tz).hour == 7

def test_to_local_time():
    dt = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)

    # UTC to UTC
    assert to_local_time(dt, "UTC") == dt

    # UTC to EST (-5)
    local = to_local_time(dt, "America/New_York")
    assert local.hour == 7
    assert local.day == 1

    # UTC to IST (+5:30)
    local = to_local_time(dt, "+0530")
    assert local.hour == 17
    assert local.minute == 30

def test_get_day_bounds_utc():
    # Test for a date in EST (-5)
    # Local day: 2024-01-01 00:00 to 23:59 EST
    # UTC: 2024-01-01 05:00 to 2024-01-02 04:59

    date_obj = datetime(2024, 1, 1)
    start_utc, end_utc = get_day_bounds_utc(date_obj, "America/New_York")

    assert start_utc.year == 2024
    assert start_utc.month == 1
    assert start_utc.day == 1
    assert start_utc.hour == 5

    assert end_utc.year == 2024
    assert end_utc.month == 1
    assert end_utc.day == 2
    assert end_utc.hour == 4
    assert end_utc.minute == 59
