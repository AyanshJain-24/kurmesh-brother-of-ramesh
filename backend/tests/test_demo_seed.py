import os
import uuid
from contextlib import nullcontext

import pytest

from app.demo_seed import DEMO_EMAIL, DEMO_FULL_NAME, DEMO_PASSWORD, DemoSeedConfiguration, enabled, seed_demo_data
from app.models import AuditEvent, Mission, Role, RouteCandidate, User, Vessel


class InMemorySeedSession:
    """Small transaction stand-in that exercises the seed's reuse branches."""
    def __init__(self):
        self.records = {Role: [], User: [], Vessel: [], Mission: [], AuditEvent: [], RouteCandidate: []}

    def begin(self):
        return nullcontext(self)

    def add(self, value):
        if value.id is None:
            value.id = uuid.uuid4()
        self.records[type(value)].append(value)

    def flush(self):
        return None

    def scalar(self, statement):
        entity = statement.column_descriptions[0].get("entity")
        if entity is RouteCandidate:
            return None
        values = self.records[entity]
        return values[0] if values else None


def test_demo_seed_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("KURMESH_DEMO_SEED", raising=False)
    assert enabled() is False


def test_demo_seed_configuration_requires_deployment_credentials(monkeypatch):
    for name in (DEMO_EMAIL, DEMO_PASSWORD, DEMO_FULL_NAME):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ValueError, match="KURMESH_DEMO_EMAIL"):
        DemoSeedConfiguration.from_environment()


def test_demo_seed_configuration_uses_environment_only(monkeypatch):
    monkeypatch.setenv(DEMO_EMAIL, "judge@example.test")
    monkeypatch.setenv(DEMO_PASSWORD, "not-a-committed-secret")
    monkeypatch.setenv(DEMO_FULL_NAME, "Demo Judge")
    configuration = DemoSeedConfiguration.from_environment()
    assert configuration.email == "judge@example.test"
    assert configuration.full_name == "Demo Judge"
    assert configuration.password == os.environ[DEMO_PASSWORD]


def test_demo_seed_twice_reuses_one_user_vessel_and_mission():
    session = InMemorySeedSession()
    configuration = DemoSeedConfiguration("judge@example.test", "not-a-committed-secret", "Demo Judge")
    first = seed_demo_data(session, configuration)
    second = seed_demo_data(session, configuration)
    assert first.user_id == second.user_id
    assert first.vessel_id == second.vessel_id
    assert first.mission_id == second.mission_id
    assert len(session.records[User]) == len(session.records[Vessel]) == len(session.records[Mission]) == 1
    assert session.records[Mission][0].state == "ANALYZING"
