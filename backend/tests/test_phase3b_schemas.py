from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.api.v1.schemas import (EnvironmentObservationCreateRequest, ModelArtifactCreateRequest,
                                PredictionCreateRequest)


def test_observation_accepts_only_declared_availability_states():
    payload = {"source_id": "11111111-1111-1111-1111-111111111111", "observation_type": "sea_state", "status": "UNAVAILABLE", "value": {}, "units": "m", "retrieved_at": datetime.now(UTC)}
    assert EnvironmentObservationCreateRequest(**payload).status == "UNAVAILABLE"
    payload["status"] = "INFERRED"
    with pytest.raises(ValidationError):
        EnvironmentObservationCreateRequest(**payload)


def test_observation_location_and_artifact_checksum_are_validated():
    payload = {"source_id": "11111111-1111-1111-1111-111111111111", "observation_type": "sea_state", "status": "LIVE", "value": {}, "units": "m", "retrieved_at": datetime.now(UTC), "location": {"longitude": 181, "latitude": 0}}
    with pytest.raises(ValidationError):
        EnvironmentObservationCreateRequest(**payload)
    with pytest.raises(ValidationError):
        ModelArtifactCreateRequest(path="metadata-only", sha256="not-a-checksum", artifact_type="model")


def test_prediction_contract_requires_explicit_references_and_non_inference_status():
    request = PredictionCreateRequest(mission_id="11111111-1111-1111-1111-111111111111", model_version_id="22222222-2222-2222-2222-222222222222", status="PENDING")
    assert request.output is None
    with pytest.raises(ValidationError):
        PredictionCreateRequest(mission_id="11111111-1111-1111-1111-111111111111", model_version_id="22222222-2222-2222-2222-222222222222", status="COMPLETED")
