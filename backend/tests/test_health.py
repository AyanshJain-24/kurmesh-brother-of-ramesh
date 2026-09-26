from app import create_app
from app.config import Settings
from app.dependencies import Check


AUTH_SECRET = "test-auth-secret-that-is-long-enough"


def test_live_is_dependency_free():
    client = create_app(Settings("sqlite+pysqlite:///:memory:", "", "INFO", ["http://localhost"], AUTH_SECRET)).test_client()
    response = client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json["status"] == "LIVE"


def test_ready_reports_dependency_status(monkeypatch):
    monkeypatch.setattr("app.api.v1.health.database_check", lambda _: Check("LIVE", "PostGIS test"))
    monkeypatch.setattr("app.api.v1.health.redis_check", lambda _: Check("LIVE"))
    client = create_app(Settings("sqlite+pysqlite:///:memory:", "redis://unused", "INFO", ["http://localhost"], AUTH_SECRET)).test_client()
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    assert response.json["services"]["database"]["status"] == "LIVE"


def test_ready_is_unavailable_when_a_dependency_fails(monkeypatch):
    monkeypatch.setattr("app.api.v1.health.database_check", lambda _: Check("ERROR", "Database unavailable"))
    monkeypatch.setattr("app.api.v1.health.redis_check", lambda _: Check("LIVE"))
    client = create_app(Settings("sqlite+pysqlite:///:memory:", "redis://unused", "INFO", ["http://localhost"], AUTH_SECRET)).test_client()
    assert client.get("/api/v1/health/ready").status_code == 503
