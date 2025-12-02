"""add failed status to sessionstatus

Revision ID: a1b2c3d4e5f6
Revises: 2c6d12801b2c
Create Date: 2025-12-01 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'b7921b6d8f0b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE sessionstatus ADD VALUE IF NOT EXISTS 'FAILED'")


def downgrade() -> None:
    """Downgrade schema."""
    # PostgreSQL does not support removing values from enums easily
    pass
