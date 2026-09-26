"""Focused tests for the demo-only Phase 5F iceberg inference endpoint."""

import json
from pathlib import Path

import pytest

from app import create_app
from app.config import Settings
from app.ml_demo.iceberg import FEATURE_NAMES, TARGET_NAMES, IcebergRidgeModel


SECRET = "test-auth-secret-that-is-long-enough"


def artifact(path: Path, *, coefficient: float = 1.0) -> None:
    """Write a test-only envelope with the immutable Phase 5F schema, not a trained model."""
    payload = {
        "artifact_schema_version": 1,
        "package_type": "kurmesh_phase5_portable_model_package",
        "model": {
            "model_type": "ridge_closed_form_standardized",
            "alpha": 10.0,
            "feature_names": list(FEATURE_NAMES),
            "target_names": list(TARGET_NAMES),
            "feature_mean": [0.0] * len(FEATURE_NAMES),
            "feature_scale_train_only": [1.0] * len(FEATURE_NAMES),
            "target_mean_train_only": [0.0, 0.0],
            "coefficients": [[coefficient, coefficient * 2.0] for _ in FEATURE_NAMES],
        },
        "provenance": {"operational_status": "OFFLINE_EXPERIMENT_ONLY"},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def settings(artifact_path: str | None) -> Settings:
    return Settings(
        "sqlite+pysqlite:///:memory:", "redis://unused", "INFO", ["http://localhost"],
        SECRET, demo_iceberg_model_artifact_path=artifact_path,
    )


def features() -> dict[str, float]:
    return dict(zip(FEATURE_NAMES, (1.0, 2.0, 3.0, 4.0, 0.5, 0.25, -0.25)))


def test_startup_loader_enforces_the_frozen_artifact_contract(tmp_path):
    path = tmp_path / "test-only-iceberg-artifact.json"
    artifact(path)
    model = IcebergRidgeModel.load(str(path))
    assert model.predict(features()) == {"dx_m": pytest.approx(10.5), "dy_m": pytest.approx(21.0)}


def test_endpoint_predicts_only_from_explicit_frozen_features(tmp_path):
    path = tmp_path / "test-only-iceberg-artifact.json"
    artifact(path)
    app = create_app(settings(str(path)))
    response = app.test_client().post("/api/v1/demo/ml/iceberg/predict", json=features())
    assert response.status_code == 200
    assert response.json["status"] == "OFFLINE_DEMO_ONLY"
    assert response.json["forecast_horizon"] == "24 hours"
    assert response.json["target_crs"] == "EPSG:3412"
    assert response.json["prediction"] == {"dx_m": pytest.approx(10.5), "dy_m": pytest.approx(21.0)}
    assert len(response.json["artifact_sha256"]) == 64


def test_model_is_loaded_at_startup_not_refit_or_reloaded_per_request(tmp_path):
    path = tmp_path / "test-only-iceberg-artifact.json"
    artifact(path, coefficient=1.0)
    app = create_app(settings(str(path)))
    artifact(path, coefficient=99.0)
    response = app.test_client().post("/api/v1/demo/ml/iceberg/predict", json=features())
    assert response.status_code == 200
    assert response.json["prediction"] == {"dx_m": pytest.approx(10.5), "dy_m": pytest.approx(21.0)}


def test_unconfigured_or_invalid_artifact_is_explicitly_model_unavailable(tmp_path):
    missing = create_app(settings(None)).test_client().post("/api/v1/demo/ml/iceberg/predict", json=features())
    assert missing.status_code == 503
    assert missing.json["error"]["code"] == "MODEL_UNAVAILABLE"
    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text("{}", encoding="utf-8")
    invalid = create_app(settings(str(invalid_path))).test_client().post("/api/v1/demo/ml/iceberg/predict", json=features())
    assert invalid.status_code == 503
    assert invalid.json["error"]["code"] == "MODEL_UNAVAILABLE"


def test_request_rejects_missing_extra_and_nonfinite_contract_features(tmp_path):
    path = tmp_path / "test-only-iceberg-artifact.json"
    artifact(path)
    client = create_app(settings(str(path))).test_client()
    missing = features(); missing.pop("current_x_m")
    assert client.post("/api/v1/demo/ml/iceberg/predict", json=missing).status_code == 422
    extra = features(); extra["future_dx_m"] = 1.0
    assert client.post("/api/v1/demo/ml/iceberg/predict", json=extra).status_code == 422
    nonfinite = features(); nonfinite["current_x_m"] = float("inf")
    assert client.post("/api/v1/demo/ml/iceberg/predict", json=nonfinite).status_code == 422
