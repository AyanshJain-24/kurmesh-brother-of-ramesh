import json
import uuid
from datetime import UTC, datetime

from flask import Blueprint, g, jsonify, request
from pydantic import ValidationError
from geoalchemy2.elements import WKTElement
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.auth import ApiError, authenticate, issue_token, password_hash, password_matches, require_roles
from app.models import (Alert, AuditEvent, EnvironmentObservation, EnvironmentSource, ModelArtifact, ModelVersion, Mission, MissionConstraint,
                        Prediction, ProvenanceRecord, Route, RouteApproval, RouteCandidate, RouteReview,
                        SimulationRun, User, Vessel)
from app.repositories import MissionRepository, Repository, RoleRepository, UserRepository
from app.api.v1.schemas import (ApprovalRequest, ConstraintRequest, EnvironmentObservationCreateRequest, EnvironmentSourceCreateRequest, EnvironmentSourceUpdateRequest, LoginRequest, MissionCreateRequest, MissionUpdateRequest, ModelArtifactCreateRequest, ModelVersionCreateRequest, ModelVersionUpdateRequest, PredictionCreateRequest,
                                MissionTransitionRequest, RegisterRequest, ReviewRequest, SimulationRequest,
                                VesselRequest)

api_blueprint = Blueprint("application", __name__)
TRANSITIONS = {"DRAFT": {"PLANNING", "FAILED"}, "PLANNING": {"ANALYZING", "FAILED"}, "ANALYZING": {"ROUTES_AVAILABLE", "FAILED"}, "ROUTES_AVAILABLE": {"UNDER_REVIEW", "FAILED"}, "UNDER_REVIEW": {"APPROVED", "REJECTED", "FAILED"}, "APPROVED": {"COMPLETED", "FAILED"}, "REJECTED": set(), "COMPLETED": set(), "FAILED": set()}


def body(schema):
    try:
        return schema.model_validate(request.get_json(silent=True) or {})
    except ValidationError as exc:
        raise ApiError("VALIDATION_ERROR", "Request validation failed", 422) from exc


def page(query, model, filters=()):
    try:
        limit = min(max(int(request.args.get("limit", 50)), 1), 100)
        offset = max(int(request.args.get("offset", 0)), 0)
    except ValueError:
        raise ApiError("VALIDATION_ERROR", "limit and offset must be integers", 422) from None
    for predicate in filters:
        query = query.where(predicate)
    rows = list(g.db.scalars(query.limit(limit).offset(offset)))
    return jsonify({"items": [serialize(row) for row in rows], "limit": limit, "offset": offset})


def _mission_location(geometry):
    if geometry is None:
        return None
    longitude, latitude = g.db.execute(select(func.ST_X(geometry), func.ST_Y(geometry))).one()
    return {"longitude": longitude, "latitude": latitude}


