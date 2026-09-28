"""ML prediction endpoints for authentic Phase 5 models.

STRICT CONTRACT:
- Communicates with ML Adapter passing the exact 6 features for iceberg drift:
    latitude, longitude, length_m, width_m, estimated_draft_m, coriolis_f
- Converts legacy fields (e.g., speed, heading) and derives physical features.
- Communicates with ML Adapter passing spatial grids for sea ice.
- Safely handles missing data returning MODEL_INCOMPATIBLE or MODEL_UNAVAILABLE.
- Never fabricates data or predictions.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request
from pydantic import ValidationError

from app.api.v1.schemas import IcebergMLInferenceRequest, SeaIceMLInferenceRequest
from app.auth import ApiError
from ml.adapter import predict_iceberg_drift, predict_sea_ice_concentration

ml_blueprint = Blueprint("ml", __name__)


@ml_blueprint.post("/iceberg/predict")
def predict_iceberg():
    """Predict 24-hour iceberg drift using exact 6 physical features via ML Adapter."""
    json_data = request.get_json(silent=True) or {}
    try:
        data = IcebergMLInferenceRequest.model_validate(json_data)
    except ValidationError as exc:
        raise ApiError("VALIDATION_ERROR", f"Request validation failed: {exc}", 422) from exc

    features = data.to_adapter_features()
    result = predict_iceberg_drift(features)

    status_code = 200
    if result.get("status") == "MODEL_UNAVAILABLE":
        status_code = 503
    elif result.get("status") == "MODEL_INCOMPATIBLE":
        status_code = 422

    return jsonify(result), status_code


@ml_blueprint.post("/sea-ice/predict")
def predict_sea_ice():
    """Predict sea-ice concentration for a spatial grid via ML Adapter."""
    json_data = request.get_json(silent=True) or {}
    try:
        data = SeaIceMLInferenceRequest.model_validate(json_data)
    except ValidationError as exc:
        raise ApiError("VALIDATION_ERROR", f"Request validation failed: {exc}", 422) from exc

    grid = data.to_spatial_grid()
    result = predict_sea_ice_concentration(grid)

    status_code = 200
    if result.get("status") == "MODEL_UNAVAILABLE":
        status_code = 503
    elif result.get("status") == "MODEL_INCOMPATIBLE":
        status_code = 422

    return jsonify(result), status_code
