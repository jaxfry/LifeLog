import pytest
from unittest.mock import patch, MagicMock
from LifeLog.collectors.live_collector import LiveCollector

@pytest.fixture
def collector():
    return LiveCollector(polling_interval=0.01, retry_attempts=2, retry_delay=0.01)

def test_collect_inserts_and_updates(monkeypatch, collector):
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    mock_conn.__enter__ = lambda self: self
    mock_conn.__exit__ = lambda self, *args: None
    
    # Mock fetchone to return a timestamp for last_processed_timestamp
    mock_cur.fetchone.return_value = [1230]
    
    # Mock the fetch_new_events function to avoid ActivityWatch connection
    def mock_fetch_new_events(since):
        return [{"timestamp": 1234, "duration_ms": 1000, "app": "TestApp", "title": "Test Title"}]
    
    monkeypatch.setattr('LifeLog.collectors.live_collector.get_connection', lambda: mock_conn)
    monkeypatch.setattr('LifeLog.collectors.live_collector.fetch_new_events', mock_fetch_new_events)
    
    collector.collect()
    
    # Verify that execute was called with expected queries
    execute_calls = [call[0][0] for call in mock_cur.execute.call_args_list]
    assert any("BEGIN TRANSACTION" in call for call in execute_calls)
    assert any("SELECT value FROM metadata" in call for call in execute_calls)
    assert any("INSERT INTO timeline_events" in call for call in execute_calls)
    assert any("INSERT INTO metadata" in call for call in execute_calls)
    assert mock_conn.commit.called

def test_collect_handles_no_new_events(monkeypatch, collector):
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    mock_conn.__enter__ = lambda self: self
    mock_conn.__exit__ = lambda self, *args: None
    
    # Mock fetchone to return a timestamp for last_processed_timestamp
    mock_cur.fetchone.return_value = [1230]
    
    # Mock the fetch_new_events function to return no events
    def mock_fetch_new_events(since):
        return []
    
    monkeypatch.setattr('LifeLog.collectors.live_collector.get_connection', lambda: mock_conn)
    monkeypatch.setattr('LifeLog.collectors.live_collector.fetch_new_events', mock_fetch_new_events)
    
    collector.collect()
    
    # Should not call insert operations when no new events
    execute_calls = [call[0][0] for call in mock_cur.execute.call_args_list]
    assert any("BEGIN TRANSACTION" in call for call in execute_calls)
    assert any("SELECT value FROM metadata" in call for call in execute_calls)
    assert not any("INSERT INTO timeline_events" in call for call in execute_calls)
    assert not any("INSERT INTO metadata" in call for call in execute_calls)
    assert mock_conn.commit.called

def test_error_handling_and_retry(monkeypatch, collector):
    with patch.object(collector.logger, 'error') as mock_log:
        # Mock collect to raise an exception
        original_collect = collector.collect
        collector.collect = MagicMock(side_effect=Exception("test error"))
        
        # Set up a counter to break the loop after a few iterations
        call_count = 0
        def mock_sleep(duration):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:  # Stop after a couple of calls
                collector._stop_event.set()
        
        with patch('time.sleep', side_effect=mock_sleep):
            collector.start()
            
        assert mock_log.called
        assert collector.collect.call_count == collector.retry_attempts
