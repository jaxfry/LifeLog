import pytest
import polars as pl
from datetime import datetime
from central_server.processing_service.logic.event_aggregation import EventAggregator
from central_server.processing_service.models import ProcessingEventData
from central_server.processing_service.logic.settings import Settings

@pytest.fixture
def aggregator():
    settings = Settings()
    return EventAggregator(settings)

def test_aggregate_events_from_data(aggregator):
    events_data = [
        ProcessingEventData(
            id=1,
            source="test",
            event_type="test_event",
            start_time=datetime(2025, 1, 1, 9, 0, 0),
            end_time=datetime(2025, 1, 1, 9, 0, 10),
            duration_s=10,
            app="TestApp",
            title="Test Title",
            url="http://test.com"
        )
    ]
    df = aggregator.aggregate_events_from_data(events_data)
    assert isinstance(df, pl.DataFrame)
    assert df.height == 1
    assert "time_display" in df.columns

def test_aggregate_events_empty_input(aggregator):
    df = aggregator.aggregate_events_from_data([])
    assert isinstance(df, pl.DataFrame)
    assert df.is_empty()

def test_aggregate_events_afk_only(aggregator):
    events_data = [
        ProcessingEventData(
            id=1,
            source="test",
            event_type="afk",
            start_time=datetime(2025, 1, 1, 9, 0, 0),
            end_time=datetime(2025, 1, 1, 9, 0, 10),
            duration_s=10,
            app=aggregator.settings.AFK_APP_NAME,
            title="AFK",
            url=None
        )
    ]
    df = aggregator.aggregate_events_from_data(events_data)
    assert isinstance(df, pl.DataFrame)
    assert df.is_empty()

def test_aggregate_events_duration_filter(aggregator):
    aggregator.settings.ENRICHMENT_MIN_DURATION_S = 15
    events_data = [
        ProcessingEventData(
            id=1,
            source="test",
            event_type="test_event",
            start_time=datetime(2025, 1, 1, 9, 0, 0),
            end_time=datetime(2025, 1, 1, 9, 0, 10),
            duration_s=10,
            app="TestApp",
            title="Test Title",
            url="http://test.com"
        )
    ]
    df = aggregator.aggregate_events_from_data(events_data)
    assert isinstance(df, pl.DataFrame)
    assert df.is_empty()