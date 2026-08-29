"""Filter recall candidates by explicit owner before ranking.

Revision ID: 017
Revises: 016
"""

import sqlalchemy as sa

from alembic import op

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("search_documents", sa.Column("owner_user_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_search_documents_owner_user_id_users",
        "search_documents",
        "users",
        ["owner_user_id"],
        ["id"],
    )
    op.create_index(
        "ix_search_documents_owner_user_id",
        "search_documents",
        ["owner_user_id"],
    )
    op.execute("""
        UPDATE search_documents
        SET owner_user_id = CASE source_type
            WHEN 'entity' THEN (
                SELECT entities.owner_user_id FROM entities WHERE entities.id = search_documents.source_id
            )
            WHEN 'event' THEN (
                SELECT events.owner_user_id FROM events WHERE events.id = search_documents.source_id
            )
            WHEN 'timeline' THEN (
                SELECT timeline_entries.owner_user_id
                FROM timeline_entries WHERE timeline_entries.id = search_documents.source_id
            )
            WHEN 'daily_summary' THEN (
                SELECT daily_summaries.owner_user_id
                FROM daily_summaries WHERE daily_summaries.id = search_documents.source_id
            )
            WHEN 'capture' THEN (
                SELECT captures.user_id FROM captures WHERE captures.id = search_documents.source_id
            )
            WHEN 'artifact_chunk' THEN (
                SELECT file_attachments.owner_user_id
                FROM content_chunks
                JOIN file_attachments ON file_attachments.id = content_chunks.file_id
                WHERE content_chunks.id = search_documents.source_id
            )
            WHEN 'evidence_span' THEN (
                SELECT evidence_documents.owner_user_id
                FROM evidence_spans
                JOIN evidence_documents ON evidence_documents.id = evidence_spans.document_id
                WHERE evidence_spans.id = search_documents.source_id
            )
            WHEN 'memory_claim' THEN (
                SELECT memory_claims.owner_user_id
                FROM memory_claims WHERE memory_claims.id = search_documents.source_id
            )
            ELSE NULL
        END
        WHERE owner_user_id IS NULL
    """)


def downgrade() -> None:
    op.drop_index("ix_search_documents_owner_user_id", table_name="search_documents")
    op.drop_constraint(
        "fk_search_documents_owner_user_id_users",
        "search_documents",
        type_="foreignkey",
    )
    op.drop_column("search_documents", "owner_user_id")