def serialize(value):
    if isinstance(value, User): return {"id": str(value.id), "email": value.email, "full_name": value.full_name, "is_active": value.is_active, "roles": [r.name for r in value.roles]}
    if isinstance(value, Vessel): return {"id": str(value.id), "name": value.name, "vessel_type": value.vessel_type, "imo_number": value.imo_number, "specifications": value.specifications}
    if isinstance(value, Mission): return {"id": str(value.id), "name": value.name, "state": value.state, "vessel_id": str(value.vessel_id) if value.vessel_id else None, "departure_at": value.departure_at.isoformat() if value.departure_at else None, "origin": _mission_location(value.origin), "destination": _mission_location(value.destination)}
    if isinstance(value, MissionConstraint): return {"id": str(value.id), "mission_id": str(value.mission_id), "constraint_type": value.constraint_type, "value": value.value}
    if isinstance(value, Route):
        raw_geom = g.db.scalar(select(func.ST_AsGeoJSON(value.geometry))) if value.geometry is not None else None
        return {"id": str(value.id), "route_candidate_id": str(value.route_candidate_id), "status": value.status, "geometry": json.loads(raw_geom) if raw_geom else None, "metadata": value.metadata_json if hasattr(value, "metadata_json") else {}}
    if isinstance(value, RouteCandidate):
        raw_geom = g.db.scalar(select(func.ST_AsGeoJSON(value.geometry))) if value.geometry is not None else None
        return {"id": str(value.id), "mission_id": str(value.mission_id), "prediction_id": str(value.prediction_id) if value.prediction_id else None, "version": value.version, "status": value.status, "risk_data_status": getattr(value, "risk_data_status", "UNKNOWN"), "geometry": json.loads(raw_geom) if raw_geom else None, "distance_nm": value.distance_nm, "estimated_duration_hours": value.estimated_duration_hours, "risk_score": value.risk_score, "risk_components": value.risk_components, "environmental_snapshot": value.environmental_snapshot, "algorithm_version": value.algorithm_version, "metadata": value.metadata_json}
    if isinstance(value, Alert): return {"id": str(value.id), "mission_id": str(value.mission_id) if value.mission_id else None, "severity": value.severity, "status": value.status, "message": value.message}
    if isinstance(value, SimulationRun): return {"id": str(value.id), "mission_id": str(value.mission_id) if value.mission_id else None, "status": value.status, "is_simulation": True}
    if isinstance(value, AuditEvent): return {"id": str(value.id), "event_type": value.event_type, "entity_type": value.entity_type, "entity_id": str(value.entity_id) if value.entity_id else None, "occurred_at": value.occurred_at.isoformat()}
    if isinstance(value, ProvenanceRecord): return {"id": str(value.id), "entity_type": value.entity_type, "entity_id": str(value.entity_id), "source_type": value.source_type, "source_reference": value.source_reference, "details": value.details}
    if isinstance(value, ModelVersion): return {"id": str(value.id), "name": value.name, "version": value.version, "status": value.status, "metadata": value.metadata_json}
    if isinstance(value, Prediction): return {"id": str(value.id), "status": value.status, "reason": value.reason, "output": value.output}
    if isinstance(value, EnvironmentSource): return {"id": str(value.id), "provider": value.provider, "source": value.source, "url": value.url, "metadata": value.metadata_json}
    if isinstance(value, EnvironmentObservation): return {"id": str(value.id), "source_id": str(value.source_id), "observation_type": value.observation_type, "status": value.status, "value": value.value, "units": value.units, "quality": value.quality, "resolution": value.resolution, "retrieved_at": value.retrieved_at.isoformat(), "valid_from": value.valid_from.isoformat() if value.valid_from else None, "valid_to": value.valid_to.isoformat() if value.valid_to else None}
    raise TypeError(f"No serializer for {type(value)!r}")


def paginated(query):
    try:
        page_number = max(int(request.args.get("page", 1)), 1)
        page_size = min(max(int(request.args.get("page_size", 20)), 1), 100)
    except ValueError:
        raise ApiError("VALIDATION_ERROR", "page and page_size must be integers", 422) from None
    total = g.db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = list(g.db.scalars(query.limit(page_size).offset((page_number - 1) * page_size)))
    return {"items": rows, "page": page_number, "page_size": page_size, "total": total}


def observation_payload(observation: EnvironmentObservation) -> dict:
    payload = serialize(observation)
    if observation.location is not None:
        longitude, latitude = g.db.execute(select(func.ST_X(observation.location), func.ST_Y(observation.location))).one()
        payload["location"] = {"longitude": longitude, "latitude": latitude}
    else:
        payload["location"] = None
    return payload


def require_mission_access(mission: Mission, user: User) -> None:
    if mission.created_by_id != user.id and "admin" not in {role.name for role in user.roles}:
        raise ApiError("FORBIDDEN", "You are not authorized to access this mission data", 403)


def audit(event_type: str, entity_type: str, entity_id: uuid.UUID | None) -> None:
    actor = getattr(g, "current_user", None)
    g.db.add(AuditEvent(actor_id=actor.id if actor else None, event_type=event_type, entity_type=entity_type, entity_id=entity_id, payload={}))


def commit():
    try:
        g.db.commit()
    except IntegrityError:
        g.db.rollback()
        raise ApiError("CONFLICT", "The requested change conflicts with existing data", 409) from None


