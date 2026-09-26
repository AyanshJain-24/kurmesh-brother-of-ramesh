"""add optional full name to user profiles"""
from alembic import op
import sqlalchemy as sa

revision = "20260911_02"
down_revision = "20260910_01"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("users", sa.Column("full_name", sa.String(length=200), nullable=True))

def downgrade() -> None:
    op.drop_column("users", "full_name")
