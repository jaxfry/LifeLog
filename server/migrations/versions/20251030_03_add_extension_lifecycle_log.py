"""Add ExtensionLifecycleLog table

Revision ID: 20251030_03
Revises: 20251030_02
Create Date: 2025-10-30 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '20251030_03'
down_revision: Union[str, Sequence[str], None] = '20251030_02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create ExtensionLifecycleLog table."""
    op.create_table(
        'extensionlifecyclelog',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('extension_id', sa.Integer(), nullable=False),
        sa.Column('hook_name', sa.String(), nullable=False),
        sa.Column('executed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('success', sa.Boolean(), nullable=False),
        sa.Column('error_message', sa.String(), nullable=True),
        sa.Column('context', sa.JSON(), nullable=True),
        sa.Column('execution_time_ms', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['extension_id'], ['extension.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_extensionlifecyclelog_extension_id'), 'extensionlifecyclelog', ['extension_id'], unique=False)


def downgrade() -> None:
    """Drop ExtensionLifecycleLog table."""
    op.drop_index(op.f('ix_extensionlifecyclelog_extension_id'), table_name='extensionlifecyclelog')
    op.drop_table('extensionlifecyclelog')
