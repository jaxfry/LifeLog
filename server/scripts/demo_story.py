"""Messy real-world demo: one school week through the real LifeLog pipeline.

Runs against a throwaway SQLite database and prints each processing stage.
Not a test; a narrated walkthrough. Delete demo_story.db afterwards.
"""

# ruff: noqa: E501 - narration script, long print lines are intentional

import asyncio
import os
from datetime import datetime

os.environ.setdefault("SECRET_KEY", "demo-secret-key-for-the-story")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///demo_story.db")

import sqlalchemy as sa
from sqlalchemy.dialects import sqlite as sqlite_dialect
from sqlmodel import SQLModel, select

_sqlite_compiler = sqlite_dialect.base.SQLiteTypeCompiler
_sqlite_compiler.visit_JSONB = _sqlite_compiler.visit_JSON
try:
    from pgvector.sqlalchemy import Vector  # noqa: F401

    _sqlite_compiler.visit_VECTOR = _sqlite_compiler.visit_JSON
except ImportError:
    pass

from app.core.logger import setup_logging
from app.models.auth import User
from app.models.config import Extension
from app.models.context import LifeArea
from app.models.files import Commitment
from app.models.kernel import Entity, Measurement, Relation
from app.models.retrieval import SearchDocument
from app.models.sources import SourceConnection
from app.services.context import link_target, recognize_areas
from app.services.ingestion import ingest_log
from app.services.tools import execute_tool

setup_logging()
import logging

logging.getLogger("app").setLevel(logging.WARNING)
DB_FILE = "demo_story.db"

T = lambda h, m=0, d=7: datetime(2026, 9, d, h, m, 0)  # noqa: E731

SCHOOL_MANIFEST = {
    "id": "com.lifelog.school",
    "version": "1.0.0",
    "api_version": "2",
    "capabilities": ["collector", "normalizer"],
    "permissions": ["network"],
    "entity_mappings": [
        {
            "event_type": "assignment",
            "entity_ref": "course",
            "entity_type": "course",
            "name_path": "course.name",
            "aliases_path": "course.aliases",
        },
        {
            "event_type": "grade",
            "entity_ref": "course",
            "entity_type": "course",
            "name_path": "course.name",
        },
        {
            "event_type": "study_session",
            "entity_ref": "course",
            "entity_type": "course",
            "name_path": "course_name",
        },
        {
            "event_type": "meeting",
            "entity_ref": "course",
            "entity_type": "course",
            "name_path": "course_name",
        },
        {
            "event_type": "meeting",
            "entity_ref": "person",
            "entity_type": "person",
            "name_path": "person",
        },
    ],
    "relation_mappings": [
        {
            "event_type": "study_session",
            "subject": "record",
            "predicate": "studied_for",
            "object": "entity",
            "object_entity_ref": "course",
        },
        {
            "event_type": "meeting",
            "subject": "record",
            "predicate": "met_with",
            "object": "entity",
            "object_entity_ref": "person",
        },
        {
            "event_type": "meeting",
            "subject": "record",
            "predicate": "for_course",
            "object": "entity",
            "object_entity_ref": "course",
        },
    ],
    "measurement_mappings": [
        {
            "event_type": "grade",
            "entity_ref": "course",
            "metric": "score",
            "value_path": "score",
            "unit_path": "score_unit",
        }
    ],
    "commitment_mappings": [
        {
            "event_type": "assignment",
            "title_path": "title",
            "due_at_path": "due_at",
            "description_path": "description",
        }
    ],
    "life_areas": [
        {
            "slug": "school",
            "name": "School",
            "recognition_hints": ["calculus", "assignment", "whiteboard", "homework"],
        }
    ],
}


def school_normalize(payload: dict):
    """Mock school connector: maps proprietary envelopes into normalized events."""
    kind = payload["kind"]
    if kind == "assignment":
        return [{
            "type": "assignment",
            "data": {
                "title": payload["title"],
                "course": {"name": payload["course"], "aliases": payload.get("aliases", [])},
                "due_at": payload["due_at"],
                "description": payload.get("description", ""),
                "timestamp": payload["due_at"],
            },
        }]
    if kind == "grade":
        return [{
            "type": "grade",
            "data": {
                "course": {"name": payload["course"]},
                "score": payload["score"],
                "score_unit": "percent",
                "timestamp": payload["timestamp"],
            },
        }]
    if kind == "study":
        return [{
            "type": "study_session",
            "data": {
                "course_name": payload["course"],
                "duration": payload["minutes"] * 60,
                "timestamp": payload["timestamp"],
            },
        }]
    if kind == "meeting":
        return [{
            "type": "meeting",
            "data": {
                "person": payload["person"],
                "course_name": payload.get("course"),
                "duration": payload["minutes"] * 60,
                "timestamp": payload["timestamp"],
            },
        }]
    return []


