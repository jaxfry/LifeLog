import difflib
import re
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from app.models.context import ReviewDecision, ReviewItem
from app.models.kernel import Entity, EntityAlias


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def upsert_review_item(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    kind: str,
    source_type: str,
    source_id: uuid.UUID,
    title: str,
    summary: str | None = None,
    payload: dict | None = None,
    consequential: bool = False,
    confidence: float | None = None,
    priority: str = "normal",
    expires_at: datetime | None = None,
    choices: list[dict] | None = None,
    capture_id: uuid.UUID | None = None,
    life_area_id: uuid.UUID | None = None,
) -> ReviewItem:
    item = (
        await session.execute(
            select(ReviewItem).where(
                ReviewItem.user_id == user_id,
                ReviewItem.source_type == source_type,
                ReviewItem.source_id == source_id,
            )
        )
    ).scalars().first()
    item = item or ReviewItem(
        user_id=user_id,
        kind=kind,
        source_type=source_type,
        source_id=source_id,
        title=title,
    )
    item.kind = kind
    item.title = title
    item.summary = summary
    item.payload = {**(item.payload or {}), **(payload or {})}
    item.consequential = consequential
    if confidence is not None:
        item.confidence = confidence
    item.priority = priority
    if expires_at is not None:
        item.expires_at = expires_at
    if choices is not None:
        item.choices = choices
    item.capture_id = capture_id
    item.life_area_id = life_area_id
    if item.status not in ("accepted", "rejected", "dismissed"):
        item.status = "pending"
    item.updated_at = _now()
    session.add(item)
    await session.flush()
    return item


