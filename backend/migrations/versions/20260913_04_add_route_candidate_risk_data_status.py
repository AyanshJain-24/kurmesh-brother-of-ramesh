"""Add risk_data_status column to route_candidates.

Revision ID: 20260913_04
Revises: 20260912_03
"""
from alembic import op
import sqlalchemy as sa

revision = "20260913_04"
down_revision = "20260912_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "route_candidates",
        sa.Column("risk_data_status", sa.String(32), nullable=True, server_default="UNKNOWN"),
    )


def downgrade() -> None:
    op.drop_column("route_candidates", "risk_data_status")
