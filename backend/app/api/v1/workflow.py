"""Governed routing persistence endpoints; this module never calculates or approves routes automatically."""
import json
import uuid

from flask import Blueprint, g, jsonify, request
from geoalchemy2.elements import WKTElement
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.v1.schemas import (AlertAcknowledgeRequest, AlertCreateRequest, GovernedApprovalRequest,
    GovernedReviewRequest, ProvenanceCreateRequest, RouteCandidateCreateRequest, RouteCandidateUpdateRequest,
    RouteCreateRequest, RouteUpdateRequest)
from app.auth import ApiError, authenticate
from app.models import Alert, AuditEvent, Mission, Prediction, ProvenanceRecord, Route, RouteApproval, RouteCandidate, RouteReview
from app.api.v1.application import TRANSITIONS
from app.routing.generator import ALGORITHM_VERSION
from app.routing.service import generate_candidates

workflow_blueprint = Blueprint("workflow", __name__)


def _body(schema):
    try:
        return schema.model_validate(request.get_json(silent=True) or {})
    except ValidationError as exc:
        raise ApiError("VALIDATION_ERROR", "Request validation failed", 422) from exc


def _roles(user): return {role.name for role in user.roles}
def _admin(user): return "admin" in _roles(user)
def _owner(mission, user): return mission.created_by_id == user.id or _admin(user)


def _mission(mission_id):
    mission = g.db.get(Mission, mission_id)
    if mission is None: raise ApiError("MISSION_NOT_FOUND", "Mission not found", 404)
    return mission


def _candidate(candidate_id):
    candidate = g.db.get(RouteCandidate, candidate_id)
    if candidate is None: raise ApiError("ROUTE_CANDIDATE_NOT_FOUND", "Route candidate not found", 404)
    return candidate


def _route(route_id):
    route = g.db.get(Route, route_id)
    if route is None: raise ApiError("ROUTE_NOT_FOUND", "Route not found", 404)
    return route


def _commit():
    try: g.db.commit()
    except IntegrityError:
        g.db.rollback(); raise ApiError("CONFLICT", "The requested change conflicts with existing data", 409) from None


def _audit(action, entity, entity_id, payload=None):
    user = getattr(g, "current_user", None)
    g.db.add(AuditEvent(actor_id=user.id if user else None, event_type=action, entity_type=entity, entity_id=entity_id, payload=payload or {}))


def _line(value):
    return WKTElement("LINESTRING(" + ", ".join(f"{lon} {lat}" for lon, lat in value.coordinates) + ")", srid=4326)


def _geometry(value):
    if value is None: return None
    raw = g.db.scalar(select(func.ST_AsGeoJSON(value)))
    return json.loads(raw) if raw else None


def _candidate_payload(value):
    return {"id": str(value.id), "mission_id": str(value.mission_id), "prediction_id": str(value.prediction_id) if value.prediction_id else None,
        "version": value.version, "status": value.status, "geometry": _geometry(value.geometry), "distance_nm": value.distance_nm,
        "estimated_duration_hours": value.estimated_duration_hours, "risk_score": value.risk_score, "risk_components": value.risk_components,
        "environmental_snapshot": value.environmental_snapshot, "algorithm_version": value.algorithm_version, "metadata": value.metadata_json}


def _route_payload(value):
    return {"id": str(value.id), "route_candidate_id": str(value.route_candidate_id), "status": value.status,
        "geometry": _geometry(value.geometry), "metadata": value.metadata_json}


def _paginate(query, serializer):
    try: limit, offset = min(max(int(request.args.get("limit", 50)), 1), 100), max(int(request.args.get("offset", 0)), 0)
    except ValueError: raise ApiError("VALIDATION_ERROR", "limit and offset must be integers", 422) from None
    return jsonify({"items": [serializer(x) for x in g.db.scalars(query.limit(limit).offset(offset))], "limit": limit, "offset": offset})