async def decide_review_item(
    session: AsyncSession,
    item: ReviewItem,
    decision: str,
    value: dict | None = None,
) -> None:
    if item.status != "pending":
        raise ValueError("Review item has already been decided")
    value = value or {}
    choice_ids = [
        str(choice["id"])
        for choice in (item.choices or [])
        if choice.get("id") is not None
    ]
    if choice_ids and decision not in choice_ids:
        raise ValueError(f"decision must be one of {choice_ids}")
    if decision == "dismiss":
        item.status = "dismissed"
        if item.kind == "entity_merge":
            item.expires_at = _now() + timedelta(days=30)
    elif item.kind == "classification":
        from app.models.captures import Capture
        from app.services.jobs import refresh_capture_status

        capture = await session.get(Capture, item.source_id)
        if capture is None:
            raise ValueError("Capture no longer exists")
        if decision == "accept":
            label = str(value.get("label") or capture.classification.get("label") or "").strip()
            if not label:
                raise ValueError("Classification requires a label")
            capture.classification = {
                **capture.classification,
                "label": label,
                "confidence": 1.0,
                "needs_review": False,
                "source": "user_confirmation",
            }
            item.status = "accepted"
        elif decision == "reject":
            capture.classification = {
                **capture.classification,
                "needs_review": False,
                "rejected": True,
                "source": "user_rejection",
            }
            item.status = "rejected"
        else:
            raise ValueError("decision must be accept, reject, or dismiss")
        capture.updated_at = _now()
        session.add(capture)
        await refresh_capture_status(session, capture.id)
    elif item.kind == "memory_proposal":
        from app.services.artifacts import review_memory_proposal

        if decision not in ("accept", "reject"):
            raise ValueError("Memory proposals must be accepted or rejected")
        await review_memory_proposal(session, item.source_id, decision)
        item.status = "accepted" if decision == "accept" else "rejected"
    elif item.kind == "entity_merge":
        from app.services.kernel import merge_entities

        if decision == "accept":
            survivor_id = uuid.UUID(str(item.payload.get("survivor_id")))
            merged_id = uuid.UUID(str(item.payload.get("merged_id") or item.source_id))
            await merge_entities(
                session,
                survivor_id=survivor_id,
                merged_id=merged_id,
                decided_by_user_id=item.user_id,
                review_item_id=item.id,
            )
            item.status = "accepted"
            involved = {str(merged_id), str(survivor_id)}
            pending_merges = (
                await session.execute(
                    select(ReviewItem).where(
                        ReviewItem.kind == "entity_merge",
                        ReviewItem.status == "pending",
                        ReviewItem.user_id == item.user_id,
                    )
                )
            ).scalars().all()
            for other in pending_merges:
                if other.id == item.id:
                    continue
                other_merged = str(other.payload.get("merged_id") or other.source_id)
                if involved & {other_merged, str(other.payload.get("survivor_id"))}:
                    other.status = "dismissed"
                    other.decided_at = _now()
                    other.updated_at = _now()
                    session.add(other)
        elif decision == "reject":
            item.status = "rejected"
        else:
            raise ValueError("entity_merge decisions must be accept, reject, or dismiss")
    elif item.kind == "entity_resolution":
        from app.services.entity_resolution import accept_candidate, reject_mention

        if decision != "reject":
            candidate_id = value.get("entity_id") or decision
            resolved = await accept_candidate(
                session,
                owner_user_id=item.user_id,
                mention_id=item.source_id,
                candidate_entity_id=uuid.UUID(str(candidate_id)),
            )
            if resolved is None:
                raise ValueError("Entity candidate no longer exists")
            item.status = "accepted"
        else:
            if not await reject_mention(
                session,
                owner_user_id=item.user_id,
                mention_id=item.source_id,
            ):
                raise ValueError("Entity mention no longer exists")
            item.status = "rejected"
    elif item.kind == "claim_conflict":
        from app.services.reconciliation import decide_claim_conflict

        peer_ids = [
            uuid.UUID(str(peer_id))
            for peer_id in item.payload.get("conflicting_claim_ids", [])
        ]
        await decide_claim_conflict(
            session,
            owner_user_id=item.user_id,
            claim_id=item.source_id,
            decision=decision,
            conflicting_claim_ids=peer_ids,
        )
        item.status = "rejected" if decision == "keep_existing" else "accepted"
    elif item.kind == "proposed_action":
        action = item.payload.get("action") or {}
        action_type = action.get("type")
        if decision == "accept":
            handler = _ACTION_HANDLERS.get(action_type)
            if handler is None:
                raise ValueError(f"unsupported proposed action: {action_type!r}")
            await handler(session, action, item.user_id)
            item.status = "accepted"
        elif decision == "reject":
            item.status = "rejected"
        else:
            item.status = "dismissed"
    elif item.kind == "commitment_revision":
        from app.models.files import Commitment, Notification
        from app.services.commitments import reminder_time

        replacement = await session.get(Commitment, item.source_id)
        previous_id = item.payload.get("previous_commitment_id")
        previous = await session.get(Commitment, uuid.UUID(previous_id)) if previous_id else None
        if replacement is None or replacement.owner_user_id != item.user_id:
            raise ValueError("Replacement commitment no longer exists")
        if previous is not None and previous.owner_user_id != item.user_id:
            raise ValueError("Previous commitment no longer exists")
        if decision == "accept":
            replacement.status = item.payload.get("previous_status") or "planned"
            replacement.data = {**replacement.data, "requires_review": False}
            scheduled_for = reminder_time(replacement)
            if scheduled_for is not None:
                session.add(
                    Notification(
                        owner_user_id=replacement.owner_user_id,
                        commitment_id=replacement.id,
                        title=replacement.title,
                        body=replacement.description,
                        scheduled_for=scheduled_for,
                        payload={"type": "commitment_reminder", "revision_reviewed": True},
                    )
                )
            item.status = "accepted"
        elif decision == "reject":
            replacement.status = "cancelled"
            if previous is not None:
                previous.status = item.payload.get("previous_status") or "suggested"
                previous.superseded_by = None
                previous.updated_at = _now()
                session.add(previous)
            item.status = "rejected"
        else:
            raise ValueError("Commitment revisions must be accepted or rejected")
        replacement.updated_at = _now()
        session.add(replacement)
    else:
        raise ValueError(f"Unsupported review kind: {item.kind}")

    item.decided_at = _now()
    item.updated_at = _now()
    session.add(item)
    session.add(ReviewDecision(review_item_id=item.id, decision=decision, value=value))
    await session.flush()


