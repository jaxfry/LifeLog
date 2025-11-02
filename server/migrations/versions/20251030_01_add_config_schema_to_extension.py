"""Add config_schema to extension

Revision ID: 20251030_01
Revises: b872d2e04e4a
Create Date: 2025-10-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20251030_01'
down_revision: Union[str, Sequence[str], None] = 'b872d2e04e4a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add config_schema column to extension table."""
    op.add_column('extension', sa.Column('config_schema', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Remove config_schema column from extension table."""
    op.drop_column('extension', 'config_schema')