def fake_normalizer(extension_id: str, payload: dict):
    if extension_id == "com.lifelog.aw":
        from app.loader.runner import run_normalization as real

        return real(extension_id, payload)
    return school_normalize(payload)


def say(title: str, body: str = "") -> None:
    print(f"\n=== {title} ===")
    if body:
        print(body)


async def main() -> None:
    engine = sa.create_engine(f"sqlite:///{DB_FILE}")
    SQLModel.metadata.create_all(engine)
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    async_engine = create_async_engine(f"sqlite+aiosqlite:///{DB_FILE}")
    async_session = sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

    import app.workers.process as process_module

    process_module.run_normalization = fake_normalizer
    from app.workers.process import process_log

    async with async_session() as s:
        alex = User(username="alex", hashed_password="x")
        s.add(alex)
        await s.flush()
        s.add(
            Extension(
                id="com.lifelog.school",
                version="1.0.0",
                config=SCHOOL_MANIFEST,
                is_active=True,
            )
        )
        s.add(
            Extension(
                id="com.lifelog.aw",
                version="1.0.5",
                config={"id": "com.lifelog.aw", "version": "1.0.5"},
                is_active=True,
            )
        )
        canvas = SourceConnection(
            user_id=alex.id, extension_id="com.lifelog.school", name="School Canvas", config={}
        )
        s.add(canvas)
        await s.flush()
        s.add(LifeArea(user_id=alex.id, slug="school", name="School", definition=SCHOOL_MANIFEST["life_areas"][0]))
        await s.commit()
        say("Setup", "Alex exists; com.lifelog.school installed with fact/entity/measurement/commitment mappings; Canvas connection + School Life Area created.")

        # ---------------------------------------------------------------- Monday
        say("MONDAY — messy day")
        say("1a. Alex uses Firefox, then browses Khan Academy (real ActivityWatch processor)")
        aw_payload = [
            {"bucket_type": "window", "bucket_id": "aw-watcher-window", "timestamp": "2026-09-07T09:00:00Z", "duration": 25.0, "data": {"app": "Firefox", "title": "Khan Academy"}},
            {"bucket_type": "web", "bucket_id": "aw-watcher-web-firefox", "timestamp": "2026-09-07T09:05:00Z", "duration": 40.0, "data": {"url": "https://www.khanacademy.org/math/calculus-1", "title": "Calculus"}},
            {"bucket_type": "window", "bucket_id": "aw-watcher-window", "timestamp": "2026-09-07T09:45:00Z", "duration": 12.0, "data": {"app": "Obsidian", "title": "notes.md"}},
        ]
        for raw in aw_payload:
            log, created = await ingest_log(s, device_id="desktop-1", extension_id="com.lifelog.aw", payload=raw)
            if created:
                events = await process_log(s, log.id)
                for e in events:
                    print(f"   -> event {e.event_type}: {e.data}")

        say("1b. Canvas sync #1: 'Problem Set 3' due Friday (Sep 11)")
        log, created = await ingest_log(
            s,
            device_id=f"source:{canvas.id}",
            extension_id="com.lifelog.school",
            source_connection_id=canvas.id,
            external_key="canvas:assignment:789",
            external_revision="r1",
            source_updated_at=T(8, 0, 7),
            update_policy="replace",
            payload={"kind": "assignment", "title": "Problem Set 3", "course": "Calculus 12", "aliases": ["MATH 210"], "due_at": "2026-09-11T23:59:00", "description": "Taylor series"},
        )
        await process_log(s, log.id)

        say("1c. Alex logs a 3h calculus study session (sloppily: 'calc 12')")
        log, created = await ingest_log(
            s, device_id="macbook", extension_id="com.lifelog.school",
            payload={"kind": "study", "course": "calc 12", "minutes": 180, "timestamp": "2026-09-07T19:00:00"},
        )
        await process_log(s, log.id)

        say("1c2. THE FIX IN ACTION — real-time lookalike detection")
        from app.models.context import ReviewItem
        items = (await s.execute(select(ReviewItem))).scalars().all()
        for item in items:
            if item.kind == "entity_merge":
                print(f"   -> Inbox: '{item.title}' (confidence={item.confidence}, reason={item.payload.get('matched')})")

        say("1d. Grade arrives: 92% on the calculus quiz (course spelled 'Calculus 12')")
        log, created = await ingest_log(
            s, device_id="macbook", extension_id="com.lifelog.school",
            payload={"kind": "grade", "course": "Calculus 12", "score": 92, "timestamp": "2026-09-07T20:00:00"},
        )
        await process_log(s, log.id)

        say("1e. Office hours with Prof. Chen")
        log, created = await ingest_log(
            s, device_id="macbook", extension_id="com.lifelog.school",
            payload={"kind": "meeting", "person": "Prof. Chen", "course": "Calculus 12", "minutes": 30, "timestamp": "2026-09-07T16:00:00"},
        )
        await process_log(s, log.id)

        say("1e2. Another study session, logged as the alias 'MATH 210' (2h, Sunday night)")
        log, created = await ingest_log(
            s, device_id="macbook", extension_id="com.lifelog.school",
            payload={"kind": "study", "course": "MATH 210", "minutes": 120, "timestamp": "2026-09-06T20:00:00"},
        )
        await process_log(s, log.id)

        say("1f. Alex snaps a whiteboard photo with a hint (note capture path)")
        areas = await recognize_areas(s, alex.id, "Whiteboard notes: Taylor series homework")
        print(f"   recognized areas: {[(a.name, c) for a, c in areas]}")
        if areas:
            area = areas[0][0]
            await link_target(s, area.id, "capture", __import__("uuid").uuid4(), source="recognition_rule", confidence=0.9)
            print(f"   linked a capture to Life Area '{area.name}' (recognition_rule, 0.9)")
        await s.commit()

        # ---------------------------------------------------------------- Wednesday
        say("WEDNESDAY — the consequential change")
        say("2a. Canvas re-syncs the SAME assignment — deadline moved to Monday Sep 14")
        log, created = await ingest_log(
            s,
            device_id=f"source:{canvas.id}",
            extension_id="com.lifelog.school",
            source_connection_id=canvas.id,
            external_key="canvas:assignment:789",
            external_revision="r2",
            source_updated_at=T(9, 0, 9),
            update_policy="replace",
            payload={"kind": "assignment", "title": "Problem Set 3", "course": "Calculus 12", "aliases": ["MATH 210"], "due_at": "2026-09-14T23:59:00", "description": "Taylor series"},
        )
        await process_log(s, log.id)

        say("2b. Canvas re-sends the SAME r2 payload (flaky network)")
        log, created = await ingest_log(
            s,
            device_id=f"source:{canvas.id}",
            extension_id="com.lifelog.school",
            source_connection_id=canvas.id,
            external_key="canvas:assignment:789",
            external_revision="r2",
            source_updated_at=T(9, 0, 9),
            update_policy="replace",
            payload={"kind": "assignment", "title": "Problem Set 3", "course": "Calculus 12", "aliases": ["MATH 210"], "due_at": "2026-09-14T23:59:00", "description": "Taylor series"},
        )
        print(f"   dedupe: was_created={created} (expected False)")

        say("2c. Alex accepts the 'calc 12' merge suggestion (one click)")
        from app.services.inbox import decide_review_item
        merge_items = (await s.execute(select(ReviewItem).where(ReviewItem.kind == "entity_merge"))).scalars().all()
        for item in merge_items:
            if item.status == "pending":
                await decide_review_item(s, item, "accept")
                print(f"   -> accepted: '{item.title}'")
        await s.commit()
        print("   -> 'calc 12' is now an alias of 'Calculus 12'; future mentions resolve directly")

        # ---------------------------------------------------------------- What the system now knows
        say("WHAT THE SYSTEM NOW KNOWS — entities")
        entities = (await s.execute(select(Entity).order_by(Entity.entity_type, Entity.name))).scalars().all()
        for e in entities:
            print(f"   {e.entity_type:<12} {e.name!r:<22} canonical_key={e.canonical_key!r} aliases={e.data.get('aliases', []) if e.data else []}")

        say("Relations (current facts)")
        rels = (await s.execute(select(Relation).where(Relation.is_superseded == False).order_by(Relation.created_at))).scalars().all()
        name_map = {e.id: e.name for e in entities}
        for r in rels:
            subj = name_map.get(r.subject_id, "event")
            obj = name_map.get(r.object_id, "?")
            print(f"   {subj} --{r.predicate}--> {obj}  [{r.occurred_from} -> {r.occurred_until}] conf={r.confidence}")

        say("Measurements")
        for m in (await s.execute(select(Measurement))).scalars().all():
            print(f"   {m.metric}: {m.value}{m.unit} on {m.occurred_at} (entity={name_map.get(m.entity_id)})")

        say("Commitments + superseded chain")
        commitments = (await s.execute(select(Commitment).order_by(Commitment.created_at))).scalars().all()
        for c in commitments:
            state = f"SUPERSEDED by {c.superseded_by}" if c.superseded_by else c.status
            print(f"   '{c.title}' due {c.due_at} [{state}]")

        say("Review items (the Inbox)")
        from app.models.context import ReviewItem
        for item in (await s.execute(select(ReviewItem).order_by(ReviewItem.created_at))).scalars().all():
            print(f"   [{item.kind}] {item.title} (consequential={item.consequential}, status={item.status})")

        say("Search: 'Taylor'")
        docs = (
            await s.execute(
                select(SearchDocument)
                .where(SearchDocument.is_superseded == False, SearchDocument.content.ilike("%Taylor%"))
                .limit(5)
            )
        ).scalars().all()
        for d in docs:
            print(f"   {d.source_type}: {d.title or d.content[:60]}")

        say("TOOLS — chat with Alex")
        result = await execute_tool(
            s, user_id=alex.id, area_id=None, name="calculate_duration",
            arguments={"entity_name": "Calculus 12", "predicate": "studied_for",
                       "occurred_from": "2026-09-01T00:00:00", "occurred_until": "2026-09-09T00:00:00"},
        )
        print(f"   'How much did I study Calculus 12 this week?' -> {result}")

        say("2d. THE FIX VERIFIED — the fragment is folded in")
        from app.services.kernel import get_current_entity_by_name
        resolved = await get_current_entity_by_name(s, "course", "calc 12")
        print(f"   -> 'calc 12' now resolves to: {resolved.name if resolved else None} (id {resolved.id if resolved else None})")

        result = await execute_tool(
            s, user_id=alex.id, area_id=None, name="calculate_duration",
            arguments={"entity_name": "calc 12", "predicate": "studied_for",
                       "occurred_from": "2026-09-01T00:00:00", "occurred_until": "2026-09-09T00:00:00"},
        )
        print(f"   '...and for the sloppy 'calc 12' entity?' -> {result}")

        result = await execute_tool(
            s, user_id=alex.id, area_id=None, name="aggregate_measurements",
            arguments={"entity_name": "Calculus 12", "metric": "score"},
        )
        print(f"   'What's my Calculus grade?' -> {result}")

        result = await execute_tool(
            s, user_id=alex.id, area_id=None, name="list_deadlines", arguments={}
        )
        print(f"   'What's due?' -> {result}")

        result = await execute_tool(
            s, user_id=alex.id, area_id=None, name="propose_action",
            arguments={
                "summary": "Move the study block for Problem Set 3 to Thursday evening",
                "action": {"type": "reschedule_commitment", "commitment_title": "Problem Set 3", "new_due_at": "2026-09-17T20:00:00"},
                "consequential": False,
            },
        )
        print(f"   'Move my study session to Thursday' -> {result} (nothing executed yet)")

        say("PRIVACY — scoped chat")
        from app.models.context import ContextLink
        links = (await s.execute(select(ContextLink))).scalars().all()
        print(f"   Context links: {len(links)}")

    await async_engine.dispose()
    import os

    os.remove(DB_FILE)
    print("\nDemo complete. (DB deleted)")


if __name__ == "__main__":
    asyncio.run(main())
