"""Add timeline block table

Revision ID: 20251104_01
Revises: 20251030_03
Create Date: 2025-11-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '20251104_01'
down_revision: Union[str, Sequence[str], None] = '20251030_03'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add TimelineBlock and TimelineBlockEventLink tables."""
    
    # Create timelineblock table
    op.create_table(
        'timelineblock',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('actor_id', sa.Integer(), nullable=False),
        sa.Column('start_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('end_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('title', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('summary', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('tags', sa.JSON(), nullable=True),
        sa.Column('block_data', sa.JSON(), nullable=False),
        sa.Column('character_count', sa.Integer(), nullable=False),
        sa.Column('token_count', sa.Integer(), nullable=True),
        sa.Column('model_version', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('prompt_template_id', sa.Integer(), nullable=True),
        sa.Column('ai_usage_log_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('superseded_by_block_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['actor_id'], ['actor.id'], ),
        sa.ForeignKeyConstraint(['prompt_template_id'], ['prompttemplate.id'], ),
        sa.ForeignKeyConstraint(['ai_usage_log_id'], ['aiusagelog.id'], ),
        sa.ForeignKeyConstraint(['superseded_by_block_id'], ['timelineblock.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ai_usage_log_id')
    )
    
    # Create timelineblockeventlink association table
    op.create_table(
        'timelineblockeventlink',
        sa.Column('timeline_block_id', sa.Integer(), nullable=False),
        sa.Column('event_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['timeline_block_id'], ['timelineblock.id'], ),
        sa.ForeignKeyConstraint(['event_id'], ['event.id'], ),
        sa.PrimaryKeyConstraint('timeline_block_id', 'event_id')
    )


def downgrade() -> None:
    """Remove TimelineBlock tables."""
    op.drop_table('timelineblockeventlink')
    op.drop_table('timelineblock')
