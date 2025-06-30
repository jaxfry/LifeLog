import pytest
from unittest.mock import MagicMock, patch
from datetime import date, datetime, time, timezone
from central_server.processing_service.logic.timeline import TimelineProcessorService
from central_server.processing_service.logic.settings import Settings
from central_server.processing_service.models import TimelineEntry, ProcessingEventData

@pytest.fixture
def settings():
    return Settings()

@pytest.fixture
def processor(settings):
    with patch('central_server.processing_service.logic.timeline.EventAggregator'), \
         patch('central_server.processing_service.logic.timeline.LLMProcessor'):
        return TimelineProcessorService(settings)

def test_merge_consecutive_entries(processor):
    entries = [
        TimelineEntry(start=datetime(2025, 1, 1, 9, 0, 0), end=datetime(2025, 1, 1, 9, 15, 0), activity="Work", project="P1"),
        TimelineEntry(start=datetime(2025, 1, 1, 9, 15, 30), end=datetime(2025, 1, 1, 9, 30, 0), activity="Work", project="P1"),
        TimelineEntry(start=datetime(2025, 1, 1, 9, 30, 0), end=datetime(2025, 1, 1, 9, 45, 0), activity="Break", project="P1"),
    ]
    merged = processor.merge_consecutive_entries(entries)
    assert len(merged) == 2
    assert merged[0].end == datetime(2025, 1, 1, 9, 30, 0)

def test_fill_gaps(processor):
    local_tz = processor.get_local_timezone()
    day_start = datetime.combine(date(2025, 1, 1), time.min, tzinfo=local_tz)
    day_end = datetime.combine(date(2025, 1, 1), time.max, tzinfo=local_tz)
    processing_window = MagicMock()
    processing_window.start_time = day_start
    processing_window.end_time = day_end

    entries = [
        TimelineEntry(start=day_start + timedelta(hours=1), end=day_start + timedelta(hours=2), activity="Work", project="P1")
    ]
    
    filled = processor.fill_gaps(entries, processing_window)
    assert len(filled) == 3
    assert filled[0].activity == "Idle / Away"
    assert filled[2].activity == "Idle / Away"

@pytest.mark.asyncio
async def test_process_events_batch(processor):
    events_data = [
        ProcessingEventData(id=1, source="test", event_type="test", start_time=datetime.now(), end_time=datetime.now(), duration_s=10, app="Test", title="Test", url=None)
        for _ in range(20) # Ensure enough events to pass the minimum threshold
    ]
    processor.settings.MIN_EVENTS_FOR_LLM_PROCESSING = 10
    
    # Mock aggregator and LLM processor
    processor.aggregator.aggregate_events_from_data.return_value = MagicMock(is_empty=lambda: False, height=20)
    processor.llm_processor.process_chunk_with_llm.return_value = [
        TimelineEntry(start=datetime.now(), end=datetime.now(), activity="Processed", project="P1")
    ]

    result = await processor.process_events_batch(events_data, date(2025, 1, 1))
    assert len(result) > 0
