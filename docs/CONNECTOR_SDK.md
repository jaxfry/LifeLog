# LifeLog Connector SDK

Ordinary source adapters use the `lifelog_sdk` package. They acquire proprietary
records and normalize them; they do not implement storage, retries, OCR,
transcription, memory, privacy, retrieval, commitments, or chat.

```python
from lifelog_sdk import PollContext, PollPage, SourceRecord


async def poll(runtime: dict) -> dict:
    context = PollContext.model_validate(runtime)
    token = context.require_secret("access_token")
    cursor = context.checkpoint_for("assignments").get("cursor")
    rows, next_cursor = await fetch_assignments(token, cursor)
    return PollPage(
        records=[
            SourceRecord.replace(
                f"assignment:{row['id']}",
                row,
                revision=row.get("updated_at"),
            )
            for row in rows
        ],
        checkpoint_stream="assignments",
        next_checkpoint={"cursor": next_cursor},
        has_more=bool(next_cursor),
    ).model_dump()
```

Use `lifelog_sdk.testing.run_poller_contract`, `validate_normalizer`, and
`assert_no_secret_echo` in connector tests. `stable_revision()` provides a
canonical content revision when a source lacks one.

Manifests may contribute optional declarative `life_areas` templates containing
vocabulary, recognition hints, cards, suggested questions, and policies. A
template never creates another memory store or bypasses base privacy policy.