@api_blueprint.post("/auth/register")
def register():
    data = body(RegisterRequest)
    email = str(data.email).strip().lower()
    if UserRepository(g.db).by_email(email):
        raise ApiError("CONFLICT", "Email is already registered", 409)
    role_repository = RoleRepository(g.db)
    default_role = role_repository.by_name("user")
    if default_role is None:
        default_role = Role(name="user")
        role_repository.add(default_role)
    user = User(email=email, full_name=data.full_name.strip(), password_hash=password_hash(data.password), roles=[default_role])
    g.db.add(user); commit(); audit("USER_REGISTERED", "User", user.id); commit()
    return jsonify({"user": serialize(user), "access_token": issue_token(user)}), 201


@api_blueprint.post("/auth/login")
def login():
    data = body(LoginRequest); user = UserRepository(g.db).by_email(str(data.email).strip().lower())
    if user is None or not password_matches(user.password_hash, data.password) or not user.is_active:
        raise ApiError("INVALID_CREDENTIALS", "Invalid credentials", 401)
    g.current_user = user; audit("USER_LOGIN", "User", user.id); commit()
    return jsonify({"access_token": issue_token(user), "token_type": "Bearer", "user": serialize(user)})


@api_blueprint.get("/users")
@require_roles("admin")
def users(): return page(select(User).order_by(User.created_at.desc()), User)


@api_blueprint.get("/users/me")
def current_user(): return jsonify(serialize(authenticate(g.db)))


@api_blueprint.get("/auth/me")
def auth_current_user(): return jsonify(serialize(authenticate(g.db)))


@api_blueprint.get("/users/<uuid:user_id>")
def user_by_id(user_id):
    user = authenticate(g.db)
    entity = g.db.get(User, user_id)
    if entity is None:
        raise ApiError("USER_NOT_FOUND", "User not found", 404)
    if entity.id != user.id and "admin" not in {role.name for role in user.roles}:
        raise ApiError("FORBIDDEN", "You are not authorized to view this user", 403)
    return jsonify(serialize(entity))


@api_blueprint.route("/vessels", methods=["GET", "POST"])
def vessels():
    authenticate(g.db)
    if request.method == "GET": return page(select(Vessel).order_by(Vessel.created_at.desc()), Vessel)
    data = body(VesselRequest); vessel = Vessel(**data.model_dump()); g.db.add(vessel); commit(); audit("VESSEL_CREATED", "Vessel", vessel.id); commit()
    return jsonify(serialize(vessel)), 201


@api_blueprint.route("/vessels/<uuid:vessel_id>", methods=["GET", "PATCH", "DELETE"])
def vessel(vessel_id):
    authenticate(g.db); entity = g.db.get(Vessel, vessel_id)
    if entity is None: raise ApiError("NOT_FOUND", "Vessel not found", 404)
    if request.method == "GET": return jsonify(serialize(entity))
    if request.method == "DELETE": g.db.delete(entity); audit("VESSEL_DELETED", "Vessel", vessel_id); commit(); return "", 204
    for key, value in body(VesselRequest).model_dump().items(): setattr(entity, key, value)
    audit("VESSEL_UPDATED", "Vessel", vessel_id); commit(); return jsonify(serialize(entity))


@api_blueprint.route("/missions", methods=["GET", "POST"])
def missions():
    user = authenticate(g.db)
    if request.method == "GET":
        query = select(Mission).order_by(Mission.created_at.desc())
        if state := request.args.get("state"): query = query.where(Mission.state == state)
        try:
            page_number = max(int(request.args.get("page", 1)), 1)
            page_size = min(max(int(request.args.get("page_size", 20)), 1), 100)
        except ValueError:
            raise ApiError("VALIDATION_ERROR", "page and page_size must be integers", 422) from None
        total = g.db.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = list(g.db.scalars(query.limit(page_size).offset((page_number - 1) * page_size)))
        return jsonify({"items": [serialize(row) for row in rows], "page": page_number, "page_size": page_size, "total": total})
    data = body(MissionCreateRequest)
    if data.vessel_id is not None and g.db.get(Vessel, data.vessel_id) is None:
        raise ApiError("VESSEL_NOT_FOUND", "Vessel not found", 404)
    values = data.model_dump(exclude={"origin", "destination"})
    mission = Mission(**values, created_by_id=user.id,
        origin=WKTElement(f"POINT({data.origin.longitude} {data.origin.latitude})", srid=4326) if data.origin else None,
        destination=WKTElement(f"POINT({data.destination.longitude} {data.destination.latitude})", srid=4326) if data.destination else None)
    g.db.add(mission); commit(); audit("MISSION_CREATED", "Mission", mission.id); commit()
    return jsonify(serialize(mission)), 201


