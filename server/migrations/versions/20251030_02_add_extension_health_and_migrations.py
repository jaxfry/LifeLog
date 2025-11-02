"""Add ExtensionHealth and ExtensionMigration tables

Revision ID: 20251030_02
Revises: 20251030_01
Create Date: 2025-10-30 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '20251030_02'
down_revision: Union[str, Sequence[str], None] = '20251030_01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create ExtensionHealth and ExtensionMigration tables."""
    
    # Create ExtensionHealth table
    op.create_table(
        'extensionhealth',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('extension_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('last_check', sa.DateTime(timezone=True), nullable=False),
        sa.Column('errors', sa.JSON(), nullable=True),
        sa.Column('warnings', sa.JSON(), nullable=True),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['extension_id'], ['extension.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_extensionhealth_extension_id'), 'extensionhealth', ['extension_id'], unique=False)
    
    # Create ExtensionMigration table
    op.create_table(
        'extensionmigration',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('extension_id', sa.Integer(), nullable=False),
        sa.Column('migration_name', sa.String(), nullable=False),
        sa.Column('applied_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('from_version', sa.String(), nullable=True),
        sa.Column('to_version', sa.String(), nullable=False),
        sa.Column('checksum', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['extension_id'], ['extension.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('extension_id', 'migration_name', name='uq_extension_migration')
    )
    op.create_index(op.f('ix_extensionmigration_extension_id'), 'extensionmigration', ['extension_id'], unique=False)


def downgrade() -> None:
    """Drop ExtensionHealth and ExtensionMigration tables."""
    op.drop_index(op.f('ix_extensionmigration_extension_id'), table_name='extensionmigration')
    op.drop_table('extensionmigration')
    op.drop_index(op.f('ix_extensionhealth_extension_id'), table_name='extensionhealth')
    op.drop_table('extensionhealth')
