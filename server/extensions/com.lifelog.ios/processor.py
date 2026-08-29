from typing import Any

ALLOWED_TYPES = {
    "location",
    "visit",
    "motion",
    "steps",
    "health",
    "calendar",
    "reminder",
    "connectivity",
    "battery",
    "power",
    "photo_library",
    "contact",
    "bluetooth",
}


def normalize(payload: dict[str, Any] | list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize already-structured, device-observed iOS signals."""
    if isinstance(payload, dict) and isinstance(payload.get("events"), list):
        records = payload["events"]
    else:
        records = payload if isinstance(payload, list) else [payload]
    normalized = []
    for record in records:
        if not isinstance(record, dict):
            continue
        event_type = str(record.get("type", "")).strip().lower()
        if event_type not in ALLOWED_TYPES:
            continue
        data = record.get("data") if isinstance(record.get("data"), dict) else {}
        normalized.append(
            {
                "type": event_type,
                "data": {
                    **data,
                    "external_id": record.get("id"),
                    "start_time": record.get("start_time"),
                    "end_time": record.get("end_time"),
                    "source": data.get("source", "lifelog_ios"),
                    "observation_kind": "direct",
                },
            }
        )
    return normalized
