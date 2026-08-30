"""Add AISettings table

Revision ID: 20251104_02
Revises: 20251104_01
Create Date: 2025-11-04 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '20251104_02'
down_revision: Union[str, Sequence[str], None] = '20251104_01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create AISettings singleton table."""
    op.create_table(
        'aisettings',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('default_embedding_provider_slug', sa.String(), nullable=True),
        sa.Column('default_embedding_model', sa.String(), nullable=True),
        sa.Column('default_embedding_dim', sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    """Drop AISettings table."""
    op.drop_table('aisettings')
