from datetime import UTC, datetime

from app.services.chat_context import (
    format_conversation_history,
    needs_tool_planning,
    parse_temporal_scope,
)


def test_yesterday_uses_client_timezone_and_cleans_retrieval_query():
    scope = parse_temporal_scope(
        "What did I work on yesterday?",
        timezone_name="America/Vancouver",
        now=datetime(2026, 8, 13, 12, tzinfo=UTC),
    )

    assert scope is not None
    assert scope.logical_from == "2026-08-12"
    assert scope.logical_until == "2026-08-13"
    assert scope.occurred_from == datetime(2026, 8, 12, 7)
    assert scope.search_query == "What did I work on"


def test_explicit_date_and_invalid_timezone_are_safe():
    scope = parse_temporal_scope(
        "Show calculus on 2026-02-03",
        timezone_name="not/a-zone",
    )

    assert scope is not None
    assert scope.logical_from == "2026-02-03"
    assert scope.occurred_from == datetime(2026, 2, 3)


def test_tool_planner_is_only_used_for_deterministic_intents():
    assert not needs_tool_planning("What do my Macbeth notes say?")
    assert needs_tool_planning("How much time did I spend on calculus?")
    assert needs_tool_planning("What unfinished work do I have?")


def test_history_is_bounded_and_labeled():
    history = [("user", f"message {index}") for index in range(20)]
    rendered = format_conversation_history(history)

    assert "message 7" not in rendered
    assert "message 8" in rendered
    assert "User: message 19" in rendered
