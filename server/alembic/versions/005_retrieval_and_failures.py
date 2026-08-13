"""Add unified retrieval projection and durable processing failures.

Revision ID: 005
Revises: 004
"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "005"
down_revision: str | None = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "search_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=True),
        sa.Column("logical_date", sa.String(), nullable=True),
        sa.Column("embedding", pgvector.sqlalchemy.Vector(dim=768), nullable=True),
        sa.Column("embedding_model", sa.String(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_superseded", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_type", "source_id", "version", name="uq_search_document_source_version"),
    )
    op.create_index("ix_search_documents_source_type", "search_documents", ["source_type"])
    op.create_index("ix_search_documents_source_id", "search_documents", ["source_id"])
    op.create_index("ix_search_documents_occurred_at", "search_documents", ["occurred_at"])
    op.create_index("ix_search_documents_logical_date", "search_documents", ["logical_date"])
    op.create_index("ix_search_documents_is_superseded", "search_documents", ["is_superseded"])
    op.create_index("ix_search_documents_current_type", "search_documents", ["is_superseded", "source_type"])
    op.execute(
        "CREATE INDEX ix_search_documents_fts ON search_documents "
        "USING gin (to_tsvector('english', content))"
    )
    op.execute(
        "CREATE INDEX ix_search_documents_embedding_hnsw ON search_documents "
        "USING hnsw (embedding vector_cosine_ops)"
    )

    op.create_table(
        "processing_failures",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=True),
        sa.Column("stage", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("error_type", sa.String(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("traceback", sa.Text(), nullable=True),
        sa.Column("context", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("last_failed_at", sa.DateTime(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("source_type", "source_id", "stage", "status"):
        op.create_index(f"ix_processing_failures_{column}", "processing_failures", [column])
    op.create_index("ix_processing_failures_open", "processing_failures", ["status", "stage"])


def downgrade() -> None:
    op.drop_table("processing_failures")
    op.drop_table("search_documents")
