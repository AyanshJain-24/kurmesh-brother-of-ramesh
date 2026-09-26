import math
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IcebergDemoInferenceRequest(Payload):
    """Frozen Phase 5F feature vector; callers must not submit raw positions."""

    current_x_m: float
    current_y_m: float
    previous_dx_m: float
    previous_dy_m: float
    previous_delta_longitude_deg: float
    day_of_year_sin: float
    day_of_year_cos: float

    @field_validator("current_x_m", "current_y_m", "previous_dx_m", "previous_dy_m", "previous_delta_longitude_deg", "day_of_year_sin", "day_of_year_cos")
    @classmethod
    def finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("must be finite")
        return value


class RegisterRequest(Payload):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    full_name: str = Field(min_length=1, max_length=200)


class LoginRequest(Payload):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)


class VesselRequest(Payload):
    name: str = Field(min_length=1, max_length=200)
    vessel_type: str = Field(min_length=1, max_length=80)
    imo_number: str | None = Field(default=None, max_length=20)
    specifications: dict[str, Any] = Field(default_factory=dict)


class PointLocation(Payload):
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-90, le=90)


class MissionCreateRequest(Payload):
    name: str = Field(min_length=1, max_length=200)
    vessel_id: uuid.UUID | None = None
    departure_at: datetime | None = None
    origin: PointLocation | None = None
    destination: PointLocation | None = None

    @model_validator(mode="after")
    def paired_coordinates(self):
        if (self.origin is None) != (self.destination is None):
            raise ValueError("origin and destination must be provided together")
        return self


class MissionUpdateRequest(Payload):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    vessel_id: uuid.UUID | None = None
    departure_at: datetime | None = None
    origin: PointLocation | None = None
    destination: PointLocation | None = None

    @model_validator(mode="after")
    def paired_coordinates(self):
        if (self.origin is None) != (self.destination is None):
            raise ValueError("origin and destination must be provided together")
        return self


class MissionTransitionRequest(Payload):
    state: Literal["DRAFT", "PLANNING", "ANALYZING", "ROUTES_AVAILABLE", "UNDER_REVIEW", "APPROVED", "REJECTED", "COMPLETED", "FAILED"]


class ConstraintRequest(Payload):
    constraint_type: str = Field(min_length=1, max_length=80)
    value: dict[str, Any]


class ReviewRequest(Payload):
    decision: Literal["RECOMMENDED", "NOT_RECOMMENDED", "NEEDS_CHANGES"]
    reason: str | None = Field(default=None, max_length=5000)


class ApprovalRequest(Payload):
    decision: Literal["APPROVED", "REJECTED"]
    reason: str | None = Field(default=None, max_length=5000)


class SimulationRequest(Payload):
    mission_id: uuid.UUID | None = None
    scenario: dict[str, Any]


class EnvironmentSourceCreateRequest(Payload):
    provider: str = Field(min_length=1, max_length=120)
    source: str = Field(min_length=1, max_length=200)
    url: str | None = Field(default=None, max_length=2000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EnvironmentSourceUpdateRequest(Payload):
    provider: str | None = Field(default=None, min_length=1, max_length=120)
    source: str | None = Field(default=None, min_length=1, max_length=200)
    url: str | None = Field(default=None, max_length=2000)
    metadata: dict[str, Any] | None = None


class EnvironmentObservationCreateRequest(Payload):
    source_id: uuid.UUID
    observation_type: str = Field(min_length=1, max_length=100)
    status: Literal["LIVE", "STALE", "UNAVAILABLE", "ERROR", "DEGRADED"]
    value: dict[str, Any]
    units: str = Field(min_length=1, max_length=64)
    quality: str | None = Field(default=None, max_length=64)
    resolution: str | None = Field(default=None, max_length=64)
    retrieved_at: datetime
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    location: PointLocation | None = None


class ModelVersionCreateRequest(Payload):
    name: str = Field(min_length=1, max_length=160)
    version: str = Field(min_length=1, max_length=80)
    status: str = Field(min_length=1, max_length=32)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ModelVersionUpdateRequest(Payload):
    status: str | None = Field(default=None, min_length=1, max_length=32)
    metadata: dict[str, Any] | None = None


class ModelArtifactCreateRequest(Payload):
    path: str = Field(min_length=1, max_length=2000)
    sha256: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    artifact_type: str = Field(min_length=1, max_length=80)


class PredictionCreateRequest(Payload):
    mission_id: uuid.UUID
    model_version_id: uuid.UUID
    status: Literal["PENDING", "FAILED", "MODEL_UNAVAILABLE"]
    input_provenance: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] | None = None
    reason: str | None = None


class GeoJSONLineString(Payload):
    type: Literal["LineString"]
    coordinates: list[list[float]] = Field(min_length=2)

    @field_validator("coordinates")
    @classmethod
    def validate_coordinates(cls, value: list[list[float]]) -> list[list[float]]:
        for point in value:
            if len(point) != 2 or not -180 <= point[0] <= 180 or not -90 <= point[1] <= 90:
                raise ValueError("coordinates must contain [longitude, latitude] pairs in range")
        return value


class RouteCandidateCreateRequest(Payload):
    version: int = Field(ge=1)
    geometry: GeoJSONLineString
    prediction_id: uuid.UUID | None = None
    status: Literal["DRAFT", "READY", "REJECTED"] = "DRAFT"
    distance_nm: float | None = Field(default=None, ge=0)
    estimated_duration_hours: float | None = Field(default=None, ge=0)
    risk_score: float | None = Field(default=None, ge=0)
    risk_components: dict[str, Any] = Field(default_factory=dict)
    environmental_snapshot: dict[str, Any] = Field(default_factory=dict)
    algorithm_version: str = Field(min_length=1, max_length=80)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RouteCandidateUpdateRequest(Payload):
    status: Literal["DRAFT", "READY", "REJECTED"] | None = None
    distance_nm: float | None = Field(default=None, ge=0)
    estimated_duration_hours: float | None = Field(default=None, ge=0)
    risk_score: float | None = Field(default=None, ge=0)
    risk_components: dict[str, Any] | None = None
    environmental_snapshot: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


class RouteCreateRequest(Payload):
    route_candidate_id: uuid.UUID
    metadata: dict[str, Any] = Field(default_factory=dict)


class RouteUpdateRequest(Payload):
    status: Literal["DRAFT", "ACTIVE", "RETIRED"] | None = None
    metadata: dict[str, Any] | None = None


class GovernedReviewRequest(Payload):
    decision: Literal["APPROVED", "REJECTED", "CHANGES_REQUESTED"]
    comments: str | None = Field(default=None, max_length=5000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class GovernedApprovalRequest(Payload):
    decision: Literal["APPROVED", "REJECTED"]
    comments: str | None = Field(default=None, max_length=5000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AlertCreateRequest(Payload):
    mission_id: uuid.UUID
    severity: Literal["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"]
    category: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=5000)


class AlertAcknowledgeRequest(Payload):
    status: Literal["ACKNOWLEDGED", "RESOLVED"] = "ACKNOWLEDGED"


class ProvenanceCreateRequest(Payload):
    entity_type: str = Field(min_length=1, max_length=100)
    entity_id: uuid.UUID
    source_type: str = Field(min_length=1, max_length=100)
    source_reference: str = Field(min_length=1, max_length=2000)
    retrieved_at: datetime | None = None
    source_timestamp: datetime | None = None
    checksum: str | None = Field(default=None, max_length=128)
    details: dict[str, Any] = Field(default_factory=dict)
