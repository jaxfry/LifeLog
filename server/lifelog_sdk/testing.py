import inspect
from collections.abc import Callable
from typing import Any

from lifelog_sdk.contracts import EventEnvelope, PollContext, PollPage


async def run_poller_contract(
    poll: Callable[[dict[str, Any]], Any],
    context: PollContext,
) -> PollPage:
    """Execute and validate an adapter exactly as the base runtime will."""
    raw = poll(context.model_dump())
    if inspect.isawaitable(raw):
        raw = await raw
    return PollPage.model_validate(raw)


def validate_normalizer(
    normalize: Callable[[dict[str, Any]], list[dict[str, Any]]],
    payload: dict[str, Any],
) -> list[EventEnvelope]:
    return [EventEnvelope.model_validate(item) for item in normalize(payload)]


def assert_no_secret_echo(page: PollPage, context: PollContext) -> None:
    serialized = page.model_dump_json()
    leaked = [key for key, value in context.secrets.items() if value and value in serialized]
    if leaked:
        raise AssertionError(f"Poll result leaked secret values for keys: {', '.join(leaked)}")
