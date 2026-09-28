"""Explicit initial persistence schema."""
from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geometry
from sqlalchemy.dialects.postgresql import UUID

revision = "20260910_01"
down_revision = None
branch_labels = depends_on = None

U = UUID(as_uuid=True)
J = sa.JSON()
T = lambda: (sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")))
I = lambda: sa.Column("id", U, primary_key=True, nullable=False)
P = lambda kind: Geometry(kind, srid=4326, spatial_index=False)

def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"
    if is_pg:
        op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    now_default = sa.text("now()") if is_pg else sa.func.now()
    json_default = sa.text("'{}'::json") if is_pg else sa.text("'{}'")

    U = UUID(as_uuid=True)
    J = sa.JSON()
    T = lambda: (sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now_default), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=now_default))
    I = lambda: sa.Column("id", U, primary_key=True, nullable=False)
    P = lambda kind: Geometry(kind, srid=4326, spatial_index=False)

    op.create_table("roles", I(), sa.Column("name", sa.String(80), nullable=False), *T(), sa.UniqueConstraint("name"))
    op.create_table("users", I(), sa.Column("email", sa.String(320), nullable=False), sa.Column("password_hash", sa.String(255), nullable=False), sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()), *T(), sa.UniqueConstraint("email"))
    op.create_index("ix_users_email", "users", ["email"])
    op.create_table("user_roles", sa.Column("user_id", U, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True), sa.Column("role_id", U, sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True))
    op.create_table("vessels", I(), sa.Column("name", sa.String(200), nullable=False), sa.Column("imo_number", sa.String(20)), sa.Column("vessel_type", sa.String(80), nullable=False), sa.Column("specifications", J, nullable=False, server_default=json_default), *T(), sa.UniqueConstraint("imo_number"))
    op.create_table("missions", I(), sa.Column("name", sa.String(200), nullable=False), sa.Column("state", sa.String(32), nullable=False, server_default="DRAFT"), sa.Column("departure_at", sa.DateTime(timezone=True)), sa.Column("origin", P("POINT")), sa.Column("destination", P("POINT")), sa.Column("vessel_id", U, sa.ForeignKey("vessels.id", ondelete="SET NULL")), sa.Column("created_by_id", U, sa.ForeignKey("users.id"), nullable=False), *T(), sa.CheckConstraint("state IN ('DRAFT','PLANNING','ANALYZING','ROUTES_AVAILABLE','UNDER_REVIEW','APPROVED','REJECTED','COMPLETED','FAILED')", name="ck_mission_state"))
    op.create_index("ix_missions_state_created", "missions", ["state", "created_at"])
    op.create_index("idx_missions_origin_gist", "missions", ["origin"], postgresql_using="gist")
    op.create_index("idx_missions_destination_gist", "missions", ["destination"], postgresql_using="gist")
    op.create_table("mission_constraints", I(), sa.Column("mission_id", U, sa.ForeignKey("missions.id", ondelete="CASCADE"), nullable=False), sa.Column("constraint_type", sa.String(80), nullable=False), sa.Column("value", J, nullable=False), *T())
    op.create_index("ix_mission_constraints_mission_id", "mission_constraints", ["mission_id"])
    op.create_table("environment_sources", I(), sa.Column("provider", sa.String(120), nullable=False), sa.Column("source", sa.String(200), nullable=False), sa.Column("url", sa.String(2000)), sa.Column("metadata_json", J, nullable=False, server_default=json_default), *T(), sa.UniqueConstraint("provider", "source", name="uq_environment_source_provider_source"))
    op.create_table("environment_observations", I(), sa.Column("source_id", U, sa.ForeignKey("environment_sources.id"), nullable=False), sa.Column("observation_type", sa.String(100), nullable=False), sa.Column("status", sa.String(20), nullable=False), sa.Column("value", J, nullable=False), sa.Column("units", sa.String(64), nullable=False), sa.Column("quality", sa.String(64)), sa.Column("resolution", sa.String(64)), sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False), sa.Column("valid_from", sa.DateTime(timezone=True)), sa.Column("valid_to", sa.DateTime(timezone=True)), sa.Column("location", P("GEOMETRY")), *T(), sa.CheckConstraint("status IN ('LIVE','STALE','UNAVAILABLE','ERROR','DEGRADED')", name="ck_environment_observation_availability"))
    op.create_index("ix_environment_observations_source_id", "environment_observations", ["source_id"])
    op.create_index("ix_environment_observation_validity", "environment_observations", ["valid_from", "valid_to"])
    op.create_index("idx_environment_observations_location_gist", "environment_observations", ["location"], postgresql_using="gist")
    op.create_table("model_versions", I(), sa.Column("name", sa.String(160), nullable=False), sa.Column("version", sa.String(80), nullable=False), sa.Column("status", sa.String(32), nullable=False), sa.Column("metadata_json", J, nullable=False, server_default=json_default), *T(), sa.UniqueConstraint("name", "version", name="uq_model_name_version"))
    op.create_table("model_artifacts", I(), sa.Column("model_version_id", U, sa.ForeignKey("model_versions.id", ondelete="CASCADE"), nullable=False), sa.Column("path", sa.String(2000), nullable=False), sa.Column("sha256", sa.String(64), nullable=False), sa.Column("artifact_type", sa.String(80), nullable=False), *T(), sa.UniqueConstraint("model_version_id", "path", name="uq_model_artifact_path"))
    op.create_index("ix_model_artifacts_model_version_id", "model_artifacts", ["model_version_id"])
    op.create_table("predictions", I(), sa.Column("mission_id", U, sa.ForeignKey("missions.id", ondelete="SET NULL")), sa.Column("model_version_id", U, sa.ForeignKey("model_versions.id", ondelete="SET NULL")), sa.Column("status", sa.String(32), nullable=False), sa.Column("input_provenance", J, nullable=False, server_default=json_default), sa.Column("output", J), sa.Column("reason", sa.Text()), *T())
    op.create_index("ix_predictions_mission_id", "predictions", ["mission_id"]); op.create_index("ix_predictions_model_version_id", "predictions", ["model_version_id"])
    op.create_table("route_candidates", I(), sa.Column("mission_id", U, sa.ForeignKey("missions.id", ondelete="CASCADE"), nullable=False), sa.Column("version", sa.Integer(), nullable=False), sa.Column("geometry", P("LINESTRING"), nullable=False), sa.Column("distance_nm", sa.Float()), sa.Column("estimated_duration_hours", sa.Float()), sa.Column("risk_score", sa.Float()), sa.Column("risk_components", J, nullable=False, server_default=json_default), sa.Column("environmental_snapshot", J, nullable=False, server_default=json_default), sa.Column("algorithm_version", sa.String(80), nullable=False), *T(), sa.UniqueConstraint("mission_id", "version", name="uq_route_candidate_mission_version"))
    op.create_index("ix_route_candidates_mission_id", "route_candidates", ["mission_id"]); op.create_index("idx_route_candidates_geometry_gist", "route_candidates", ["geometry"], postgresql_using="gist")
    op.create_table("routes", I(), sa.Column("route_candidate_id", U, sa.ForeignKey("route_candidates.id", ondelete="CASCADE"), nullable=False), sa.Column("status", sa.String(32), nullable=False), *T(), sa.UniqueConstraint("route_candidate_id"))
    op.create_table("route_reviews", I(), sa.Column("route_id", U, sa.ForeignKey("routes.id", ondelete="CASCADE"), nullable=False), sa.Column("reviewer_id", U, sa.ForeignKey("users.id"), nullable=False), sa.Column("decision", sa.String(32), nullable=False), sa.Column("reason", sa.Text()), *T())
    op.create_index("ix_route_reviews_route_id", "route_reviews", ["route_id"])
    op.create_table("route_approvals", I(), sa.Column("route_id", U, sa.ForeignKey("routes.id", ondelete="CASCADE"), nullable=False), sa.Column("approver_id", U, sa.ForeignKey("users.id"), nullable=False), sa.Column("decision", sa.String(16), nullable=False), sa.Column("reason", sa.Text()), *T(), sa.CheckConstraint("decision IN ('APPROVED','REJECTED')", name="ck_route_approval_decision"))
    op.create_index("ix_route_approvals_route_id", "route_approvals", ["route_id"])
    op.create_table("alerts", I(), sa.Column("mission_id", U, sa.ForeignKey("missions.id", ondelete="SET NULL")), sa.Column("severity", sa.String(16), nullable=False), sa.Column("status", sa.String(32), nullable=False), sa.Column("message", sa.Text(), nullable=False), sa.Column("resolved_at", sa.DateTime(timezone=True)), *T())
    op.create_index("ix_alerts_mission_id", "alerts", ["mission_id"])
    op.create_table("simulation_runs", I(), sa.Column("mission_id", U, sa.ForeignKey("missions.id", ondelete="SET NULL")), sa.Column("status", sa.String(32), nullable=False), sa.Column("scenario", J, nullable=False), sa.Column("results", J), sa.Column("is_simulation", sa.Boolean(), nullable=False, server_default=sa.true()), *T())
    op.create_index("ix_simulation_runs_mission_id", "simulation_runs", ["mission_id"])
    op.create_table("audit_events", I(), sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=now_default), sa.Column("actor_id", U, sa.ForeignKey("users.id", ondelete="SET NULL")), sa.Column("event_type", sa.String(100), nullable=False), sa.Column("entity_type", sa.String(100), nullable=False), sa.Column("entity_id", U), sa.Column("payload", J, nullable=False, server_default=json_default))
    op.create_index("ix_audit_events_occurred_at", "audit_events", ["occurred_at"]); op.create_index("ix_audit_events_actor_id", "audit_events", ["actor_id"]); op.create_index("ix_audit_events_event_type", "audit_events", ["event_type"])
    op.create_table("provenance_records", I(), sa.Column("entity_type", sa.String(100), nullable=False), sa.Column("entity_id", U, nullable=False), sa.Column("source_type", sa.String(100), nullable=False), sa.Column("source_reference", sa.String(2000), nullable=False), sa.Column("details", J, nullable=False, server_default=json_default), *T())
    op.create_index("ix_provenance_entity", "provenance_records", ["entity_type", "entity_id"])

