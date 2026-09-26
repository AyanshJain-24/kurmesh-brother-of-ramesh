"""Add governed routing workflow persistence fields.

Revision ID: 20260912_03
Revises: 20260911_02
"""
from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geometry
from sqlalchemy.dialects.postgresql import UUID

revision = "20260912_03"
down_revision = "20260911_02"
branch_labels = depends_on = None


def upgrade() -> None:
    op.add_column("route_candidates", sa.Column("prediction_id", UUID(as_uuid=True), sa.ForeignKey("predictions.id", ondelete="SET NULL")))
    op.add_column("route_candidates", sa.Column("status", sa.String(32), nullable=False, server_default="DRAFT"))
    op.add_column("route_candidates", sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")))
    op.create_index("ix_route_candidates_prediction_id", "route_candidates", ["prediction_id"])
    op.add_column("routes", sa.Column("geometry", Geometry("LINESTRING", srid=4326, spatial_index=False)))
    op.add_column("routes", sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")))
    op.create_index("idx_routes_geometry_gist", "routes", ["geometry"], postgresql_using="gist")
    op.add_column("route_reviews", sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")))
    op.add_column("route_approvals", sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")))
    op.add_column("alerts", sa.Column("category", sa.String(80), nullable=False, server_default="GENERAL"))
    op.add_column("alerts", sa.Column("title", sa.String(200), nullable=False, server_default="Alert"))
    op.add_column("alerts", sa.Column("acknowledged_by_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")))
    op.add_column("alerts", sa.Column("acknowledged_at", sa.DateTime(timezone=True)))
    op.add_column("provenance_records", sa.Column("retrieved_at", sa.DateTime(timezone=True)))
    op.add_column("provenance_records", sa.Column("source_timestamp", sa.DateTime(timezone=True)))
    op.add_column("provenance_records", sa.Column("checksum", sa.String(128)))


def downgrade() -> None:
    op.drop_index("idx_routes_geometry_gist", table_name="routes")
    op.drop_index("ix_route_candidates_prediction_id", table_name="route_candidates")
    for table, column in (("provenance_records", "checksum"), ("provenance_records", "source_timestamp"), ("provenance_records", "retrieved_at"), ("alerts", "acknowledged_at"), ("alerts", "acknowledged_by_id"), ("alerts", "title"), ("alerts", "category"), ("route_approvals", "metadata_json"), ("route_reviews", "metadata_json"), ("routes", "metadata_json"), ("routes", "geometry"), ("route_candidates", "metadata_json"), ("route_candidates", "status"), ("route_candidates", "prediction_id")):
        op.drop_column(table, column)