@workflow_blueprint.post("/missions/<uuid:mission_id>/route-candidates/generate")
def generate_route_candidates(mission_id):
    """Generate deterministic candidates; selection and approval remain human actions."""
    user = authenticate(g.db)
    mission = g.db.scalar(select(Mission).where(Mission.id == mission_id).with_for_update())
    if mission is None:
        raise ApiError("MISSION_NOT_FOUND", "Mission not found", 404)
    if not _owner(mission, user):
        raise ApiError("FORBIDDEN", "Mission ownership is required", 403)
    request_body = request.get_json(silent=True)
    if request_body not in (None, {}):
        raise ApiError("VALIDATION_ERROR", "Route candidate generation does not accept request fields", 422)
    if mission.state not in {"ANALYZING", "ROUTES_AVAILABLE"}:
        raise ApiError("INVALID_MISSION_STATE", "Route candidates can be generated only while ANALYZING or after routes are available", 409)
    try:
        candidates, warnings = generate_candidates(g.db, mission)
    except ValueError as exc:
        raise ApiError("INVALID_MISSION_GEOMETRY", str(exc), 422) from exc
    # Reuse the established mission transition table. Re-generation is allowed
    # only after a prior successful transition and never bypasses review.
    if mission.state == "ANALYZING":
        if "ROUTES_AVAILABLE" not in TRANSITIONS[mission.state]:
            raise ApiError("INVALID_STATE_TRANSITION", "Mission cannot transition to ROUTES_AVAILABLE", 409)
        mission.state = "ROUTES_AVAILABLE"
        _audit("MISSION_TRANSITIONED", "Mission", mission.id, {"state": "ROUTES_AVAILABLE", "reason": "route_candidates_generated"})
    for candidate in candidates:
        _audit("ROUTE_CANDIDATE_GENERATED", "RouteCandidate", candidate.id, {"algorithm_version": ALGORITHM_VERSION, "route_type": candidate.metadata_json["route_type"]})
    _commit()
    return jsonify({
        "mission_id": str(mission.id), "candidate_count": len(candidates),
        "candidates": [_candidate_payload(candidate) for candidate in candidates],
        "algorithm_version": ALGORITHM_VERSION,
        "environment_status": [candidate.risk_components.get("availability", "UNAVAILABLE") for candidate in candidates],
        "warnings": warnings,
    }), 201


@workflow_blueprint.route("/missions/<uuid:mission_id>/route-candidates", methods=["GET", "POST"])
def candidates(mission_id):
    user = authenticate(g.db); mission = _mission(mission_id)
    if not _owner(mission, user): raise ApiError("FORBIDDEN", "Mission ownership is required", 403)
    if request.method == "GET": return _paginate(select(RouteCandidate).where(RouteCandidate.mission_id == mission_id).order_by(RouteCandidate.version), _candidate_payload)
    data = _body(RouteCandidateCreateRequest)
    if data.prediction_id and (prediction := g.db.get(Prediction, data.prediction_id)) is None: raise ApiError("PREDICTION_NOT_FOUND", "Prediction not found", 404)
    if data.prediction_id and prediction.mission_id != mission_id: raise ApiError("CONFLICT", "Prediction belongs to another mission", 409)
    entity = RouteCandidate(mission_id=mission_id, geometry=_line(data.geometry), metadata_json=data.metadata,
        **data.model_dump(exclude={"geometry", "metadata"}))
    g.db.add(entity); _audit("ROUTE_CANDIDATE_CREATED", "RouteCandidate", entity.id); _commit()
    return jsonify(_candidate_payload(entity)), 201


@workflow_blueprint.route("/route-candidates/<uuid:candidate_id>", methods=["GET", "PATCH", "DELETE"])
def candidate(candidate_id):
    user = authenticate(g.db); entity = _candidate(candidate_id); mission = _mission(entity.mission_id)
    if not _owner(mission, user): raise ApiError("FORBIDDEN", "Mission ownership is required", 403)
    if request.method == "GET": return jsonify(_candidate_payload(entity))
    if request.method == "DELETE":
        if g.db.scalar(select(Route).where(Route.route_candidate_id == entity.id)): raise ApiError("CONFLICT", "A selected candidate cannot be deleted", 409)
        g.db.delete(entity); _audit("ROUTE_CANDIDATE_DELETED", "RouteCandidate", candidate_id); _commit(); return "", 204
    data = _body(RouteCandidateUpdateRequest)
    if entity.status not in {"DRAFT", "READY"}: raise ApiError("INVALID_ROUTE_CANDIDATE_STATE", "Candidate cannot be updated in its current state", 409)
    for field in ("status", "distance_nm", "estimated_duration_hours", "risk_score"):
        value = getattr(data, field)
        if value is not None: setattr(entity, field, value)
    for field, column in (("risk_components", "risk_components"), ("environmental_snapshot", "environmental_snapshot"), ("metadata", "metadata_json")):
        value = getattr(data, field)
        if value is not None: setattr(entity, column, value)
    _audit("ROUTE_CANDIDATE_UPDATED", "RouteCandidate", entity.id); _commit(); return jsonify(_candidate_payload(entity))


