from typing import Any


def normalize(payload: dict[str, Any] | list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Normalizes the raw payload from the ActivityWatch collector.
    """
    if isinstance(payload, dict) and isinstance(payload.get("events"), list):
        raw_events = payload["events"]
    elif isinstance(payload, list):
        raw_events = payload
    else:
        raw_events = [payload]

    normalized_events = []

    for raw_event in raw_events:
        # Compatibility for clients that performed normalization locally.
        if raw_event.get("type") and isinstance(raw_event.get("data"), dict):
            normalized_events.append(raw_event)
            continue
        # Filter out short events (noise)
        duration = raw_event.get("duration", 0)
        if duration < 5:
            continue

        bucket_type = raw_event.get("bucket_type", "unknown")
        bucket_id = raw_event.get("bucket_id", "")
        raw_inner_data = raw_event.get("data", {})

        event_type = "unknown"
        normalized_data = {
            "start_time": raw_event.get("timestamp"),
            "duration": raw_event.get("duration"),
            "source": "activitywatch"
        }

        if "window" in bucket_type or "window" in bucket_id:
            event_type = "app_usage"
            normalized_data["app"] = raw_inner_data.get("app")
            normalized_data["title"] = raw_inner_data.get("title")

        elif "afk" in bucket_type or "afk" in bucket_id:
            event_type = "device_status"
            normalized_data["status"] = raw_inner_data.get("status") # 'afk' or 'not-afk'

        elif "web" in bucket_type or "browser" in bucket_id:
            event_type = "browsing"
            normalized_data["url"] = raw_inner_data.get("url")
            normalized_data["title"] = raw_inner_data.get("title")

        else:
            # Fallback for unknown types, keep raw data to debug
            normalized_data["raw"] = raw_inner_data

        normalized_events.append({
            "type": event_type,
            "data": normalized_data
        })

    return normalized_events
