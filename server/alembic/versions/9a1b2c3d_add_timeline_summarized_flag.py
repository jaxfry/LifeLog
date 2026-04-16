"""add timeline summarized flag

Revision ID: $(date +%N | md5 | head -c 8)
Revises: 8b606de8d217
Create Date: $(date -u +'%Y-%m-%d %H:%M:%S.%N')

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '9a1b2c3d'
down_revision = '8b606de8d217'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column('timeline', sa.Column('is_summarized', sa.Boolean(), server_default='false', nullable=False))

def downgrade() -> None:
    op.drop_column('timeline', 'is_summarized')
