"""revert vector dimensions to 768

Revision ID: c1d2e3f4g5h6
Revises: a1b2c3d4e5f6
Create Date: 2025-12-02 01:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import pgvector

# revision identifiers, used by Alembic.
revision: str = 'c1d2e3f4g5h6'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Revert embedding dimensions back to 768 to match gemini-embedding-001 output."""
    # Clear existing embeddings as they may be incompatible
    op.execute("UPDATE daily_chapters SET embedding = NULL")
    op.execute("UPDATE timeline SET embedding = NULL")

    # Revert to 768 dimensions
    op.alter_column('daily_chapters', 'embedding',
               existing_type=pgvector.sqlalchemy.vector.VECTOR(dim=3072),
               type_=pgvector.sqlalchemy.vector.VECTOR(dim=768),
               existing_nullable=True)
    op.alter_column('timeline', 'embedding',
               existing_type=pgvector.sqlalchemy.vector.VECTOR(dim=3072),
               type_=pgvector.sqlalchemy.vector.VECTOR(dim=768),
               existing_nullable=True)


def downgrade() -> None:
    """Upgrade to 3072 dimensions."""
    op.execute("UPDATE daily_chapters SET embedding = NULL")
    op.execute("UPDATE timeline SET embedding = NULL")

    op.alter_column('timeline', 'embedding',
               existing_type=pgvector.sqlalchemy.vector.VECTOR(dim=768),
               type_=pgvector.sqlalchemy.vector.VECTOR(dim=3072),
               existing_nullable=True)
    op.alter_column('daily_chapters', 'embedding',
               existing_type=pgvector.sqlalchemy.vector.VECTOR(dim=768),
               type_=pgvector.sqlalchemy.vector.VECTOR(dim=3072),
               existing_nullable=True)