@api_blueprint.route("/missions/<uuid:mission_id>", methods=["GET", "PATCH", "DELETE"])
def mission(mission_id):
    user = authenticate(g.db); entity = MissionRepository(g.db).get(mission_id)
    if entity is None: raise ApiError("NOT_FOUND", "Mission not found", 404)
    if request.method == "GET": return jsonify(serialize(entity))
    if entity.created_by_id != user.id and "admin" not in {r.name for r in user.roles}: raise ApiError("FORBIDDEN", "Mission ownership is required", 403)
    if request.method == "DELETE": g.db.delete(entity); commit(); audit("MISSION_DELETED", "Mission", mission_id); commit(); return "", 204
    data = body(MissionUpdateRequest)
    if data.vessel_id is not None and g.db.get(Vessel, data.vessel_id) is None:
        raise ApiError("VESSEL_NOT_FOUND", "Vessel not found", 404)
    values = data.model_dump(exclude_unset=True, exclude={"origin", "destination"})
    for key, value in values.items(): setattr(entity, key, value)
    if data.origin is not None and data.destination is not None:
        entity.origin = WKTElement(f"POINT({data.origin.longitude} {data.origin.latitude})", srid=4326)
        entity.destination = WKTElement(f"POINT({data.destination.longitude} {data.destination.latitude})", srid=4326)
    commit(); audit("MISSION_UPDATED", "Mission", mission_id); commit(); return jsonify(serialize(entity))


@api_blueprint.post("/missions/<uuid:mission_id>/transition")
def transition(mission_id):
    user = authenticate(g.db); entity = g.db.get(Mission, mission_id)
    if entity is None: raise ApiError("MISSION_NOT_FOUND", "Mission not found", 404)
    if entity.created_by_id != user.id and "admin" not in {role.name for role in user.roles}:
        raise ApiError("FORBIDDEN", "Mission ownership is required", 403)
    requested = body(MissionTransitionRequest).state
    if requested == "APPROVED": raise ApiError("HUMAN_APPROVAL_REQUIRED", "Approve a reviewed route using the approval endpoint", 409)
    if requested not in TRANSITIONS[entity.state]: raise ApiError("INVALID_STATE_TRANSITION", f"Cannot transition from {entity.state} to {requested}", 409)
    entity.state = requested; g.current_user = user; audit("MISSION_TRANSITIONED", "Mission", entity.id); commit(); return jsonify(serialize(entity))


@api_blueprint.post("/missions/<uuid:mission_id>/constraints")
def mission_constraint(mission_id):
    user = authenticate(g.db)
    mission = g.db.get(Mission, mission_id)
    if mission is None: raise ApiError("NOT_FOUND", "Mission not found", 404)
    if mission.created_by_id != user.id and "admin" not in {role.name for role in user.roles}:
        raise ApiError("FORBIDDEN", "Mission ownership is required", 403)
    data = body(ConstraintRequest); constraint = MissionConstraint(mission_id=mission_id, **data.model_dump()); g.db.add(constraint); audit("MISSION_CONSTRAINT_CREATED", "MissionConstraint", constraint.id); commit(); return jsonify(serialize(constraint)), 201


@api_blueprint.route("/environment/sources", methods=["GET", "POST"])
def environment_sources():
    authenticate(g.db)
    if request.method == "GET":
        result = paginated(select(EnvironmentSource).order_by(EnvironmentSource.created_at.desc()))
        return jsonify({**result, "items": [serialize(item) for item in result["items"]]})
    data = body(EnvironmentSourceCreateRequest)
    if g.db.scalar(select(EnvironmentSource).where(EnvironmentSource.provider == data.provider, EnvironmentSource.source == data.source)):
        raise ApiError("DUPLICATE_ENVIRONMENT_SOURCE", "An environment source with this provider and source already exists", 409)
    entity = EnvironmentSource(provider=data.provider, source=data.source, url=data.url, metadata_json=data.metadata)
    g.db.add(entity); commit(); audit("ENVIRONMENT_SOURCE_CREATED", "EnvironmentSource", entity.id); commit()
    return jsonify(serialize(entity)), 201


