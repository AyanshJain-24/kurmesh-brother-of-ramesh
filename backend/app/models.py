import uuid
from datetime import datetime
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class Timestamped:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class Role(Timestamped, Base):
    __tablename__ = "roles"
    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    users: Mapped[list["User"]] = relationship(secondary="user_roles", back_populates="roles")


class User(Timestamped, Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    full_name: Mapped[str | None] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    roles: Mapped[list[Role]] = relationship(secondary="user_roles", back_populates="users")
    missions: Mapped[list["Mission"]] = relationship(back_populates="created_by", passive_deletes=True)


class UserRole(Base):
    __tablename__ = "user_roles"
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)


class Vessel(Timestamped, Base):
    __tablename__ = "vessels"
    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    imo_number: Mapped[str | None] = mapped_column(String(20), unique=True)
    vessel_type: Mapped[str] = mapped_column(String(80), nullable=False)
    specifications: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    missions: Mapped[list["Mission"]] = relationship(back_populates="vessel")


class Mission(Timestamped, Base):
    __tablename__ = "missions"
    __table_args__ = (CheckConstraint("state IN ('DRAFT','PLANNING','ANALYZING','ROUTES_AVAILABLE','UNDER_REVIEW','APPROVED','REJECTED','COMPLETED','FAILED')", name="ck_mission_state"), Index("ix_missions_state_created", "state", "created_at"))
    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    state: Mapped[str] = mapped_column(String(32), default="DRAFT", nullable=False)
    departure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    origin: Mapped[str | None] = mapped_column(Geometry("POINT", srid=4326, spatial_index=True))
    destination: Mapped[str | None] = mapped_column(Geometry("POINT", srid=4326, spatial_index=True))
    vessel_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("vessels.id", ondelete="SET NULL"))
    created_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    vessel: Mapped[Vessel | None] = relationship(back_populates="missions")
    created_by: Mapped[User] = relationship(back_populates="missions")
    constraints: Mapped[list["MissionConstraint"]] = relationship(back_populates="mission", cascade="all, delete-orphan")
    route_candidates: Mapped[list["RouteCandidate"]] = relationship(back_populates="mission", cascade="all, delete-orphan")


class MissionConstraint(Timestamped, Base):
    __tablename__ = "mission_constraints"
    id: Mapped[uuid.UUID] = uuid_pk()
    mission_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("missions.id", ondelete="CASCADE"), nullable=False, index=True)
    constraint_type: Mapped[str] = mapped_column(String(80), nullable=False)
    value: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    mission: Mapped[Mission] = relationship(back_populates="constraints")


class EnvironmentSource(Timestamped, Base):
    __tablename__ = "environment_sources"
    id: Mapped[uuid.UUID] = uuid_pk()
    provider: Mapped[str] = mapped_column(String(120), nullable=False)
    source: Mapped[str] = mapped_column(String(200), nullable=False)
    url: Mapped[str | None] = mapped_column(String(2000))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    __table_args__ = (UniqueConstraint("provider", "source", name="uq_environment_source_provider_source"),)


