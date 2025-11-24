"""add dirty status to sessionstatus

Revision ID: 7ae0bd174f75
Revises: c581534a2882
Create Date: 2025-11-23 21:07:47.880454

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7ae0bd174f75'
down_revision: Union[str, Sequence[str], None] = 'c581534a2882'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE sessionstatus ADD VALUE IF NOT EXISTS 'DIRTY'")


def downgrade() -> None:
    """Downgrade schema."""
    # PostgreSQL does not support removing values from enums easily
    pass