@api_blueprint.route("/environment/sources/<uuid:source_id>", methods=["GET", "PATCH"])
def environment_source(source_id):
    authenticate(g.db); entity = g.db.get(EnvironmentSource, source_id)
    if entity is None: raise ApiError("ENVIRONMENT_SOURCE_NOT_FOUND", "Environment source not found", 404)
    if request.method == "GET": return jsonify(serialize(entity))
    data = body(EnvironmentSourceUpdateRequest)
    provider, source = data.provider or entity.provider, data.source or entity.source
    conflict = g.db.scalar(select(EnvironmentSource).where(EnvironmentSource.provider == provider, EnvironmentSource.source == source, EnvironmentSource.id != entity.id))
    if conflict: raise ApiError("DUPLICATE_ENVIRONMENT_SOURCE", "An environment source with this provider and source already exists", 409)
    if data.provider is not None: entity.provider = data.provider
    if data.source is not None: entity.source = data.source
    if data.url is not None: entity.url = data.url
    if data.metadata is not None: entity.metadata_json = data.metadata
    audit("ENVIRONMENT_SOURCE_UPDATED", "EnvironmentSource", entity.id); commit(); return jsonify(serialize(entity))


@api_blueprint.route("/environment/observations", methods=["GET", "POST"])
def environment_observations():
    authenticate(g.db)
    if request.method == "GET":
        query = select(EnvironmentObservation).order_by(EnvironmentObservation.retrieved_at.desc())
        if value := request.args.get("observation_type"): query = query.where(EnvironmentObservation.observation_type == value)
        if value := request.args.get("status"): query = query.where(EnvironmentObservation.status == value)
        if value := request.args.get("source_id"):
            try: query = query.where(EnvironmentObservation.source_id == uuid.UUID(value))
            except ValueError: raise ApiError("VALIDATION_ERROR", "source_id must be a UUID", 422) from None
        if value := request.args.get("valid_from"): query = query.where(EnvironmentObservation.retrieved_at >= value)
        if value := request.args.get("valid_to"): query = query.where(EnvironmentObservation.retrieved_at <= value)
        result = paginated(query)
        return jsonify({**result, "items": [observation_payload(item) for item in result["items"]]})
    data = body(EnvironmentObservationCreateRequest)
    if g.db.get(EnvironmentSource, data.source_id) is None: raise ApiError("ENVIRONMENT_SOURCE_NOT_FOUND", "Environment source not found", 404)
    location = WKTElement(f"POINT({data.location.longitude} {data.location.latitude})", srid=4326) if data.location else None
    entity = EnvironmentObservation(**data.model_dump(exclude={"location"}), location=location)
    g.db.add(entity); commit(); audit("ENVIRONMENT_OBSERVATION_CREATED", "EnvironmentObservation", entity.id); commit()
    return jsonify(observation_payload(entity)), 201


@api_blueprint.get("/environment/observations/<uuid:observation_id>")
def environment_observation(observation_id):
    authenticate(g.db); entity = g.db.get(EnvironmentObservation, observation_id)
    if entity is None: raise ApiError("ENVIRONMENT_OBSERVATION_NOT_FOUND", "Environment observation not found", 404)
    return jsonify(observation_payload(entity))


@api_blueprint.route("/predictions", methods=["GET", "POST"])
def predictions():
    user = authenticate(g.db)
    if request.method == "GET":
        query = select(Prediction).join(Mission, Prediction.mission_id == Mission.id).order_by(Prediction.created_at.desc())
        if "admin" not in {role.name for role in user.roles}:
            query = query.where(Mission.created_by_id == user.id)
        result = paginated(query)
        return jsonify({**result, "items": [serialize(item) for item in result["items"]]})
    data = body(PredictionCreateRequest)
    mission = g.db.get(Mission, data.mission_id)
    if mission is None: raise ApiError("MISSION_NOT_FOUND", "Mission not found", 404)
    require_mission_access(mission, user)
    if g.db.get(ModelVersion, data.model_version_id) is None: raise ApiError("MODEL_NOT_FOUND", "Model version not found", 404)
    entity = Prediction(**data.model_dump())
    g.db.add(entity); commit(); audit("PREDICTION_RECORDED", "Prediction", entity.id); commit()
    return jsonify(serialize(entity)), 201


