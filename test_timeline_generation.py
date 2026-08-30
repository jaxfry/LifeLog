#!/usr/bin/env python3
"""
Simple test script to validate timeline generation components.

This script tests the core timeline generation functionality without
requiring a full database setup.
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone


ROOT_DIR = Path(__file__).resolve().parent
SERVER_SRC = ROOT_DIR / "server" / "src"
if str(SERVER_SRC) not in sys.path:
    sys.path.insert(0, str(SERVER_SRC))


def test_chunk_budget():
    """Test ChunkBudget configuration."""
    print("Testing ChunkBudget...")
    from lifelog.services.chunking import ChunkBudget
    
    budget = ChunkBudget(
        max_characters=4000,
        min_chunk_duration_minutes=5,
        max_chunk_duration_hours=4
    )
    
    assert budget.max_characters == 4000
    assert budget.max_tokens == 1000  # 4000 / 4
    assert budget.min_chunk_duration == timedelta(minutes=5)
    assert budget.max_chunk_duration == timedelta(hours=4)
    
    print("✓ ChunkBudget tests passed")


def test_event_chunk():
    """Test EventChunk creation and methods."""
    print("Testing EventChunk...")
    
    # Mock Event class for testing
    class MockEvent:
        def __init__(self, event_id, start_time, end_time, summary):
            self.id = event_id
            self.start_time = start_time
            self.end_time = end_time
            self.summary = summary
    
    from lifelog.services.chunking import EventChunk
    
    start = datetime(2025, 11, 3, 10, 0, 0, tzinfo=timezone.utc)
    events = [
        MockEvent(1, start, start + timedelta(minutes=10), "Working on code"),
        MockEvent(2, start + timedelta(minutes=10), start + timedelta(minutes=20), "Reading docs"),
        MockEvent(3, start + timedelta(minutes=20), start + timedelta(minutes=30), "Testing feature"),
    ]
    
    chunk = EventChunk(events)
    
    assert chunk.start_time == start
    assert chunk.end_time == start + timedelta(minutes=30)
    assert chunk.character_count == sum(len(e.summary) for e in events)
    assert len(chunk.event_ids) == 3
    assert chunk.duration() == timedelta(minutes=30)
    
    # Test text representation
    text = chunk.to_text()
    assert "Working on code" in text
    assert "Reading docs" in text
    assert "Testing feature" in text
    
    print("✓ EventChunk tests passed")


def test_prompt_template():
    """Test default prompt template formatting."""
    print("Testing prompt template...")
    from lifelog.services.timeline_generation import DEFAULT_TIMELINE_PROMPT
    
    events_text = "[2025-11-03T10:00:00+00:00] Working on code (duration: 10.0 min)"
    formatted = DEFAULT_TIMELINE_PROMPT.format(events_text=events_text)
    
    assert "Working on code" in formatted
    assert "JSON" in formatted
    assert "title" in formatted
    assert "summary" in formatted
    
    print("✓ Prompt template tests passed")


def test_token_estimation():
    """Test token count estimation."""
    print("Testing token estimation...")
    from lifelog.services.chunking import TimelineChunkingService
    
    text = "This is a test sentence with approximately twenty-five characters here."
    tokens = TimelineChunkingService.estimate_token_count(text)
    
    # Should be roughly len(text) / 4
    expected = len(text) // 4
    assert abs(tokens - expected) < 5  # Allow small variance
    
    print(f"✓ Token estimation tests passed (estimated {tokens} tokens for {len(text)} chars)")


def test_models_import():
    """Test that all new models can be imported."""
    print("Testing model imports...")
    
    try:
        from lifelog.models import (
            TimelineBlock,
            TimelineBlockEventLink,
            EventRawLogLink
        )
        print("✓ All models imported successfully")
    except ImportError as e:
        print(f"✗ Model import failed: {e}")
        return False
    
    return True


def test_services_import():
    """Test that all new services can be imported."""
    print("Testing service imports...")
    
    try:
        from lifelog.services.chunking import (
            TimelineChunkingService,
            EventChunk,
            ChunkBudget
        )
        from lifelog.services.timeline_generation import (
            TimelineGenerationService
        )
        print("✓ All services imported successfully")
    except ImportError as e:
        print(f"✗ Service import failed: {e}")
        return False
    
    return True


def test_actor_import():
    """Test that enricher actor can be imported."""
    print("Testing actor imports...")
    
    try:
        from lifelog.actors.enrichers import TimelineEnricher
        print("✓ TimelineEnricher actor imported successfully")
    except ImportError as e:
        print(f"✗ Actor import failed: {e}")
        return False
    
    return True


def test_api_import():
    """Test that API endpoints can be imported."""
    print("Testing API imports...")
    
    try:
        from lifelog.api.timeline_blocks import router
        print("✓ Timeline blocks API imported successfully")
    except ImportError as e:
        print(f"✗ API import failed: {e}")
        return False
    
    return True


def test_scheduler_import():
    """Test that scheduler can be imported."""
    print("Testing scheduler imports...")
    
    try:
        from lifelog.core.scheduler import (
            ScheduledTaskRunner,
            get_scheduler,
            start_scheduler,
            stop_scheduler
        )
        print("✓ Scheduler imported successfully")
    except ImportError as e:
        print(f"✗ Scheduler import failed: {e}")
        return False
    
    return True


def main():
    """Run all tests."""
    print("=" * 60)
    print("Timeline Generation Component Tests")
    print("=" * 60)
    print()
    
    # Track failures
    failed = []
    
    # Import tests (most critical)
    tests = [
        ("Models", test_models_import),
        ("Services", test_services_import),
        ("Actor", test_actor_import),
        ("API", test_api_import),
        ("Scheduler", test_scheduler_import),
    ]
    
    for name, test_func in tests:
        try:
            if not test_func():
                failed.append(name)
        except Exception as e:
            print(f"✗ {name} test failed with exception: {e}")
            failed.append(name)
        print()
    
    # Unit tests (require successful imports)
    if not failed:
        unit_tests = [
            test_chunk_budget,
            test_event_chunk,
            test_prompt_template,
            test_token_estimation,
        ]
        
        for test_func in unit_tests:
            try:
                test_func()
                print()
            except Exception as e:
                print(f"✗ Test failed with exception: {e}")
                import traceback
                traceback.print_exc()
                failed.append(test_func.__name__)
                print()
    
    # Summary
    print("=" * 60)
    if failed:
        print(f"FAILED: {len(failed)} test(s) failed:")
        for name in failed:
            print(f"  - {name}")
        return 1
    else:
        print("SUCCESS: All tests passed! ✓")
        return 0


if __name__ == "__main__":
    sys.exit(main())