@workflow_blueprint.route("/missions/<uuid:mission_id>/routes", methods=["GET", "POST"])
def mission_routes(mission_id):
    user = authenticate(g.db); mission = _mission(mission_id)
    if not _owner(mission, user): raise ApiError("FORBIDDEN", "Mission ownership is required", 403)
    query = select(Route).join(RouteCandidate).where(RouteCandidate.mission_id == mission_id).order_by(Route.created_at.desc())
    if request.method == "GET": return _paginate(query, _route_payload)
    data = _body(RouteCreateRequest); candidate = _candidate(data.route_candidate_id)
    if candidate.mission_id != mission_id: raise ApiError("CONFLICT", "Candidate belongs to another mission", 409)
    if candidate.status != "READY": raise ApiError("INVALID_ROUTE_CANDIDATE_STATE", "Only READY candidates may be selected", 409)
    entity = Route(route_candidate_id=candidate.id, status="DRAFT", geometry=candidate.geometry, metadata_json=data.metadata)
    g.db.add(entity); _audit("ROUTE_CREATED", "Route", entity.id); _commit(); return jsonify(_route_payload(entity)), 201


@workflow_blueprint.route("/routes/<uuid:route_id>", methods=["GET", "PATCH"])
def route_detail(route_id):
    user = authenticate(g.db); entity = _route(route_id); mission = _mission(_candidate(entity.route_candidate_id).mission_id)
    if not _owner(mission, user): raise ApiError("FORBIDDEN", "Mission ownership is required", 403)
    if request.method == "GET": return jsonify(_route_payload(entity))
    data = _body(RouteUpdateRequest)
    if data.status == "APPROVED": raise ApiError("HUMAN_APPROVAL_REQUIRED", "Use the approval endpoint", 409)
    if entity.status not in {"DRAFT", "ACTIVE"}: raise ApiError("INVALID_ROUTE_STATE", "Route cannot be updated in its current state", 409)
    if data.status: entity.status = data.status
    if data.metadata is not None: entity.metadata_json = data.metadata
    _audit("ROUTE_UPDATED", "Route", entity.id); _commit(); return jsonify(_route_payload(entity))


@workflow_blueprint.post("/routes/<uuid:route_id>/reviews")
def create_review(route_id):
    user = authenticate(g.db); entity = _route(route_id); mission = _mission(_candidate(entity.route_candidate_id).mission_id)
    if "operator" not in _roles(user) and not _admin(user): raise ApiError("FORBIDDEN", "Reviewer role is required", 403)
    if mission.created_by_id == user.id and not _admin(user): raise ApiError("FORBIDDEN", "Mission owners cannot review their own routes", 403)
    if entity.status not in {"DRAFT", "UNDER_REVIEW"}: raise ApiError("INVALID_ROUTE_STATE", "Route cannot be reviewed in its current state", 409)
    data = _body(GovernedReviewRequest); entity.status = "UNDER_REVIEW"
    review = RouteReview(route_id=route_id, reviewer_id=user.id, decision=data.decision, reason=data.comments, metadata_json=data.metadata)
    g.db.add(review); _audit("ROUTE_REVIEW_CREATED", "RouteReview", review.id, {"route_id": str(route_id), "decision": data.decision}); _commit()
    return jsonify({"id": str(review.id), "route_id": str(route_id), "decision": review.decision, "comments": review.reason}), 201