@api_blueprint.get("/predictions/<uuid:prediction_id>")
def prediction(prediction_id):
    user = authenticate(g.db); entity = g.db.get(Prediction, prediction_id)
    if entity is None: raise ApiError("PREDICTION_NOT_FOUND", "Prediction not found", 404)
    mission = g.db.get(Mission, entity.mission_id)
    if mission is None: raise ApiError("PREDICTION_NOT_FOUND", "Prediction not found", 404)
    require_mission_access(mission, user)
    return jsonify(serialize(entity))


@api_blueprint.get("/routes")
def routes():
    user = authenticate(g.db)
    query = select(Route).join(RouteCandidate).join(Mission).order_by(Route.created_at.desc())
    if "admin" not in {role.name for role in user.roles}:
        query = query.where(Mission.created_by_id == user.id)
    return page(query, Route)


@api_blueprint.post("/routes/<uuid:route_id>/review")
def review_route(route_id):
    user = authenticate(g.db); route = g.db.get(Route, route_id)
    if route is None: raise ApiError("NOT_FOUND", "Route not found", 404)
    candidate = g.db.get(RouteCandidate, route.route_candidate_id); mission = g.db.get(Mission, candidate.mission_id) if candidate else None
    if mission is None: raise ApiError("NOT_FOUND", "Route mission not found", 404)
    roles = {role.name for role in user.roles}
    if not roles.intersection({"operator", "admin"}) or (mission.created_by_id == user.id and "admin" not in roles):
        raise ApiError("FORBIDDEN", "An independent operator or admin reviewer is required", 403)
    data = body(ReviewRequest); review = RouteReview(route_id=route_id, reviewer_id=user.id, **data.model_dump()); route.status = "UNDER_REVIEW"; g.db.add(review); audit("ROUTE_REVIEWED", "Route", route_id); commit()
    return jsonify({"id": str(review.id), "route_id": str(route_id), "decision": review.decision}), 201


@api_blueprint.post("/routes/<uuid:route_id>/approval")
@require_roles("operator", "admin")
def approve_route(route_id):
    route = g.db.get(Route, route_id)
    if route is None: raise ApiError("NOT_FOUND", "Route not found", 404)
    data = body(ApprovalRequest); user = g.current_user
    candidate = g.db.get(RouteCandidate, route.route_candidate_id); mission = g.db.get(Mission, candidate.mission_id) if candidate else None
    if mission is None: raise ApiError("NOT_FOUND", "Route mission not found", 404)
    if mission.created_by_id == user.id and "admin" not in {role.name for role in user.roles}:
        raise ApiError("FORBIDDEN", "Mission owner cannot approve their own route", 403)
    review = g.db.scalar(select(RouteReview).where(RouteReview.route_id == route_id).order_by(RouteReview.created_at.desc()))
    if route.status != "UNDER_REVIEW" or review is None or review.decision not in {"RECOMMENDED", "APPROVED"}:
        raise ApiError("ROUTE_NOT_UNDER_REVIEW", "An affirmative human review is required before approval", 409)
    if review.reviewer_id == user.id:
        raise ApiError("REVIEWER_APPROVER_SEPARATION_REQUIRED", "The route reviewer cannot approve the same route", 409)
    approval = RouteApproval(route_id=route_id, approver_id=user.id, **data.model_dump()); route.status = data.decision
    candidate = g.db.get(RouteCandidate, route.route_candidate_id); mission = g.db.get(Mission, candidate.mission_id) if candidate else None
    if mission: mission.state = data.decision
    g.db.add(approval); audit(f"ROUTE_{data.decision}", "Route", route_id); commit()
    return jsonify({"id": str(approval.id), "route_id": str(route_id), "decision": approval.decision}), 201


@api_blueprint.get("/alerts")
def alerts():
    user = authenticate(g.db)
    query = select(Alert).join(Mission, Alert.mission_id == Mission.id).order_by(Alert.created_at.desc())
    if "admin" not in {role.name for role in user.roles}:
        query = query.where(Mission.created_by_id == user.id)
    return page(query, Alert)


