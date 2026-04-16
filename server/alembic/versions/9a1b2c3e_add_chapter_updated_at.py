"""add chapter updated_at

Revision ID: 9a1b2c3e
Revises: 9a1b2c3d
Create Date: 2024-04-15 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect

revision = '9a1b2c3e'
down_revision = '9a1b2c3d'
branch_labels = None
depends_on = None

def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    cols = [c['name'] for c in inspector.get_columns('daily_chapters')]
    if 'updated_at' not in cols:
        op.add_column('daily_chapters', sa.Column('updated_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=True))
        op.execute('UPDATE daily_chapters SET updated_at = last_touched_at WHERE updated_at IS NULL')
        op.alter_column('daily_chapters', 'updated_at', nullable=False)

def downgrade() -> None:
    op.drop_column('daily_chapters', 'updated_at')
