from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.api.v1.schemas import (AlertCreateRequest, GeoJSONLineString, GovernedApprovalRequest,
    GovernedReviewRequest, ProvenanceCreateRequest, RouteCandidateCreateRequest, RouteCreateRequest)


LINE = {"type": "LineString", "coordinates": [[72.1, 18.9], [73.0, 19.4]]}


def test_route_candidate_contract_accepts_safe_geojson_and_rejects_invalid_positions():
    request = RouteCandidateCreateRequest(version=1, geometry=LINE, algorithm_version="submitted-manual-1")
    assert request.geometry.type == "LineString"
    with pytest.raises(ValidationError):
        GeoJSONLineString(type="LineString", coordinates=[[181, 0], [72, 18]])
    with pytest.raises(ValidationError):
        GeoJSONLineString(type="Point", coordinates=[[72, 18], [73, 19]])


def test_governance_contracts_are_explicit_and_cannot_auto_approve():
    assert RouteCreateRequest(route_candidate_id="11111111-1111-1111-1111-111111111111").route_candidate_id
    assert GovernedReviewRequest(decision="APPROVED").decision == "APPROVED"
    assert GovernedApprovalRequest(decision="REJECTED").decision == "REJECTED"
    with pytest.raises(ValidationError):
        GovernedReviewRequest(decision="AUTO_APPROVED")
    with pytest.raises(ValidationError):
        GovernedApprovalRequest(decision="AUTO_APPROVED")


def test_alert_and_provenance_contracts_require_explicit_traceability_fields():
    alert = AlertCreateRequest(mission_id="11111111-1111-1111-1111-111111111111", severity="HIGH", category="NAVIGATION", title="Manual warning", message="Operator-supplied alert")
    assert alert.severity == "HIGH"
    provenance = ProvenanceCreateRequest(entity_type="RouteCandidate", entity_id="11111111-1111-1111-1111-111111111111", source_type="operator_submission", source_reference="submission-42", retrieved_at=datetime.now(UTC))
    assert provenance.source_reference == "submission-42"
    with pytest.raises(ValidationError):
        AlertCreateRequest(mission_id="11111111-1111-1111-1111-111111111111", severity="URGENT", category="NAVIGATION", title="x", message="x")
