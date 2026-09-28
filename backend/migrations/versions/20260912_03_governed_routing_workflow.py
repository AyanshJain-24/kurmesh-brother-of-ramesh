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
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"
    json_default = sa.text("'{}'::json") if is_pg else sa.text("'{}'")

    with op.batch_alter_table("route_candidates") as batch_op:
        batch_op.add_column(sa.Column("prediction_id", UUID(as_uuid=True), sa.ForeignKey("predictions.id", ondelete="SET NULL", name="fk_route_candidates_prediction_id")))
        batch_op.add_column(sa.Column("status", sa.String(32), nullable=False, server_default="DRAFT"))
        batch_op.add_column(sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=json_default))
        batch_op.create_index("ix_route_candidates_prediction_id", ["prediction_id"])

    with op.batch_alter_table("routes") as batch_op:
        batch_op.add_column(sa.Column("geometry", Geometry("LINESTRING", srid=4326, spatial_index=False)))
        batch_op.add_column(sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=json_default))
        if is_pg:
            batch_op.create_index("idx_routes_geometry_gist", ["geometry"], postgresql_using="gist")
        else:
            batch_op.create_index("idx_routes_geometry_gist", ["geometry"])

    with op.batch_alter_table("route_reviews") as batch_op:
        batch_op.add_column(sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=json_default))

    with op.batch_alter_table("route_approvals") as batch_op:
        batch_op.add_column(sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=json_default))

    with op.batch_alter_table("alerts") as batch_op:
        batch_op.add_column(sa.Column("category", sa.String(80), nullable=False, server_default="GENERAL"))
        batch_op.add_column(sa.Column("title", sa.String(200), nullable=False, server_default="Alert"))
        batch_op.add_column(sa.Column("acknowledged_by_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL", name="fk_alerts_acknowledged_by_id")))
        batch_op.add_column(sa.Column("acknowledged_at", sa.DateTime(timezone=True)))

    with op.batch_alter_table("provenance_records") as batch_op:
        batch_op.add_column(sa.Column("retrieved_at", sa.DateTime(timezone=True)))
        batch_op.add_column(sa.Column("source_timestamp", sa.DateTime(timezone=True)))
        batch_op.add_column(sa.Column("checksum", sa.String(128)))


def downgrade() -> None:
    with op.batch_alter_table("routes") as batch_op:
        batch_op.drop_index("idx_routes_geometry_gist")
        batch_op.drop_column("metadata_json")
        batch_op.drop_column("geometry")
    with op.batch_alter_table("route_candidates") as batch_op:
        batch_op.drop_index("ix_route_candidates_prediction_id")
        batch_op.drop_column("metadata_json")
        batch_op.drop_column("status")
        batch_op.drop_column("prediction_id")
    with op.batch_alter_table("route_approvals") as batch_op:
        batch_op.drop_column("metadata_json")
    with op.batch_alter_table("route_reviews") as batch_op:
        batch_op.drop_column("metadata_json")
    with op.batch_alter_table("alerts") as batch_op:
        batch_op.drop_column("acknowledged_at")
        batch_op.drop_column("acknowledged_by_id")
        batch_op.drop_column("title")
        batch_op.drop_column("category")
    with op.batch_alter_table("provenance_records") as batch_op:
        batch_op.drop_column("checksum")
        batch_op.drop_column("source_timestamp")
        batch_op.drop_column("retrieved_at")
