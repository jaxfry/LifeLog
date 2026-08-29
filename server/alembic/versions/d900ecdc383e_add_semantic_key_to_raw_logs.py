"""add semantic_key to raw_logs

Revision ID: d900ecdc383e
Revises: f7b2b40cbe94
Create Date: 2026-08-13 18:58:05.127927

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'd900ecdc383e'
down_revision: Union[str, Sequence[str], None] = 'f7b2b40cbe94'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('raw_logs', sa.Column('semantic_key', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.create_index(op.f('ix_raw_logs_semantic_key'), 'raw_logs', ['semantic_key'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_raw_logs_semantic_key'), table_name='raw_logs')
    op.drop_column('raw_logs', 'semantic_key')
