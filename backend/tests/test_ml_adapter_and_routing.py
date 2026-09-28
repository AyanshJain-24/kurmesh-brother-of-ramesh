import math
import pytest
from app import create_app
from app.config import Settings
from ml.adapter import MLAdapter, compute_coriolis_f
from routing.polar_astar import PolarAStarRouter


def test_coriolis_calculation():
    # At equator (lat 0), f = 0
    f_eq = compute_coriolis_f(0.0)
    assert f_eq == 0.0

    # At 90 deg N (lat 90), f = 2 * Omega * sin(pi/2) = 2 * 7.2921159e-5 = 1.45842e-4
    f_north = compute_coriolis_f(90.0)
    assert f_north == pytest.approx(1.45842e-4, rel=1e-3)

    # At 60 deg S (lat -60), f = 2 * Omega * sin(-pi/3) < 0
    f_south = compute_coriolis_f(-60.0)
    expected_south = 2.0 * 7.2921159e-5 * math.sin(math.radians(-60.0))
    assert f_south == pytest.approx(expected_south, rel=1e-3)


def test_ml_adapter_iceberg_validation_and_safe_fallback():
    adapter = MLAdapter()

    # Incomplete features
    res = adapter.predict_iceberg_drift({"latitude": -65.0})
    assert res["status"] == "MODEL_INCOMPATIBLE"
    assert "Missing required iceberg features" in res["reason"]

    # Valid 6 features (including coriolis_f)
    valid_features = {
        "latitude": -65.0,
        "longitude": 120.0,
        "length_m": 250.0,
        "width_m": 120.0,
        "estimated_draft_m": 180.0,
        "coriolis_f": compute_coriolis_f(-65.0),
    }
    res = adapter.predict_iceberg_drift(valid_features)
    assert res["status"] in ("LIVE", "MODEL_UNAVAILABLE")
    # Provenance must be intact
    assert "provenance" in res
    assert res["provenance"]["model"] == "iceberg_drift"


def test_ml_adapter_sea_ice_validation_and_safe_fallback():
    adapter = MLAdapter()

    # Invalid grid
    res = adapter.predict_sea_ice_concentration({"lat_min": -70.0, "lat_max": -75.0, "lon_min": 10.0, "lon_max": 20.0})
    assert res["status"] == "MODEL_INCOMPATIBLE"
    assert "Spatial grid must specify either 'bounds' or 'coordinates'" in res["reason"]

    # Valid grid
    valid_grid = {"bounds": [10.0, -75.0, 20.0, -65.0]}
    res = adapter.predict_sea_ice_concentration(valid_grid)
    assert res["status"] in ("LIVE", "MODEL_UNAVAILABLE")
    assert "provenance" in res
    assert res["provenance"]["model"] == "sea_ice_concentration"


def test_polar_astar_deterministic_and_safe_routing():
    router = PolarAStarRouter()
    origin = (10.0, -70.0)
    destination = (12.0, -71.0)

    candidate = router.find_path(origin, destination)

    # Verification: route must have coordinates, distance, and safe status
    assert candidate["status"] in ("READY", "DRAFT")
    assert candidate["risk_data_status"] in ("AVAILABLE", "UNKNOWN", "VERIFIED")
    assert candidate["distance_nm"] > 0.0
    assert len(candidate["coordinates"]) >= 2
    assert candidate["coordinates"][0] == origin
    assert candidate["coordinates"][-1] == destination
    assert candidate["algorithm_version"] == "polar-astar-v1"

    # Multi-path generator check
    candidates = router.generate_candidate_paths(origin, destination)
    assert len(candidates) == 3
    assert [c["route_type"] for c in candidates] == ["DIRECT", "NORTH_BIAS", "SOUTH_BIAS"]


def test_ml_api_endpoints_via_flask_client():
    settings = Settings("sqlite+pysqlite:///:memory:", "redis://unused", "INFO", ["http://localhost"], "test-auth-secret-that-is-long-enough")
    app = create_app(settings)
    app.config["TESTING"] = True
    client = app.test_client()

    # Iceberg predict
    payload = {
        "latitude": -68.5,
        "longitude": 75.0,
        "length_m": 300.0,
        "width_m": 150.0,
        "estimated_draft_m": 200.0,
        "heading": 180.0,  # Legacy field should be accepted and safely handled
        "speed": 1.5,      # Legacy field
    }
    response = client.post("/api/v1/ml/iceberg/predict", json=payload)
    assert response.status_code in (200, 503)
    data = response.get_json()
    assert "status" in data
    assert data["status"] in ("LIVE", "MODEL_UNAVAILABLE")
    assert "provenance" in data

    # Sea ice predict
    grid_payload = {
        "lat_min": -75.0,
        "lat_max": -65.0,
        "lon_min": 50.0,
        "lon_max": 80.0,
    }
    response2 = client.post("/api/v1/ml/sea-ice/predict", json=grid_payload)
    assert response2.status_code in (200, 503)
    data2 = response2.get_json()
    assert "status" in data2
    assert data2["status"] in ("LIVE", "MODEL_UNAVAILABLE")
    assert "provenance" in data2
