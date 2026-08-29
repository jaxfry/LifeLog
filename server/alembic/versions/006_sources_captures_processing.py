"""Add source connections, universal captures, and staged processing.

Revision ID: 006
Revises: 005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "006"
down_revision: str | None = "005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("devices", sa.Column("user_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_devices_user", "devices", "users", ["user_id"], ["id"])
    op.create_index("ix_devices_user_id", "devices", ["user_id"])

    op.create_table(
        "source_connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("extension_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("schedule_cron", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_sync_started_at", sa.DateTime(), nullable=True),
        sa.Column("last_sync_completed_at", sa.DateTime(), nullable=True),
        sa.Column("last_sync_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('active','paused','error','disconnected')",
            name="ck_source_connections_status",
        ),
        sa.ForeignKeyConstraint(["extension_id"], ["extensions.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("user_id", "extension_id", "status", "is_active"):
        op.create_index(f"ix_source_connections_{column}", "source_connections", [column])
    op.create_index(
        "ix_source_connections_extension_active",
        "source_connections",
        ["extension_id", "is_active"],
    )

    op.create_table(
        "source_secrets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("key_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["connection_id"], ["source_connections.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("connection_id", "key", name="uq_source_secret_connection_key"),
    )
    op.create_index("ix_source_secrets_connection_id", "source_secrets", ["connection_id"])

    op.create_table(
        "source_checkpoints",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("stream", sa.String(), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["connection_id"], ["source_connections.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("connection_id", "stream", name="uq_source_checkpoint_stream"),
    )
    op.create_index("ix_source_checkpoints_connection_id", "source_checkpoints", ["connection_id"])

    op.create_table(
        "source_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("external_key", sa.String(), nullable=False),
        sa.Column("current_raw_log_id", sa.Uuid(), nullable=True),
        sa.Column("current_revision", sa.String(), nullable=True),
        sa.Column("source_updated_at", sa.DateTime(), nullable=True),
        sa.Column("update_policy", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "update_policy IN ('append','replace','snapshot')",
            name="ck_source_records_update_policy",
        ),
        sa.ForeignKeyConstraint(["connection_id"], ["source_connections.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("connection_id", "external_key", name="uq_source_record_external_key"),
    )
    op.create_index("ix_source_records_connection_id", "source_records", ["connection_id"])
    op.create_index("ix_source_records_current_raw_log_id", "source_records", ["current_raw_log_id"])

    op.add_column("commitments", sa.Column("source_record_id", sa.Uuid(), nullable=True))
    op.add_column("commitments", sa.Column("mapping_key", sa.String(), nullable=True))
    op.add_column("commitments", sa.Column("superseded_by", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_commitments_source_record",
        "commitments",
        "source_records",
        ["source_record_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_commitments_superseded_by",
        "commitments",
        "commitments",
        ["superseded_by"],
        ["id"],
    )
    for column in ("source_record_id", "mapping_key", "superseded_by"):
        op.create_index(f"ix_commitments_{column}", "commitments", [column])

    op.drop_index("ix_raw_logs_payload_hash", table_name="raw_logs")
    op.create_index("ix_raw_logs_payload_hash", "raw_logs", ["payload_hash"], unique=False)
    op.add_column("raw_logs", sa.Column("ingest_key", sa.String(), nullable=True))
    op.execute(
        "UPDATE raw_logs SET ingest_key = "
        "md5('device:' || device_id || ':' || payload_hash) || "
        "md5(':device:' || device_id || ':' || payload_hash)"
    )
    op.alter_column("raw_logs", "ingest_key", nullable=False)
    op.create_index("ix_raw_logs_ingest_key", "raw_logs", ["ingest_key"], unique=True)
    op.add_column("raw_logs", sa.Column("source_connection_id", sa.Uuid(), nullable=True))
    op.add_column("raw_logs", sa.Column("source_record_id", sa.Uuid(), nullable=True))
    op.add_column("raw_logs", sa.Column("external_key", sa.String(), nullable=True))
    op.add_column("raw_logs", sa.Column("external_revision", sa.String(), nullable=True))
    op.add_column("raw_logs", sa.Column("source_updated_at", sa.DateTime(), nullable=True))
    op.add_column("raw_logs", sa.Column("update_policy", sa.String(), server_default="append", nullable=False))
    op.create_foreign_key(
        "fk_raw_logs_source_connection",
        "raw_logs",
        "source_connections",
        ["source_connection_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_raw_logs_source_record",
        "raw_logs",
        "source_records",
        ["source_record_id"],
        ["id"],
    )
    for column in ("source_connection_id", "source_record_id", "external_key"):
        op.create_index(f"ix_raw_logs_{column}", "raw_logs", [column])

    op.create_table(
        "captures",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("device_id", sa.String(), nullable=True),
        sa.Column("source_connection_id", sa.Uuid(), nullable=True),
        sa.Column("idempotency_key", sa.String(), nullable=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("captured_at", sa.DateTime(), nullable=False),
        sa.Column("timezone", sa.String(), nullable=True),
        sa.Column("intent", sa.String(), nullable=True),
        sa.Column("text_content", sa.Text(), nullable=True),
        sa.Column("context_hints", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("privacy", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("classification", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("processing_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("kind IN ('photo','audio','video','note','file','scan')", name="ck_captures_kind"),
        sa.CheckConstraint(
            "status IN ('received','preserved','processing','awaiting_review',"
            "'ready','partially_ready','failed','cancelled')",
            name="ck_captures_status",
        ),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"]),
        sa.ForeignKeyConstraint(["source_connection_id"], ["source_connections.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_capture_user_idempotency"),
    )
    for column in (
        "user_id",
        "device_id",
        "source_connection_id",
        "idempotency_key",
        "kind",
        "status",
        "captured_at",
        "intent",
    ):
        op.create_index(f"ix_captures_{column}", "captures", [column])
    op.create_index("ix_captures_user_created", "captures", ["user_id", "created_at"])

    op.create_table(
        "capture_artifacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("capture_id", sa.Uuid(), nullable=False),
        sa.Column("file_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["capture_id"], ["captures.id"]),
        sa.ForeignKeyConstraint(["file_id"], ["file_attachments.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("capture_id", "file_id", name="uq_capture_artifact_file"),
    )
    op.create_index("ix_capture_artifacts_capture_id", "capture_artifacts", ["capture_id"])
    op.create_index("ix_capture_artifacts_file_id", "capture_artifacts", ["file_id"])

    op.create_table(
        "upload_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("capture_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("mime_type", sa.String(), nullable=False),
        sa.Column("total_bytes", sa.Integer(), nullable=False),
        sa.Column("received_bytes", sa.Integer(), nullable=False),
        sa.Column("temp_path", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("content_hash", sa.String(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending','uploading','complete','cancelled','expired','failed')",
            name="ck_upload_sessions_status",
        ),
        sa.ForeignKeyConstraint(["capture_id"], ["captures.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_upload_sessions_capture_id", "upload_sessions", ["capture_id"])
    op.create_index("ix_upload_sessions_status", "upload_sessions", ["status"])
    op.create_index("ix_upload_sessions_expires_at", "upload_sessions", ["expires_at"])

    op.create_table(
        "processing_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("capture_id", sa.Uuid(), nullable=True),
        sa.Column("target_type", sa.String(), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("stage", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("input_version", sa.Integer(), nullable=False),
        sa.Column("processor", sa.String(), nullable=False),
        sa.Column("processor_version", sa.String(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("output_refs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error_type", sa.String(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending','running','completed','failed','skipped','cancelled')",
            name="ck_processing_jobs_status",
        ),
        sa.ForeignKeyConstraint(["capture_id"], ["captures.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "target_type",
            "target_id",
            "stage",
            "input_version",
            name="uq_processing_job_stage_version",
        ),
    )
    for column in ("capture_id", "target_type", "target_id", "stage", "status"):
        op.create_index(f"ix_processing_jobs_{column}", "processing_jobs", [column])
    op.create_index(
        "ix_processing_jobs_target_status",
        "processing_jobs",
        ["target_type", "target_id", "status"],
    )


def downgrade() -> None:
    op.drop_table("processing_jobs")
    op.drop_table("upload_sessions")
    op.drop_table("capture_artifacts")
    op.drop_table("captures")
    for column in ("superseded_by", "mapping_key", "source_record_id"):
        op.drop_index(f"ix_commitments_{column}", table_name="commitments")
    op.drop_constraint("fk_commitments_superseded_by", "commitments", type_="foreignkey")
    op.drop_constraint("fk_commitments_source_record", "commitments", type_="foreignkey")
    for column in ("superseded_by", "mapping_key", "source_record_id"):
        op.drop_column("commitments", column)
    for column in ("external_key", "source_record_id", "source_connection_id"):
        op.drop_index(f"ix_raw_logs_{column}", table_name="raw_logs")
    op.drop_constraint("fk_raw_logs_source_record", "raw_logs", type_="foreignkey")
    op.drop_constraint("fk_raw_logs_source_connection", "raw_logs", type_="foreignkey")
    op.drop_index("ix_raw_logs_ingest_key", table_name="raw_logs")
    for column in (
        "update_policy",
        "source_updated_at",
        "external_revision",
        "external_key",
        "source_record_id",
        "source_connection_id",
        "ingest_key",
    ):
        op.drop_column("raw_logs", column)
    op.drop_index("ix_raw_logs_payload_hash", table_name="raw_logs")
    op.create_index("ix_raw_logs_payload_hash", "raw_logs", ["payload_hash"], unique=True)
    op.drop_table("source_records")
    op.drop_table("source_checkpoints")
    op.drop_table("source_secrets")
    op.drop_table("source_connections")
    op.drop_index("ix_devices_user_id", table_name="devices")
    op.drop_constraint("fk_devices_user", "devices", type_="foreignkey")
    op.drop_column("devices", "user_id")