@workflow_blueprint.post("/routes/<uuid:route_id>/approvals")
def create_approval(route_id):
    user = authenticate(g.db); entity = _route(route_id); mission = _mission(_candidate(entity.route_candidate_id).mission_id)
    if "operator" not in _roles(user) and not _admin(user): raise ApiError("FORBIDDEN", "Approver role is required", 403)
    if mission.created_by_id == user.id and not _admin(user): raise ApiError("FORBIDDEN", "Mission owners cannot approve their own routes", 403)
    if entity.status != "UNDER_REVIEW": raise ApiError("ROUTE_NOT_UNDER_REVIEW", "A route must be under review before approval", 409)
    review = g.db.scalar(select(RouteReview).where(RouteReview.route_id == route_id).order_by(RouteReview.created_at.desc()))
    if review is None or review.decision != "APPROVED": raise ApiError("APPROVED_REVIEW_REQUIRED", "An approved human review is required", 409)
    if review.reviewer_id == user.id: raise ApiError("REVIEWER_APPROVER_SEPARATION_REQUIRED", "Reviewer and approver must differ", 409)
    data = _body(GovernedApprovalRequest); approval = RouteApproval(route_id=route_id, approver_id=user.id, decision=data.decision, reason=data.comments, metadata_json=data.metadata)
    entity.status = data.decision
    g.db.add(approval); _audit("ROUTE_APPROVAL_CREATED", "RouteApproval", approval.id, {"route_id": str(route_id), "decision": data.decision}); _commit()
    return jsonify({"id": str(approval.id), "route_id": str(route_id), "decision": approval.decision}), 201


@workflow_blueprint.route("/missions/<uuid:mission_id>/alerts", methods=["GET", "POST"])
def mission_alerts(mission_id):
    user = authenticate(g.db); mission = _mission(mission_id)
    if not _owner(mission, user): raise ApiError("FORBIDDEN", "Mission ownership is required", 403)
    if request.method == "GET":
        return _paginate(select(Alert).where(Alert.mission_id == mission_id).order_by(Alert.created_at.desc()), lambda x: {"id": str(x.id), "mission_id": str(x.mission_id), "severity": x.severity, "category": x.category, "title": x.title, "message": x.message, "status": x.status, "acknowledged_at": x.acknowledged_at.isoformat() if x.acknowledged_at else None})
    data = _body(AlertCreateRequest)
    if data.mission_id != mission_id: raise ApiError("CONFLICT", "Alert mission does not match URL", 409)
    entity = Alert(mission_id=mission_id, severity=data.severity, category=data.category, title=data.title, message=data.message, status="OPEN")
    g.db.add(entity); _audit("ALERT_CREATED", "Alert", entity.id); _commit(); return jsonify({"id": str(entity.id), "status": entity.status}), 201


@workflow_blueprint.post("/alerts/<uuid:alert_id>/acknowledgement")
def acknowledge_alert(alert_id):
    user = authenticate(g.db); entity = g.db.get(Alert, alert_id)
    if entity is None: raise ApiError("ALERT_NOT_FOUND", "Alert not found", 404)
    if entity.mission_id is None or not _owner(_mission(entity.mission_id), user): raise ApiError("FORBIDDEN", "Mission ownership is required", 403)
    data = _body(AlertAcknowledgeRequest); entity.status = data.status; entity.acknowledged_by_id = user.id; entity.acknowledged_at = func.now()
    _audit("ALERT_ACKNOWLEDGED", "Alert", entity.id, {"status": data.status}); _commit(); return jsonify({"id": str(entity.id), "status": entity.status})


@workflow_blueprint.route("/provenance", methods=["GET", "POST"])
def provenance_records():
    user = authenticate(g.db)
    if request.method == "GET":
        if not _admin(user): raise ApiError("FORBIDDEN", "Admin role is required", 403)
        return _paginate(select(ProvenanceRecord).order_by(ProvenanceRecord.created_at.desc()), lambda x: {"id": str(x.id), "entity_type": x.entity_type, "entity_id": str(x.entity_id), "source_type": x.source_type, "source_reference": x.source_reference, "retrieved_at": x.retrieved_at.isoformat() if x.retrieved_at else None, "source_timestamp": x.source_timestamp.isoformat() if x.source_timestamp else None, "checksum": x.checksum, "details": x.details})
    if not _admin(user) and "operator" not in _roles(user): raise ApiError("FORBIDDEN", "Operator role is required", 403)
    data = _body(ProvenanceCreateRequest); entity = ProvenanceRecord(**data.model_dump())
    g.db.add(entity); _audit("PROVENANCE_CREATED", "ProvenanceRecord", entity.id, {"entity_type": data.entity_type, "entity_id": str(data.entity_id)}); _commit()
    return jsonify({"id": str(entity.id), "entity_type": entity.entity_type, "entity_id": str(entity.entity_id)}), 201
