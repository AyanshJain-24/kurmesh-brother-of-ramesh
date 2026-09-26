import pytest

from app import create_app
from app.config import Settings


SECRET = "test-auth-secret-that-is-long-enough"


def settings() -> Settings:
    return Settings("sqlite+pysqlite:///:memory:", "redis://unused", "INFO", ["http://localhost"], SECRET)


def test_application_blueprint_is_registered():
    app = create_app(settings())
    paths = {rule.rule for rule in app.url_map.iter_rules()}
    assert "/api/v1/auth/login" in paths
    assert "/api/v1/missions" in paths
    assert "/api/v1/missions/<uuid:mission_id>/route-candidates/generate" in paths
    assert "/api/v1/health/live" in paths


def test_protected_route_returns_json_authentication_error():
    response = create_app(settings()).test_client().get("/api/v1/missions")
    assert response.status_code == 401
    assert response.json["error"]["code"] == "UNAUTHENTICATED"


def test_route_generation_endpoint_requires_authentication():
    response = create_app(settings()).test_client().post("/api/v1/missions/11111111-1111-1111-1111-111111111111/route-candidates/generate", json={})
    assert response.status_code == 401
    assert response.json["error"]["code"] == "UNAUTHENTICATED"


def test_invalid_api_path_returns_json_error():
    response = create_app(settings()).test_client().get("/api/v1/not-a-route")
    assert response.status_code == 404
    assert response.json["error"]["code"] == "NOT_FOUND"


def test_invalid_config_rejects_missing_auth_secret():
    with pytest.raises(ValueError, match="AUTH_SECRET"):
        create_app(Settings("sqlite+pysqlite:///:memory:", "", "INFO", ["http://localhost"]))


def test_session_is_closed_after_api_request(monkeypatch):
    app = create_app(settings())
    calls = []

    class Session:
        def close(self): calls.append("close")

    app.config["KURMESH_SESSION_FACTORY"] = lambda: Session()
    response = app.test_client().get("/api/v1/auth/login")
    assert response.status_code == 405
    assert calls == ["close"]
