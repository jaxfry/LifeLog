from typing import Any
from sqlmodel import select
from .. import models
from ..core.actors import ActorBase, ActorConfig, actor_registry
from ..dependencies import get_session


@actor_registry.register(
    ActorConfig(
        slug="test-processor",
        actor_type=models.ActorType.PROCESSOR,
        version="1.0.0",
    )
)
class TestProcessor(ActorBase):
    """
    Example processor for 'test-source' data. Expects a 'message' field.
    """

    async def run(self, data: models.RawLog) -> Any:
        raw_log = data
        print(f"--- Running 'test-processor' on raw_log_id: {raw_log.id} ---")

        # In a class-based actor, we can get a session when we need it.
        # This is a simplified example; a more robust solution might use a
        # context manager or dependency injection framework.
        session = await anext(get_session())

        # The actor's own metadata (like its DB `id`) would be passed in
        # during instantiation in a real scenario. For now, we'll look it up.
        statement = select(models.Actor).where(models.Actor.slug == "test-processor")
        actor = (await session.exec(statement)).one_or_none()
        if not actor:
            print("ERROR: Could not find self in database. Aborting.")
            return

        event_type_slug = "test-event"  # This processor knows what it creates
        statement = select(models.EventType).where(
            models.EventType.slug == event_type_slug
        )
        event_type = (await session.exec(statement)).one_or_none()

        if not event_type:
            print(f"ERROR: EventType '{event_type_slug}' not found. Cannot process.")
            # Log failure
            if actor and actor.id is not None:
                session.add(models.ActorProcessingLog(
                    actor_id=actor.id,
                    actor_version_at_processing=actor.version,
                    raw_log_id=raw_log.id,
                    status="FAILURE",
                    details={"reason": "missing_event_type", "expected": event_type_slug},
                ))
                await session.commit()
            return

        summary = raw_log.raw_data.get("message", "No message provided")

        if actor.id is None or event_type.id is None:
            print("ERROR: Actor or EventType ID is None. Cannot create event.")
            return

        new_event = models.Event(
            processor_actor_id=actor.id,
            start_time=raw_log.ingested_at,
            event_type_id=event_type.id,
            summary=summary,
        )

        new_event.raw_logs.append(raw_log)
        session.add(new_event)
        await session.commit()

        # Log success
        if actor.id is not None:
            session.add(models.ActorProcessingLog(
                actor_id=actor.id,
                actor_version_at_processing=actor.version,
                raw_log_id=raw_log.id,
                event_id=new_event.id,
                status="SUCCESS",
                details={"created_event_id": new_event.id},
            ))
            await session.commit()

        print(
            f"SUCCESS: Created Event (id={new_event.id}) from RawLog (id={raw_log.id})"
        )