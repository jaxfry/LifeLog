"""Evidence-backed episodes and deterministic entity identity.

Revision ID: 010
Revises: 009
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("kind", sa.String(), nullable=False, server_default="activity"))
    op.create_index("ix_sessions_kind", "sessions", ["kind"])
    op.add_column("timeline_entries", sa.Column("evidence_event_ids", postgresql.JSONB(), nullable=True))
    op.add_column("timeline_entries", sa.Column("confidence", sa.Float(), nullable=True))
    op.add_column("timeline_entries", sa.Column("inferences", postgresql.JSONB(), nullable=True))
    op.add_column("daily_summaries", sa.Column("open_loops", postgresql.JSONB(), nullable=True))
    op.add_column("daily_summaries", sa.Column("inferences", postgresql.JSONB(), nullable=True))

    # Migration 009 intentionally installed a non-unique lookup index. Collapse
    # races that happened before atomic identity locking, while preserving every
    # old entity as a superseded node with an auditable forward pointer.
    op.execute("""
        WITH ranked AS (
            SELECT id,
                   first_value(id) OVER (
                       PARTITION BY owner_user_id, entity_type, canonical_key
                       ORDER BY created_at, id
                   ) AS survivor_id,
                   row_number() OVER (
                       PARTITION BY owner_user_id, entity_type, canonical_key
                       ORDER BY created_at, id
                   ) AS rn
            FROM entities
            WHERE is_superseded = false
              AND owner_user_id IS NOT NULL
              AND canonical_key IS NOT NULL
        )
        UPDATE relations r
        SET object_id = ranked.survivor_id
        FROM ranked
        WHERE ranked.rn > 1 AND r.object_type = 'entity' AND r.object_id = ranked.id
    """)
    op.execute("""
        WITH ranked AS (
            SELECT id,
                   first_value(id) OVER (
                       PARTITION BY owner_user_id, entity_type, canonical_key
                       ORDER BY created_at, id
                   ) AS survivor_id,
                   row_number() OVER (
                       PARTITION BY owner_user_id, entity_type, canonical_key
                       ORDER BY created_at, id
                   ) AS rn
            FROM entities
            WHERE is_superseded = false
              AND owner_user_id IS NOT NULL
              AND canonical_key IS NOT NULL
        )
        UPDATE relations r
        SET subject_id = ranked.survivor_id
        FROM ranked
        WHERE ranked.rn > 1 AND r.subject_type = 'entity' AND r.subject_id = ranked.id
    """)
    op.execute("""
        WITH ranked AS (
            SELECT id,
                   first_value(id) OVER (
                       PARTITION BY owner_user_id, entity_type, canonical_key
                       ORDER BY created_at, id
                   ) AS survivor_id,
                   row_number() OVER (
                       PARTITION BY owner_user_id, entity_type, canonical_key
                       ORDER BY created_at, id
                   ) AS rn
            FROM entities
            WHERE is_superseded = false
              AND owner_user_id IS NOT NULL
              AND canonical_key IS NOT NULL
        )
        UPDATE search_documents d
        SET is_superseded = true
        FROM ranked
        WHERE ranked.rn > 1 AND d.source_type = 'entity' AND d.source_id = ranked.id
    """)
    op.execute("""
        WITH ranked AS (
            SELECT id,
                   first_value(id) OVER (
                       PARTITION BY owner_user_id, entity_type, canonical_key
                       ORDER BY created_at, id
                   ) AS survivor_id,
                   row_number() OVER (
                       PARTITION BY owner_user_id, entity_type, canonical_key
                       ORDER BY created_at, id
                   ) AS rn
            FROM entities
            WHERE is_superseded = false
              AND owner_user_id IS NOT NULL
              AND canonical_key IS NOT NULL
        )
        UPDATE entities e
        SET is_superseded = true, superseded_by = ranked.survivor_id
        FROM ranked
        WHERE ranked.rn > 1 AND e.id = ranked.id
    """)
    op.drop_index("ix_entities_owner_current_name", table_name="entities")
    op.create_index(
        "uq_entities_owner_current_name",
        "entities",
        ["owner_user_id", "entity_type", "canonical_key"],
        unique=True,
        postgresql_where=sa.text(
            "is_superseded = false AND owner_user_id IS NOT NULL AND canonical_key IS NOT NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index("uq_entities_owner_current_name", table_name="entities")
    op.create_index(
        "ix_entities_owner_current_name",
        "entities",
        ["owner_user_id", "entity_type", "canonical_key"],
        postgresql_where=sa.text("is_superseded = false AND canonical_key IS NOT NULL"),
    )
    op.drop_column("daily_summaries", "inferences")
    op.drop_column("daily_summaries", "open_loops")
    op.drop_column("timeline_entries", "inferences")
    op.drop_column("timeline_entries", "confidence")
    op.drop_column("timeline_entries", "evidence_event_ids")
    op.drop_index("ix_sessions_kind", table_name="sessions")
    op.drop_column("sessions", "kind")
