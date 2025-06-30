import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta, timezone
from local_daemon.collector import ActivityWatchCollector
from aw_core.models import Event as AWEvent

@pytest.fixture
def collector():
    with patch('local_daemon.collector.ActivityWatchClient') as mock_aw_client:
        collector = ActivityWatchCollector()
        collector.aw_client = mock_aw_client.return_value
        yield collector

@pytest.fixture
def mock_cache():
    with patch('local_daemon.collector.cache') as mock_cache_module:
        yield mock_cache_module

def test_generate_event_hash(collector):
    ts = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    h1 = collector._generate_event_hash(ts, "app", "title", "url")
    h2 = collector._generate_event_hash(ts, "app", "title", "url")
    h3 = collector._generate_event_hash(ts, "app2", "title", "url")
    assert h1 == h2
    assert h1 != h3

def test_process_aw_event(collector):
    aw_event = AWEvent(
        id=1,
        timestamp=datetime.now(timezone.utc),
        duration=timedelta(seconds=60),
        data={"app": "TestApp", "title": "Test Title"}
    )
    processed = collector._process_aw_event(aw_event, "desktop_activity.window", "test-device")
    assert processed is not None
    assert processed["data"]["app"] == "TestApp"
    assert "event_hash" in processed

def test_collect_and_store_events(collector, mock_cache):
    bucket_id = "aw-watcher-window_testhost"
    with patch.dict(collector.last_collection_times, {bucket_id: None}):
        # Mock the fetch call to return a single event
        mock_event = AWEvent(id=1, timestamp=datetime.now(timezone.utc), duration=timedelta(seconds=60), data={"app": "TestApp", "title": "Test"})
        collector._fetch_events_from_bucket = MagicMock(return_value=[mock_event])
        
        # Mock the cache to report that the event is new
        mock_cache.add_event_to_cache.return_value = True

        # Run collection
        count = collector.collect_and_store_events()
        
        # Assertions
        assert count > 0
        collector._fetch_events_from_bucket.assert_called()
        mock_cache.add_event_to_cache.assert_called()

def test_collect_events_client_unavailable():
    # Intentionally create a collector where the client fails to initialize
    with patch('local_daemon.collector.ActivityWatchClient', side_effect=Exception("AW connection failed")):
        collector = ActivityWatchCollector()
        assert collector.aw_client is None
        
        # Attempt to collect events
        start_time = datetime.now(timezone.utc) - timedelta(minutes=10)
        end_time = datetime.now(timezone.utc)
        events = collector._collect_events(start_time, end_time)
        
        # Should return an empty list and not raise an error
        assert events == []