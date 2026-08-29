from app.loader.runner import run_normalization


def test_ios_signal_normalizer_preserves_observation_and_identity():
    events = run_normalization(
        "com.lifelog.ios",
        {
            "id": "5312A722-730F-42F6-8F47-6A2DF4F5F39C",
            "type": "visit",
            "start_time": "2026-08-13T09:12:00Z",
            "end_time": "2026-08-13T10:04:00Z",
            "data": {
                "latitude": "49.2827",
                "longitude": "-123.1207",
                "source": "core_location_visit",
            },
        },
    )

    assert events == [
        {
            "type": "visit",
            "data": {
                "latitude": "49.2827",
                "longitude": "-123.1207",
                "source": "core_location_visit",
                "external_id": "5312A722-730F-42F6-8F47-6A2DF4F5F39C",
                "start_time": "2026-08-13T09:12:00Z",
                "end_time": "2026-08-13T10:04:00Z",
                "observation_kind": "direct",
            },
        }
    ]


def test_ios_signal_normalizer_drops_unknown_signal_types():
    assert run_normalization("com.lifelog.ios", {"type": "raw_keystrokes", "data": {}}) == []


def test_ios_signal_normalizer_accepts_batched_device_observations():
    events = run_normalization(
        "com.lifelog.ios",
        {
            "format": "lifelog.ios.signal-batch.v1",
            "events": [
                {
                    "id": "battery-1",
                    "type": "battery",
                    "start_time": "2026-08-21T17:00:00Z",
                    "data": {"level": "0.74", "source": "ios_device"},
                },
                {"id": "unsafe-1", "type": "raw_keystrokes", "data": {}},
            ],
        },
    )

    assert len(events) == 1
    assert events[0]["type"] == "battery"
    assert events[0]["data"]["external_id"] == "battery-1"
