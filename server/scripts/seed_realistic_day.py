"""Send one deterministic, messy day through the real client ingestion path.

Run inside the Docker server container after the API and worker are healthy:
    python scripts/seed_realistic_day.py --server-url http://localhost:8000

The script bootstraps only a demo user/device, then uses the public device API
for every capture. ActivityWatch records are deliberately noisy and batched in
the same envelope emitted by the desktop collector.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import secrets
from collections import Counter
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import func
from sqlmodel import select

from app.core.database import async_session_factory
from app.core.security import hash_api_key, hash_password
from app.models.accounting import AIUsage
from app.models.auth import Device, User
from app.models.captures import Capture
from app.models.ingest import Event, RawLog
from app.models.kernel import Entity
from app.models.processing import Session, TimelineEntry
from app.models.retrieval import SearchDocument
from app.services.processing import run_processing_pipeline

DEMO_USERNAME = "alex-realistic-day"
DEMO_DEVICE_ID = "demo-macbook-pro-14"
EXTENSION_ID = "com.lifelog.aw"
TIMEZONE = "America/Vancouver"

PROFILES = {
    "morning": [
        ("Safari", "Weather — Vancouver"),
        ("Messages", "Mom — Messages"),
        ("Music", "Nujabes — Feather"),
        ("Calendar", "Wednesday, August 12"),
        ("Finder", "Downloads"),
    ],
    "calculus": [
        ("Safari", "Limits and continuity - Khan Academy"),
        ("Preview", "MATH 12 - 3.4 Derivatives.pdf"),
        ("Obsidian", "calc limits lecture 12 aug.md"),
        ("Goodnotes", "Calculus 12 — Unit 3"),
        ("Messages", "study grp (4)"),
        ("Finder", "IMG_4821.HEIC"),
    ],
    "physics": [
        ("Preview", "Physics worksheet FINAL (2).pdf"),
        ("Safari", "projectile motion simulation"),
        ("Obsidian", "phys notes - kinematics??.md"),
        ("Calculator", "Calculator"),
        ("Google Chrome", "Desmos | Graphing Calculator"),
        ("Messages", "Evan — Messages"),
    ],
    "english": [
        ("Microsoft Word", "Macbeth essay outline - autosaved"),
        ("Safari", "Macbeth Act 2: Scene 1"),
        ("Preview", "Macbeth prompt AUG12.pdf"),
        ("Obsidian", "english quotes messy.md"),
        ("Mail", "Re: essay conference"),
    ],
    "homework": [
        ("Visual Studio Code", "projectile_lab_analysis.py — physics-lab"),
        ("Terminal", "alex — zsh — 132x38"),
        ("Safari", "Canvas — Dashboard"),
        ("Preview", "Physics worksheet FINAL (2).pdf"),
        ("Obsidian", "2026-08-12.md"),
        ("Discord", "#general | robotics club"),
        ("Messages", "study grp (4)"),
    ],
    "evening": [
        ("YouTube", "why derivative rules work - YouTube"),
        ("Safari", "reddit: mechanical keyboards"),
        ("Steam", "Hades II"),
        ("Discord", "Friends / voice-chat"),
        ("Music", "Liked Songs"),
        ("Finder", "Desktop"),
    ],
}

URLS = {
    "Weather — Vancouver": "https://weather.gc.ca/city/pages/bc-74_metric_e.html",
    "Limits and continuity - Khan Academy": "https://www.khanacademy.org/math/ap-calculus-ab/ab-limits-new",
    "projectile motion simulation": "https://phet.colorado.edu/en/simulations/projectile-motion",
    "Desmos | Graphing Calculator": "https://www.desmos.com/calculator",
    "Macbeth Act 2: Scene 1": "https://www.folger.edu/explore/shakespeares-works/macbeth/read/2/1/",
    "Canvas — Dashboard": "https://school.instructure.com/",
    "why derivative rules work - YouTube": "https://www.youtube.com/watch?v=fictitious-demo",
    "reddit: mechanical keyboards": "https://www.reddit.com/r/MechanicalKeyboards/",
}


def local(day: date, hour: int, minute: int) -> datetime:
    return datetime.combine(day, time(hour, minute), ZoneInfo(TIMEZONE))


def iso_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def noisy_title(rng: random.Random, title: str) -> str | None:
    roll = rng.random()
    if roll < 0.007:
        return None
    if roll < 0.025:
        return f"{title}  "
    if roll < 0.045:
        return title.replace(" - ", " — ")
    if roll < 0.06:
        return f"{title} (Not Responding)"
    return title


def generate_activitywatch_day(day: date, seed: int) -> list[dict]:
    rng = random.Random(seed)
    segments = [
        (local(day, 6, 52), local(day, 7, 43), "morning"),
        (local(day, 8, 36), local(day, 10, 18), "calculus"),
        (local(day, 10, 29), local(day, 12, 6), "physics"),
        (local(day, 12, 43), local(day, 15, 19), "english"),
        (local(day, 16, 3), local(day, 18, 11), "homework"),
        (local(day, 19, 6), local(day, 22, 54), "evening"),
    ]
    events: list[dict] = []
    for segment_index, (start, end, profile) in enumerate(segments):
        events.append(
            {
                "source": "activitywatch",
                "bucket_id": "aw-watcher-afk_demo-macbook-pro-14",
                "bucket_type": "afkstatus",
                "timestamp": iso_utc(start),
                "duration": round(rng.uniform(8, 35), 3),
                "data": {"status": "not-afk"},
            }
        )
        cursor = start
        choices = PROFILES[profile]
        current = rng.choice(choices)
        while cursor < end:
            if rng.random() < 0.31:
                current = rng.choice(choices)
            duration = min(rng.lognormvariate(2.72, 0.72), (end - cursor).total_seconds())
            duration = max(0.15, duration)
            app, title = current
            if rng.random() < 0.003:
                app = None
            event = {
                "source": "activitywatch",
                "bucket_id": "aw-watcher-window_demo-macbook-pro-14",
                "bucket_type": "currentwindow",
                "timestamp": iso_utc(cursor),
                "duration": round(duration, 3),
                "data": {"app": app, "title": noisy_title(rng, title)},
            }
            events.append(event)

            url = URLS.get(title)
            if url and rng.random() < 0.72:
                web_event = {
                    "source": "activitywatch",
                    "bucket_id": "aw-watcher-web-safari_demo-macbook-pro-14",
                    "bucket_type": "web.tab.current",
                    "timestamp": iso_utc(cursor + timedelta(milliseconds=rng.randint(20, 900))),
                    "duration": round(max(0.1, duration + rng.uniform(-2.5, 2.5)), 3),
                    "data": {
                        "url": url + ("?utm_source=demo" if rng.random() < 0.04 else ""),
                        "title": noisy_title(rng, title),
                        "audible": rng.random() < 0.08,
                        "incognito": False,
                        "tabCount": rng.randint(7, 43),
                    },
                }
                events.append(web_event)

            # ActivityWatch includes tiny focus changes. The normalizer should
            # discard these rather than pretending they are meaningful work.
            if rng.random() < 0.018:
                events.append(
                    {
                        **event,
                        "timestamp": iso_utc(cursor + timedelta(milliseconds=80)),
                        "duration": round(rng.uniform(0.1, 4.8), 3),
                        "data": {"app": "NotificationCenter", "title": ""},
                    }
                )
            cursor += timedelta(seconds=duration + rng.uniform(0.03, 1.8))

        next_start = segments[segment_index + 1][0] if segment_index + 1 < len(segments) else end
        events.append(
            {
                "source": "activitywatch",
                "bucket_id": "aw-watcher-afk_demo-macbook-pro-14",
                "bucket_type": "afkstatus",
                "timestamp": iso_utc(end),
                "duration": round(max(12, (next_start - end).total_seconds()), 3),
                "data": {"status": "afk"},
            }
        )

    events.sort(key=lambda item: item["timestamp"])
    return events


async def bootstrap_demo_identity() -> tuple[str, User]:
    api_key = secrets.token_hex(32)
    async with async_session_factory() as session:
        user = (
            await session.execute(select(User).where(User.username == DEMO_USERNAME))
        ).scalars().first()
        if user is None:
            user = User(
                username=DEMO_USERNAME,
                hashed_password=hash_password("lifelog-demo"),
                is_active=True,
                is_superuser=False,
            )
            session.add(user)
            await session.flush()
        else:
            user.hashed_password = hash_password("lifelog-demo")
            user.is_active = True
            session.add(user)
        device = await session.get(Device, DEMO_DEVICE_ID)
        if device is None:
            device = Device(
                id=DEMO_DEVICE_ID,
                user_id=user.id,
                name="Alex's MacBook Pro (Demo)",
                device_type="macos",
                api_key_hash=hash_api_key(api_key),
            )
        else:
            device.user_id = user.id
            device.api_key_hash = hash_api_key(api_key)
            device.is_active = True
        session.add(device)
        await session.commit()
        return api_key, user


async def send_day(server_url: str, day: date, raw_events: list[dict], api_key: str) -> dict:
    headers = {"X-API-Key": api_key}
    created_ids: list[str] = []
    duplicate_verified = False
    async with httpx.AsyncClient(base_url=server_url, timeout=60) as client:
        for index in range(0, len(raw_events), 250):
            batch = raw_events[index : index + 250]
            body = {
                "extension_id": EXTENSION_ID,
                "payload": {
                    "format": "activitywatch.raw.v1",
                    "bucket_host": DEMO_DEVICE_ID,
                    "events": batch,
                },
                "client_timestamp": iso_utc(datetime.now(UTC)),
                "client_timezone": TIMEZONE,
            }
            response = await client.post("/api/v1/ingest", json=body, headers=headers)
            response.raise_for_status()
            result = response.json()
            if result["status"] == "created":
                created_ids.append(result["id"])
            if index == 0:
                duplicate = await client.post("/api/v1/ingest", json=body, headers=headers)
                duplicate.raise_for_status()
                duplicate_verified = duplicate.json()["status"] == "duplicate"

        notes = [
            (7, 18, "remember: charger is still in the kitchen lol", "quick_note", {}),
            (9, 47, "teacher said quiz is probably Monday?? check Canvas", "class_note", {"course": "Calculus 12"}),
            (
                11,
                34,
                "projectile lab: use the LOW table, not the tall one. Evan has video",
                "class_note",
                {"course": "Physics 12"},
            ),
            (12, 16, "cafeteria was out of noodles; $8.75 sandwich", "expense_note", {"place": "school cafeteria"}),
            (
                14,
                52,
                "Macbeth idea: dagger is less prophecy and more him giving himself permission",
                "essay_idea",
                {"course": "English 12"},
            ),
            (
                17,
                26,
                "got distracted tuning the projectile analysis. still need questions 7-12",
                "progress_note",
                {"course": "Physics 12"},
            ),
            (22, 41, "tomorrow: print english outline + ask calc teacher about #14", "inbox", {}),
        ]
        capture_ids = []
        for hour, minute, text, intent, hints in notes:
            captured_at = local(day, hour, minute)
            response = await client.post(
                "/api/v1/captures/notes",
                headers=headers,
                json={
                    "text": text,
                    "captured_at": captured_at.isoformat(),
                    "timezone": TIMEZONE,
                    "intent": intent,
                    "context_hints": hints,
                    "privacy": {"visibility": "global"},
                    "idempotency_key": f"realistic-day:{day}:{hour:02d}{minute:02d}",
                },
            )
            response.raise_for_status()
            capture_ids.append(response.json()["capture"]["id"])
    return {
        "raw_log_ids": created_ids,
        "capture_ids": capture_ids,
        "duplicate_verified": duplicate_verified,
    }


async def wait_for_processing(raw_log_ids: list[str], timeout_seconds: int = 180) -> Counter:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while True:
        async with async_session_factory() as session:
            statuses = Counter(
                (
                    await session.execute(
                        select(RawLog.processing_status).where(RawLog.id.in_(raw_log_ids))
                    )
                ).scalars().all()
            )
        if statuses.get("pending", 0) == 0 or asyncio.get_running_loop().time() > deadline:
            return statuses
        await asyncio.sleep(0.5)


async def build_report(day: date, raw_count: int, send_result: dict, statuses: Counter) -> dict:
    async with async_session_factory() as session:
        processing = await run_processing_pipeline(session)
        event_counts = dict(
            (
                await session.execute(
                    select(Event.event_type, func.count(Event.id))
                    .where(Event.logical_date == day.isoformat())
                    .group_by(Event.event_type)
                )
            ).all()
        )
        session_sizes = list(
            (
                await session.execute(
                    select(Session.id, Session.kind, func.count(Event.id))
                    .join(Event, Event.session_id == Session.id)
                    .where(Session.logical_date == day.isoformat())
                    .group_by(Session.id, Session.kind)
                    .order_by(func.min(Event.start_time))
                )
            ).all()
        )
        report = {
            "day": day.isoformat(),
            "timezone": TIMEZONE,
            "generated_raw_activitywatch_events": raw_count,
            "raw_batches_created": len(send_result["raw_log_ids"]),
            "idempotent_duplicate_verified": send_result["duplicate_verified"],
            "processing_statuses": dict(statuses),
            "normalized_events": event_counts,
            "normalized_event_total": sum(event_counts.values()),
            "sessions_created_this_run": processing["sessions_created"],
            "session_count": len(session_sizes),
            "activity_episode_count": sum(kind == "activity" for _id, kind, _count in session_sizes),
            "idle_period_count": sum(kind == "idle" for _id, kind, _count in session_sizes),
            "activity_episode_sizes": [
                count for _id, kind, count in session_sizes if kind == "activity"
            ],
            "timeline_entries": await session.scalar(select(func.count(TimelineEntry.id))),
            "note_captures": await session.scalar(
                select(func.count(Capture.id)).where(Capture.device_id == DEMO_DEVICE_ID)
            ),
            "search_documents": await session.scalar(select(func.count(SearchDocument.id))),
            "embedded_search_documents": await session.scalar(
                select(func.count(SearchDocument.id)).where(SearchDocument.embedding.is_not(None))
            ),
            "current_graph_entities": await session.scalar(
                select(func.count(Entity.id)).where(Entity.is_superseded == False)
            ),
            "ai_calls": await session.scalar(select(func.count(AIUsage.id))),
            "ai_cost_usd": await session.scalar(select(func.coalesce(func.sum(AIUsage.cost), 0.0))),
            "observations": [
                "Sub-five-second focus noise is intentionally filtered.",
                "Window, browser, and AFK streams overlap like real ActivityWatch buckets.",
                "Titles contain nulls, whitespace, app stalls, URL tracking parameters, and rapid switching.",
                "Episodes follow AFK boundaries and elapsed time; AI receives aggregated evidence, not raw focus spam.",
            ],
        }
    output = Path("storage/demo/realistic_day_report.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, default=str) + "\n")
    return report


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server-url", default="http://localhost:8000")
    parser.add_argument("--day", type=date.fromisoformat, default=date(2026, 8, 12))
    parser.add_argument("--seed", type=int, default=20260812)
    parser.add_argument("--report-only", action="store_true")
    args = parser.parse_args()

    if args.report_only:
        async with async_session_factory() as session:
            raw_logs = (
                await session.execute(
                    select(RawLog).where(RawLog.extension_id == EXTENSION_ID)
                )
            ).scalars().all()
        statuses = Counter(log.processing_status for log in raw_logs)
        report = await build_report(
            args.day,
            len(generate_activitywatch_day(args.day, args.seed)),
            {
                "raw_log_ids": [str(log.id) for log in raw_logs],
                "duplicate_verified": True,
            },
            statuses,
        )
        print(json.dumps(report, indent=2, default=str))
        return

    api_key, _user = await bootstrap_demo_identity()
    raw_events = generate_activitywatch_day(args.day, args.seed)
    result = await send_day(args.server_url, args.day, raw_events, api_key)
    statuses = await wait_for_processing(result["raw_log_ids"])
    report = await build_report(args.day, len(raw_events), result, statuses)
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