@api_blueprint.route("/simulation", methods=["GET", "POST"])
def simulation():
    authenticate(g.db)
    if request.method == "GET": return page(select(SimulationRun).order_by(SimulationRun.created_at.desc()), SimulationRun)
    data = body(SimulationRequest); run = SimulationRun(**data.model_dump(), status="PENDING", is_simulation=True); g.db.add(run); audit("SIMULATION_REQUESTED", "SimulationRun", run.id); commit()
    return jsonify(serialize(run)), 202


@api_blueprint.get("/provenance")
def provenance():
    user = authenticate(g.db)
    if "admin" not in {role.name for role in user.roles}:
        raise ApiError("FORBIDDEN", "Admin role is required", 403)
    return page(select(ProvenanceRecord).order_by(ProvenanceRecord.created_at.desc()), ProvenanceRecord)


@api_blueprint.route("/models", methods=["GET", "POST"])
def models():
    authenticate(g.db)
    if request.method == "GET":
        result = paginated(select(ModelVersion).order_by(ModelVersion.created_at.desc()))
        return jsonify({**result, "items": [serialize(item) for item in result["items"]]})
    data = body(ModelVersionCreateRequest)
    if g.db.scalar(select(ModelVersion).where(ModelVersion.name == data.name, ModelVersion.version == data.version)):
        raise ApiError("DUPLICATE_MODEL_VERSION", "A model with this name and version already exists", 409)
    entity = ModelVersion(name=data.name, version=data.version, status=data.status, metadata_json=data.metadata)
    g.db.add(entity); commit(); audit("MODEL_VERSION_CREATED", "ModelVersion", entity.id); commit()
    return jsonify(serialize(entity)), 201


@api_blueprint.route("/models/<uuid:model_id>", methods=["GET", "PATCH"])
def model(model_id):
    authenticate(g.db); entity = g.db.get(ModelVersion, model_id)
    if entity is None: raise ApiError("MODEL_NOT_FOUND", "Model version not found", 404)
    if request.method == "GET": return jsonify(serialize(entity))
    data = body(ModelVersionUpdateRequest)
    if data.status is not None: entity.status = data.status
    if data.metadata is not None: entity.metadata_json = data.metadata
    audit("MODEL_VERSION_UPDATED", "ModelVersion", entity.id); commit(); return jsonify(serialize(entity))


@api_blueprint.route("/models/<uuid:model_id>/artifacts", methods=["GET", "POST"])
def model_artifacts(model_id):
    authenticate(g.db)
    if g.db.get(ModelVersion, model_id) is None: raise ApiError("MODEL_NOT_FOUND", "Model version not found", 404)
    if request.method == "GET":
        result = paginated(select(ModelArtifact).where(ModelArtifact.model_version_id == model_id).order_by(ModelArtifact.created_at.desc()))
        return jsonify({**result, "items": [{"id": str(item.id), "model_version_id": str(item.model_version_id), "path": item.path, "sha256": item.sha256, "artifact_type": item.artifact_type} for item in result["items"]]})
    data = body(ModelArtifactCreateRequest)
    entity = ModelArtifact(model_version_id=model_id, **data.model_dump())
    g.db.add(entity); commit(); audit("MODEL_ARTIFACT_RECORDED", "ModelArtifact", entity.id); commit()
    return jsonify({"id": str(entity.id), "model_version_id": str(entity.model_version_id), "path": entity.path, "sha256": entity.sha256, "artifact_type": entity.artifact_type}), 201


@api_blueprint.get("/models/<uuid:model_id>/artifacts/<uuid:artifact_id>")
def model_artifact(model_id, artifact_id):
    authenticate(g.db)
    if g.db.get(ModelVersion, model_id) is None: raise ApiError("MODEL_NOT_FOUND", "Model version not found", 404)
    entity = g.db.get(ModelArtifact, artifact_id)
    if entity is None or entity.model_version_id != model_id: raise ApiError("MODEL_ARTIFACT_NOT_FOUND", "Model artifact not found", 404)
    return jsonify({"id": str(entity.id), "model_version_id": str(entity.model_version_id), "path": entity.path, "sha256": entity.sha256, "artifact_type": entity.artifact_type})


@api_blueprint.get("/audit")
@require_roles("admin")
def audit_events(): return page(select(AuditEvent).order_by(AuditEvent.occurred_at.desc()), AuditEvent)
