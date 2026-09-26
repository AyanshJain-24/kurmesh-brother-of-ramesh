"""Demo-only endpoint for explicit Phase 5F iceberg Ridge features."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request
from pydantic import ValidationError

from app.api.v1.schemas import IcebergDemoInferenceRequest
from app.auth import ApiError
from app.ml_demo.iceberg import IcebergDemoModelService, ModelUnavailable


ml_demo_blueprint = Blueprint("ml_demo", __name__)


@ml_demo_blueprint.post("/iceberg/predict")
def predict_iceberg_displacement():
    """Predict a 24-hour projected displacement from supplied frozen-contract features."""
    try:
        data = IcebergDemoInferenceRequest.model_validate(request.get_json(silent=True) or {})
    except ValidationError as exc:
        raise ApiError("VALIDATION_ERROR", "Request validation failed", 422) from exc
    service: IcebergDemoModelService = current_app.extensions["kurmesh_demo_iceberg_model"]
    try:
        prediction = service.predict(data.model_dump())
    except ModelUnavailable as exc:
        raise ApiError("MODEL_UNAVAILABLE", "The demo iceberg model is unavailable", 503) from exc
    except ValueError as exc:
        raise ApiError("VALIDATION_ERROR", "Contract-valid finite features are required", 422) from exc
    assert service.model is not None
    return jsonify({
        "status": "OFFLINE_DEMO_ONLY",
        "model_type": "ridge_closed_form_standardized",
        "artifact_sha256": service.model.artifact_sha256,
        "forecast_horizon": "24 hours",
        "target_crs": "EPSG:3412",
        "prediction": prediction,
        "notice": "Demo-only decision support. This response cannot approve or execute a route.",
    })