def downgrade() -> None:
    indexes = [("ix_provenance_entity","provenance_records"),("ix_audit_events_event_type","audit_events"),("ix_audit_events_actor_id","audit_events"),("ix_audit_events_occurred_at","audit_events"),("ix_simulation_runs_mission_id","simulation_runs"),("ix_alerts_mission_id","alerts"),("ix_route_approvals_route_id","route_approvals"),("ix_route_reviews_route_id","route_reviews"),("idx_route_candidates_geometry_gist","route_candidates"),("ix_route_candidates_mission_id","route_candidates"),("ix_predictions_model_version_id","predictions"),("ix_predictions_mission_id","predictions"),("ix_model_artifacts_model_version_id","model_artifacts"),("idx_environment_observations_location_gist","environment_observations"),("ix_environment_observation_validity","environment_observations"),("ix_environment_observations_source_id","environment_observations"),("ix_mission_constraints_mission_id","mission_constraints"),("idx_missions_destination_gist","missions"),("idx_missions_origin_gist","missions"),("ix_missions_state_created","missions"),("ix_users_email","users")]
    for name, table in indexes: op.drop_index(name, table_name=table)
    for table in ["provenance_records","audit_events","simulation_runs","alerts","route_approvals","route_reviews","routes","route_candidates","predictions","model_artifacts","model_versions","environment_observations","environment_sources","mission_constraints","missions","vessels","user_roles","users","roles"]: op.drop_table(table)
