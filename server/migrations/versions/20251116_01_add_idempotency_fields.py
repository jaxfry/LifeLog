"""Add idempotency fields and sync cursors

Revision ID: 20251116_01
Revises: 20251104_02_add_ai_settings_table
Create Date: 2025-11-16

This migration adds comprehensive idempotency support:
1. RawLog: external_id, fingerprint fields with unique constraints
2. Event: external_id field with unique constraint
3. SyncCursor: new table for tracking device-source sync watermarks
4. TimelineBlock: unique constraint on (actor_id, start_time, end_time)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '20251116_01'
down_revision = ('20251104_02', '20251023_01')  # Merge both branches
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add idempotency fields to RawLog
    op.add_column('rawlog', sa.Column('external_id', sa.String(), nullable=True))
    op.add_column('rawlog', sa.Column('fingerprint', sa.String(), nullable=True))
    
    # Create indexes for RawLog idempotency fields
    op.create_index(op.f('ix_rawlog_external_id'), 'rawlog', ['external_id'], unique=False)
    op.create_index(op.f('ix_rawlog_fingerprint'), 'rawlog', ['fingerprint'], unique=False)
    
    # Create unique constraints for RawLog (allowing NULLs as they don't violate uniqueness in Postgres)
    op.create_unique_constraint(
        'uq_rawlog_source_device_external',
        'rawlog',
        ['source_actor_id', 'device_id', 'external_id']
    )
    op.create_unique_constraint(
        'uq_rawlog_source_device_fingerprint',
        'rawlog',
        ['source_actor_id', 'device_id', 'fingerprint']
    )
    
    # Add idempotency field to Event
    op.add_column('event', sa.Column('external_id', sa.String(), nullable=True))
    op.create_index(op.f('ix_event_external_id'), 'event', ['external_id'], unique=False)
    op.create_unique_constraint(
        'uq_event_processor_external',
        'event',
        ['processor_actor_id', 'external_id']
    )
    
    # Create SyncCursor table
    op.create_table(
        'synccursor',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('device_id', sa.Integer(), nullable=False),
        sa.Column('source_actor_id', sa.Integer(), nullable=False),
        sa.Column('cursor_key', sa.String(), nullable=False),
        sa.Column('cursor_value', sa.String(), nullable=False),
        sa.Column('last_updated', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['device_id'], ['device.id'], ),
        sa.ForeignKeyConstraint(['source_actor_id'], ['actor.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'device_id', 'source_actor_id', 'cursor_key',
            name='uq_synccursor_device_source_key'
        )
    )
    op.create_index(op.f('ix_synccursor_device_id'), 'synccursor', ['device_id'], unique=False)
    op.create_index(op.f('ix_synccursor_source_actor_id'), 'synccursor', ['source_actor_id'], unique=False)
    
    # Add unique constraint to TimelineBlock
    op.create_unique_constraint(
        'uq_timelineblock_actor_timerange',
        'timelineblock',
        ['actor_id', 'start_time', 'end_time']
    )


def downgrade() -> None:
    # Remove TimelineBlock unique constraint
    op.drop_constraint('uq_timelineblock_actor_timerange', 'timelineblock', type_='unique')
    
    # Drop SyncCursor table
    op.drop_index(op.f('ix_synccursor_source_actor_id'), table_name='synccursor')
    op.drop_index(op.f('ix_synccursor_device_id'), table_name='synccursor')
    op.drop_table('synccursor')
    
    # Remove Event idempotency fields
    op.drop_constraint('uq_event_processor_external', 'event', type_='unique')
    op.drop_index(op.f('ix_event_external_id'), table_name='event')
    op.drop_column('event', 'external_id')
    
    # Remove RawLog idempotency fields
    op.drop_constraint('uq_rawlog_source_device_fingerprint', 'rawlog', type_='unique')
    op.drop_constraint('uq_rawlog_source_device_external', 'rawlog', type_='unique')
    op.drop_index(op.f('ix_rawlog_fingerprint'), table_name='rawlog')
    op.drop_index(op.f('ix_rawlog_external_id'), table_name='rawlog')
    op.drop_column('rawlog', 'fingerprint')
    op.drop_column('rawlog', 'external_id')
