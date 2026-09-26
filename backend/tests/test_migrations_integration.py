import os
import subprocess
import sys
from datetime import UTC, datetime

import pytest
from geoalchemy2 import WKTElement
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.models import (Alert, AuditEvent, EnvironmentObservation, EnvironmentSource, Mission,
                        ModelArtifact, ModelVersion, Prediction, ProvenanceRecord, Role, Route,
                        RouteApproval, RouteCandidate, RouteReview, SimulationRun, User, Vessel)


@pytest.mark.integration
def test_migration_from_clean_postgis_database():
    """Run only against a disposable PostGIS database; never substitutes SQLite for spatial persistence."""
    url = os.environ.get("KURMESH_INTEGRATION_DATABASE_URL")
    if not url:
        pytest.skip("KURMESH_INTEGRATION_DATABASE_URL is required for clean PostGIS migration test")
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=False, capture_output=True, text=True, env={**os.environ, "DATABASE_URL": url})
    assert result.returncode == 0, result.stderr
    with engine.connect() as connection:
        assert connection.execute(text("SELECT PostGIS_Version()")) .scalar_one()
        assert connection.execute(text("SELECT to_regclass('public.missions')")) .scalar_one() == "missions"
        assert connection.execute(text("SELECT to_regclass('public.route_candidates')")) .scalar_one() == "route_candidates"


@pytest.mark.integration
def test_postgis_spatial_persistence_and_relationships():
    url = os.environ.get("KURMESH_INTEGRATION_DATABASE_URL")
    if not url:
        pytest.skip("KURMESH_INTEGRATION_DATABASE_URL is required for PostGIS persistence test")
    engine = create_engine(url)
    session = Session(engine)
    try:
        role = Role(name="database-test-role")
        user = User(email="database-test@example.test", password_hash="test-only", roles=[role])
        vessel = Vessel(name="database-test-vessel", vessel_type="test")
        mission = Mission(name="database-test-mission", created_by=user, vessel=vessel, origin=WKTElement("POINT(0 0)", srid=4326), destination=WKTElement("POINT(1 1)", srid=4326))
        source = EnvironmentSource(provider="test-only", source="migration-test")
        observation = EnvironmentObservation(source=source, observation_type="test-only", status="UNAVAILABLE", value={"test": True}, units="none", retrieved_at=datetime.now(UTC), location=WKTElement("POINT(0 0)", srid=4326))
        version = ModelVersion(name="test-only", version="0", status="MODEL_UNAVAILABLE")
        artifact = ModelArtifact(model_version=version, path="test-only", sha256="0" * 64, artifact_type="test-only")
        candidate = RouteCandidate(mission=mission, version=1, geometry=WKTElement("LINESTRING(0 0, 1 1)", srid=4326), risk_components={}, environmental_snapshot={}, algorithm_version="test-only")
        route = Route(route_candidate=candidate, status="UNDER_REVIEW")
        session.add_all([role, user, vessel, mission, source, observation, version, artifact, candidate, route])
        session.flush()
        records = [Prediction(mission_id=mission.id, model_version_id=version.id, status="MODEL_UNAVAILABLE", input_provenance={}, reason="test-only"), RouteReview(route_id=route.id, reviewer_id=user.id, decision="REVIEWED"), RouteApproval(route_id=route.id, approver_id=user.id, decision="REJECTED", reason="test-only"), Alert(mission_id=mission.id, severity="INFO", status="OPEN", message="test-only"), SimulationRun(mission_id=mission.id, status="COMPLETED", scenario={}, is_simulation=True), AuditEvent(actor_id=user.id, event_type="DATABASE_TEST", entity_type="Mission", entity_id=mission.id, payload={}), ProvenanceRecord(entity_type="Mission", entity_id=mission.id, source_type="test", source_reference="test-only", details={})]
        session.add_all(records)
        session.commit()
        assert session.execute(text("SELECT ST_AsText(origin) FROM missions WHERE id = :id"), {"id": mission.id}).scalar_one() == "POINT(0 0)"
        assert session.get(Mission, mission.id).vessel_id == vessel.id
    finally:
        session.rollback()
        session.close()


@pytest.mark.integration
def test_migration_downgrade_removes_only_kurmesh_schema_objects():
    url = os.environ.get("KURMESH_INTEGRATION_DATABASE_URL")
    if not url:
        pytest.skip("KURMESH_INTEGRATION_DATABASE_URL is required for migration downgrade test")
    result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=False, capture_output=True, text=True, env={**os.environ, "DATABASE_URL": url})
    assert result.returncode == 0, result.stderr
    result = subprocess.run([sys.executable, "-m", "alembic", "downgrade", "base"], check=False, capture_output=True, text=True, env={**os.environ, "DATABASE_URL": url})
    assert result.returncode == 0, result.stderr
    engine = create_engine(url)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT to_regclass('public.missions')")).scalar_one() is None
        assert connection.execute(text("SELECT PostGIS_Version()")).scalar_one()
