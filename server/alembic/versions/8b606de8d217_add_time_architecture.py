"""add_time_architecture

Revision ID: 8b606de8d217
Revises: 479c58aed83c
Create Date: 2026-04-15 18:35:34.654048

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8b606de8d217'
down_revision: Union[str, Sequence[str], None] = '479c58aed83c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('raw_logs', sa.Column('iana_timezone', sa.String(), nullable=True))
    op.add_column('raw_logs', sa.Column('logical_date', sa.String(), nullable=True))
    op.create_index(op.f('ix_raw_logs_logical_date'), 'raw_logs', ['logical_date'], unique=False)
    
    op.add_column('sessions', sa.Column('iana_timezone', sa.String(), nullable=True))
    op.add_column('sessions', sa.Column('logical_date', sa.String(), nullable=True))
    op.add_column('sessions', sa.Column('last_touched_at', sa.DateTime(), nullable=True))
    op.create_index(op.f('ix_sessions_logical_date'), 'sessions', ['logical_date'], unique=False)
    
    op.add_column('events', sa.Column('iana_timezone', sa.String(), nullable=True))
    op.add_column('events', sa.Column('logical_date', sa.String(), nullable=True))
    op.create_index(op.f('ix_events_logical_date'), 'events', ['logical_date'], unique=False)
    
    op.add_column('timeline', sa.Column('iana_timezone', sa.String(), nullable=True))
    op.add_column('timeline', sa.Column('logical_date', sa.String(), nullable=True))
    op.create_index(op.f('ix_timeline_logical_date'), 'timeline', ['logical_date'], unique=False)
    
    op.add_column('daily_chapters', sa.Column('logical_date', sa.String(), nullable=True))
    op.add_column('daily_chapters', sa.Column('last_touched_at', sa.DateTime(), nullable=True))
    op.create_index(op.f('ix_daily_chapters_logical_date'), 'daily_chapters', ['logical_date'], unique=False)

    op.add_column('daily_summaries', sa.Column('logical_date', sa.String(), nullable=True))
    op.add_column('daily_summaries', sa.Column('status', sa.String(), server_default='READY', nullable=False))
    op.add_column('daily_summaries', sa.Column('last_touched_at', sa.DateTime(), nullable=True))
    op.create_index(op.f('ix_daily_summaries_logical_date'), 'daily_summaries', ['logical_date'], unique=False)

def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_daily_summaries_logical_date'), table_name='daily_summaries')
    op.drop_column('daily_summaries', 'last_touched_at')
    op.drop_column('daily_summaries', 'status')
    op.drop_column('daily_summaries', 'logical_date')

    op.drop_index(op.f('ix_daily_chapters_logical_date'), table_name='daily_chapters')
    op.drop_column('daily_chapters', 'last_touched_at')
    op.drop_column('daily_chapters', 'logical_date')

    op.drop_index(op.f('ix_timeline_logical_date'), table_name='timeline')
    op.drop_column('timeline', 'logical_date')
    op.drop_column('timeline', 'iana_timezone')

    op.drop_index(op.f('ix_events_logical_date'), table_name='events')
    op.drop_column('events', 'logical_date')
    op.drop_column('events', 'iana_timezone')

    op.drop_index(op.f('ix_sessions_logical_date'), table_name='sessions')
    op.drop_column('sessions', 'last_touched_at')
    op.drop_column('sessions', 'logical_date')
    op.drop_column('sessions', 'iana_timezone')

    op.drop_index(op.f('ix_raw_logs_logical_date'), table_name='raw_logs')
    op.drop_column('raw_logs', 'logical_date')
    op.drop_column('raw_logs', 'iana_timezone')