class EnvironmentObservation(Timestamped, Base):
    __tablename__ = "environment_observations"
    __table_args__ = (
        CheckConstraint("status IN ('LIVE','STALE','UNAVAILABLE','ERROR','DEGRADED')", name="ck_environment_observation_availability"),
        Index("ix_environment_observation_validity", "valid_from", "valid_to"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("environment_sources.id"), nullable=False, index=True)
    observation_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    value: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    units: Mapped[str] = mapped_column(String(64), nullable=False)
    quality: Mapped[str | None] = mapped_column(String(64))
    resolution: Mapped[str | None] = mapped_column(String(64))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    location: Mapped[str | None] = mapped_column(Geometry("GEOMETRY", srid=4326, spatial_index=True))
    source: Mapped[EnvironmentSource] = relationship()


class ModelVersion(Timestamped, Base):
    __tablename__ = "model_versions"
    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    version: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    __table_args__ = (UniqueConstraint("name", "version", name="uq_model_name_version"),)


class ModelArtifact(Timestamped, Base):
    __tablename__ = "model_artifacts"
    id: Mapped[uuid.UUID] = uuid_pk()
    model_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("model_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    path: Mapped[str] = mapped_column(String(2000), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_type: Mapped[str] = mapped_column(String(80), nullable=False)
    model_version: Mapped[ModelVersion] = relationship()
    __table_args__ = (UniqueConstraint("model_version_id", "path", name="uq_model_artifact_path"),)


class Prediction(Timestamped, Base):
    __tablename__ = "predictions"
    id: Mapped[uuid.UUID] = uuid_pk()
    mission_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("missions.id", ondelete="SET NULL"), index=True)
    model_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("model_versions.id", ondelete="SET NULL"), index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    input_provenance: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    output: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    reason: Mapped[str | None] = mapped_column(Text)


class RouteCandidate(Timestamped, Base):
    __tablename__ = "route_candidates"
    __table_args__ = (UniqueConstraint("mission_id", "version", name="uq_route_candidate_mission_version"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    mission_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("missions.id", ondelete="CASCADE"), nullable=False, index=True)
    prediction_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("predictions.id", ondelete="SET NULL"), index=True)
    version: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="DRAFT", nullable=False)
    geometry: Mapped[str] = mapped_column(Geometry("LINESTRING", srid=4326, spatial_index=True), nullable=False)
    distance_nm: Mapped[float | None]
    estimated_duration_hours: Mapped[float | None]
    risk_score: Mapped[float | None]
    risk_components: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    environmental_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(80), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    mission: Mapped[Mission] = relationship(back_populates="route_candidates")


class Route(Timestamped, Base):
    __tablename__ = "routes"
    id: Mapped[uuid.UUID] = uuid_pk()
    route_candidate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("route_candidates.id", ondelete="CASCADE"), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    geometry: Mapped[str | None] = mapped_column(Geometry("LINESTRING", srid=4326, spatial_index=True))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    route_candidate: Mapped[RouteCandidate] = relationship()


class RouteReview(Timestamped, Base):
    __tablename__ = "route_reviews"
    id: Mapped[uuid.UUID] = uuid_pk()
    route_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("routes.id", ondelete="CASCADE"), nullable=False, index=True)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class RouteApproval(Timestamped, Base):
    __tablename__ = "route_approvals"
    id: Mapped[uuid.UUID] = uuid_pk()
    route_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("routes.id", ondelete="CASCADE"), nullable=False, index=True)
    approver_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    __table_args__ = (CheckConstraint("decision IN ('APPROVED','REJECTED')", name="ck_route_approval_decision"),)


class Alert(Timestamped, Base):
    __tablename__ = "alerts"
    id: Mapped[uuid.UUID] = uuid_pk()
    mission_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("missions.id", ondelete="SET NULL"), index=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    category: Mapped[str] = mapped_column(String(80), default="GENERAL", nullable=False)
    title: Mapped[str] = mapped_column(String(200), default="Alert", nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    acknowledged_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SimulationRun(Timestamped, Base):
    __tablename__ = "simulation_runs"
    id: Mapped[uuid.UUID] = uuid_pk()
    mission_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("missions.id", ondelete="SET NULL"), index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    scenario: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    results: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    is_simulation: Mapped[bool] = mapped_column(default=True, nullable=False)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[uuid.UUID] = uuid_pk()
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class ProvenanceRecord(Timestamped, Base):
    __tablename__ = "provenance_records"
    id: Mapped[uuid.UUID] = uuid_pk()
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    source_type: Mapped[str] = mapped_column(String(100), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(2000), nullable=False)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checksum: Mapped[str | None] = mapped_column(String(128))
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    __table_args__ = (Index("ix_provenance_entity", "entity_type", "entity_id"),)