def _parse_action_datetime(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        return parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


async def _reschedule_commitment(
    session: AsyncSession,
    action: dict,
    owner_user_id: uuid.UUID,
) -> None:
    from app.models.files import Commitment

    title = str(action.get("commitment_title") or "").strip()
    new_due_at = action.get("new_due_at")
    if not title or not new_due_at:
        raise ValueError("reschedule_commitment requires commitment_title and new_due_at")
    commitment = (
        await session.execute(
            select(Commitment)
            .where(Commitment.owner_user_id == owner_user_id)
            .where(Commitment.title.ilike(f"%{title}%"))
            .order_by(col(Commitment.created_at).desc())
            .limit(1)
        )
    ).scalars().first()
    if commitment is None:
        raise ValueError(f"no commitment matching {title!r}")
    commitment.due_at = _parse_action_datetime(new_due_at)
    commitment.data = {**commitment.data, "requires_review": False, "rescheduled_by": "proposed_action"}
    commitment.updated_at = _now()
    session.add(commitment)


_ACTION_HANDLERS: dict[str, object] = {
    "reschedule_commitment": _reschedule_commitment,
}


async def suggest_entity_merges(session: AsyncSession, user_id: uuid.UUID, limit: int = 25) -> int:
    """Scan current entities for identity-key collisions and lookalike names.

    Tiers, all deterministic:
      0. exact alias-key collisions (existing behavior)
      1. token prefix-containment ("calc 12" vs "Calculus 12")
      2. near-typos via edit distance ("Calulus 12" vs "Calculus 12")
      3. fuzzy name similarity (SequenceMatcher)
    Never auto-merges; suggestions land in the user's Inbox as review items.
    """
    entities = (
        await session.execute(
            select(Entity)
            .where(Entity.is_superseded == False, Entity.owner_user_id == user_id)
            .limit(5000)
        )
    ).scalars().all()
    candidates: dict[frozenset[str], tuple[Entity, Entity, float, str]] = {}

    def record(survivor: Entity, merged: Entity, confidence: float, matched: str) -> None:
        if survivor.id == merged.id:
            return
        if _known_distinct_identities(survivor, merged):
            return
        key = frozenset({str(survivor.id), str(merged.id)})
        prior = candidates.get(key)
        if prior is None or confidence > prior[2]:
            candidates[key] = (survivor, merged, confidence, matched)

    for first, second, confidence, matched in await _exact_key_pairs(session, entities):
        record(first, second, confidence, matched)
    for first, second, confidence, matched in await _fuzzy_pairs(entities):
        record(first, second, confidence, matched)

    blocked = await _blocked_pairs(session, user_id)
    pairs = [
        (survivor, merged, confidence, matched)
        for key, (survivor, merged, confidence, matched) in candidates.items()
        if key not in blocked
    ]
    pairs.sort(key=lambda item: item[2], reverse=True)

    suggested = 0
    for survivor, merged, confidence, matched in pairs[:limit]:
        await _upsert_merge_item(session, user_id, survivor, merged, confidence, matched)
        suggested += 1
    return suggested


async def suggest_entity_merges_for(
    session: AsyncSession,
    user_id: uuid.UUID,
    entity_id: uuid.UUID,
    limit: int = 3,
) -> int:
    """Match one freshly-created entity against current same-type entities."""
    entity = await session.get(Entity, entity_id)
    if entity is None or entity.is_superseded or _generic_name(entity.name):
        return 0
    peers = (
        await session.execute(
            select(Entity)
            .where(
                Entity.is_superseded == False,
                Entity.entity_type == entity.entity_type,
                Entity.owner_user_id == user_id,
            )
            .limit(5000)
        )
    ).scalars().all()
    blocked = await _blocked_pairs(session, user_id)
    scored: list[tuple[Entity, float, str]] = []
    for peer in peers:
        if peer.id == entity.id or _generic_name(peer.name):
            continue
        if _known_distinct_identities(entity, peer):
            continue
        key = frozenset({str(entity.id), str(peer.id)})
        if key in blocked:
            continue
        confidence, matched = _name_similarity(entity.name, peer.name)
        if confidence is None:
            continue
        scored.append((peer, confidence, matched))
    scored.sort(key=lambda item: item[1], reverse=True)

    suggested = 0
    for peer, confidence, matched in scored[:limit]:
        survivor, merged = _ordered_pair(entity, peer)
        await _upsert_merge_item(session, user_id, survivor, merged, confidence, matched)
        suggested += 1
    return suggested


_GENERIC_TOKENS = {
    "note", "notes", "meeting", "meetings", "session", "sessions", "untitled",
    "document", "doc", "file", "files", "folder", "new", "default", "unknown",
    "general", "misc", "other", "home", "temp", "todo", "inbox", "draft",
}
_SECTION_QUALIFIERS = {
    "lab", "lecture", "discussion", "recitation", "section", "studio",
    "seminar", "tutorial", "class", "online",
}


def _tokens(name: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", name.casefold())


def _known_distinct_identities(first: Entity, second: Entity) -> bool:
    return bool(
        first.identity_namespace
        and first.identity_namespace == second.identity_namespace
        and first.external_identity
        and second.external_identity
        and first.external_identity != second.external_identity
    )


def _strip(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.casefold())


def _generic_name(name: str | None) -> bool:
    tokens = _tokens(name or "")
    if not tokens:
        return True
    if all(len(token) < 4 for token in tokens) and len("".join(tokens)) < 6:
        return True
    return all(token in _GENERIC_TOKENS or token.isdigit() for token in tokens)


def _levenshtein(a: str, b: str) -> int:
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for index_a, char_a in enumerate(a, 1):
        current = [index_a]
        for index_b, char_b in enumerate(b, 1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[index_b] + 1,
                    previous[index_b - 1] + (char_a != char_b),
                )
            )
        previous = current
    return previous[-1]


def _name_similarity(name_a: str | None, name_b: str | None) -> tuple[float | None, str]:
    """Deterministic lookalike score for two names, with a reason label."""
    if not name_a or not name_b:
        return None, "missing"
    tokens_a, tokens_b = _tokens(name_a), _tokens(name_b)
    if tokens_a == tokens_b:
        return None, "identical"
    shorter, longer = (tokens_a, tokens_b) if len(tokens_a) <= len(tokens_b) else (tokens_b, tokens_a)

    leftover = _prefix_contained(shorter, longer)
    if leftover is not None:
        extras = [token for token in leftover if not token.isdigit()]
        if extras and all(token in _SECTION_QUALIFIERS for token in extras):
            return None, "section qualifier"
        return (0.7 if extras else 0.9), "prefix-containment"

    strip_a, strip_b = _strip(name_a), _strip(name_b)
    if min(len(strip_a), len(strip_b)) >= 5:
        distance = _levenshtein(strip_a, strip_b)
        if distance == 1:
            return 0.95, "near-typo"
        if distance == 2 and max(len(strip_a), len(strip_b)) >= 8:
            return 0.85, "near-typo"

    if min(len(strip_a), len(strip_b)) >= 6:
        ratio = difflib.SequenceMatcher(None, strip_a, strip_b).ratio()
        if ratio >= 0.82:
            return 0.75, "fuzzy-name"
    return None, "no-match"


def _prefix_contained(shorter: list[str], longer: list[str]) -> list[str] | None:
    """Match every shorter token against a distinct longer token by prefix."""
    remaining = list(longer)
    for token in shorter:
        for index, candidate in enumerate(remaining):
            if candidate.startswith(token) or token.startswith(candidate):
                remaining.pop(index)
                break
        else:
            return None
    return remaining


async def _exact_key_pairs(
    session: AsyncSession,
    entities: list[Entity],
) -> list[tuple[Entity, Entity, float, str]]:
    """Tier 0: same-type canonical or alias key collisions."""
    entity_by_id = {entity.id: entity for entity in entities}
    entities_by_key: dict[tuple[str, str], list[Entity]] = {}
    for entity in entities:
        if entity.canonical_key:
            entities_by_key.setdefault(
                (entity.entity_type, entity.canonical_key), []
            ).append(entity)
    aliases = (
        await session.execute(
            select(EntityAlias).where(col(EntityAlias.entity_id).in_(list(entity_by_id.keys())))
        )
    ).scalars().all()
    pairs: list[tuple[Entity, Entity, float, str]] = []

    # Display-name equality is a strong review signal, not an automatic identity
    # rule. Pair every duplicate with one stable survivor to avoid quadratic work.
    for (_entity_type, key), current in entities_by_key.items():
        if len(current) < 2:
            continue
        current.sort(key=lambda entity: (entity.created_at, str(entity.id)))
        survivor = current[0]
        for other in current[1:]:
            pairs.append((survivor, other, 0.99, f"canonical-key:{key}"))

    for alias in aliases:
        if not alias.canonical_key or alias.entity_id not in entity_by_id:
            continue
        alias_entity = entity_by_id[alias.entity_id]
        owners = entities_by_key.get(
            (alias_entity.entity_type, alias.canonical_key), []
        )
        for owner in owners[:1]:
            if owner.id != alias.entity_id:
                survivor, merged = _ordered_pair(owner, alias_entity)
                pairs.append((survivor, merged, 0.85, f"alias-key:{alias.canonical_key}"))

    by_alias_key: dict[tuple[str, str], list[uuid.UUID]] = {}
    for alias in aliases:
        entity = entity_by_id.get(alias.entity_id)
        if alias.canonical_key and entity is not None:
            by_alias_key.setdefault(
                (entity.entity_type, alias.canonical_key), []
            ).append(alias.entity_id)
    for (entity_type, key), entity_ids in by_alias_key.items():
        if (entity_type, key) in entities_by_key:
            continue
        current = [
            entity_by_id[entity_id]
            for entity_id in dict.fromkeys(entity_ids)
            if entity_id in entity_by_id
        ]
        if len(current) < 2:
            continue
        current.sort(key=lambda entity: entity.created_at)
        survivor = current[0]
        for other in current[1:]:
            pairs.append((survivor, other, 0.85, f"alias-key:{key}"))
    return pairs


async def _fuzzy_pairs(entities: list[Entity]) -> list[tuple[Entity, Entity, float, str]]:
    by_type: dict[str, list[Entity]] = {}
    for entity in entities:
        if _generic_name(entity.name):
            continue
        by_type.setdefault(entity.entity_type, []).append(entity)
    pairs: list[tuple[Entity, Entity, float, str]] = []
    for same_type in by_type.values():
        blocks: dict[str, list[Entity]] = {}
        for entity in same_type:
            stripped = _strip(entity.name or "")
            blocks.setdefault(stripped[:2], []).append(entity)
        for block in blocks.values():
            by_length: dict[int, list[Entity]] = {}
            for entity in block:
                by_length.setdefault(len(_strip(entity.name or "")), []).append(entity)
            lengths = sorted(by_length)
            for index, length in enumerate(lengths):
                for other_length in lengths[index:]:
                    if other_length - length > 4:
                        break
                    for first in by_length[length]:
                        for second in by_length[other_length]:
                            if first.id == second.id:
                                continue
                            confidence, matched = _name_similarity(first.name, second.name)
                            if confidence is None:
                                continue
                            survivor, merged = _ordered_pair(first, second)
                            pairs.append((survivor, merged, confidence, matched))
    return pairs


def _ordered_pair(first: Entity, second: Entity) -> tuple[Entity, Entity]:
    if first.created_at != second.created_at:
        survivor, merged = (
            (first, second) if first.created_at < second.created_at else (second, first)
        )
    else:
        survivor, merged = (
            (first, second) if str(first.id) < str(second.id) else (second, first)
        )
    return survivor, merged


async def _blocked_pairs(session: AsyncSession, user_id: uuid.UUID) -> set[frozenset[str]]:
    items = (
        await session.execute(
            select(ReviewItem).where(
                ReviewItem.user_id == user_id,
                ReviewItem.kind == "entity_merge",
                ReviewItem.source_type.in_(("entity", "entity_merge_pair")),
            )
        )
    ).scalars().all()
    blocked: set[frozenset[str]] = set()
    for item in items:
        if item.status == "dismissed" and (
            item.expires_at is None or item.expires_at <= _now()
        ):
            continue
        survivor = item.payload.get("survivor_id")
        merged = item.payload.get("merged_id") or item.source_id
        if survivor and merged:
            blocked.add(frozenset({str(merged), str(survivor)}))
    return blocked


async def _upsert_merge_item(
    session: AsyncSession,
    user_id: uuid.UUID,
    survivor: Entity,
    merged: Entity,
    confidence: float,
    matched: str,
) -> ReviewItem:
    pair_key = ":".join(sorted((str(survivor.id), str(merged.id))))
    pair_id = uuid.uuid5(uuid.NAMESPACE_URL, f"lifelog:entity-merge:{user_id}:{pair_key}")
    item = await upsert_review_item(
        session,
        user_id=user_id,
        kind="entity_merge",
        source_type="entity_merge_pair",
        source_id=pair_id,
        title=f'Are "{merged.name}" and "{survivor.name}" the same?',
        summary=(
            "Two current entities look like the same thing. "
            "Merging keeps every fact, folds all names as aliases, and "
            "makes future mentions resolve to one entity."
        ),
        payload={
            "survivor_id": str(survivor.id),
            "merged_id": str(merged.id),
            "merged_name": merged.name,
            "survivor_name": survivor.name,
            "matched": matched,
        },
        confidence=round(confidence, 2),
        priority="normal",
        choices=[
            {"id": "accept", "label": f"Merge into {survivor.name}"},
            {"id": "reject", "label": "Keep separate"},
            {"id": "dismiss", "label": "Not now"},
        ],
    )
    if item.status == "dismissed" and item.expires_at is not None and item.expires_at <= _now():
        item.status = "pending"
        item.decided_at = None
        item.expires_at = None
        item.updated_at = _now()
        session.add(item)
        await session.flush()
    return item
