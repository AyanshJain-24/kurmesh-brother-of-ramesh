from datetime import UTC, datetime
import uuid

from app.environment.ingestion import EnvironmentalObservationIngestionService
from app.environment.providers import NormalizedEnvironmentalObservation, ObservationProvenance, ObservationStatus


NOW = datetime(2026, 9, 14, tzinfo=UTC)


def unavailable() -> NormalizedEnvironmentalObservation:
    return NormalizedEnvironmentalObservation("weather", ObservationStatus.UNAVAILABLE, None, NOW, ObservationProvenance("test", None, "test://unavailable"))


def test_unavailable_outcome_does_not_touch_repository_or_persist_fake_observation(monkeypatch):
    class Repository:
        def __init__(self, session):
            pass

        def __getattr__(self, name):
            raise AssertionError(f"Unavailable data must not invoke repository method {name}")

    monkeypatch.setattr("app.environment.ingestion.EnvironmentRepository", Repository)
    result = EnvironmentalObservationIngestionService(object()).persist(unavailable())
    assert result.persisted is False
    assert result.observation_id is None


def test_persisted_observation_retains_normalized_provenance(monkeypatch):
    captured = {}

    class Repository:
        def __init__(self, session):
            pass

        def source_by_provider_and_product(self, provider, product):
            assert (provider, product) == ("test", "product-v1")
            return None

        def add_source(self, source):
            source.id = uuid.uuid4()
            return source

        def add_observation(self, observation):
            observation.id = uuid.uuid4()
            captured["observation"] = observation
            return observation

        def add_provenance(self, record):
            captured["provenance"] = record
            return record

    monkeypatch.setattr("app.environment.ingestion.EnvironmentRepository", Repository)
    normalized = NormalizedEnvironmentalObservation(
        "sea_ice_concentration", ObservationStatus.LIVE, NOW, NOW,
        ObservationProvenance("test", "product-v1", "test://object/1", checksum="sha256:test", details={"dataset": "test-only"}),
        value={"concentration": 0.5}, units="fraction",
    )
    result = EnvironmentalObservationIngestionService(object()).persist(normalized)
    assert result.persisted is True
    assert captured["observation"].value == {"concentration": 0.5}
    assert captured["provenance"].source_reference == "test://object/1"
    assert captured["provenance"].source_timestamp == NOW
    assert captured["provenance"].details == {"provider": "test", "product": "product-v1", "dataset": "test-only"}


def test_existing_environment_api_routes_are_unchanged():
    from app import create_app
    from app.config import Settings

    app = create_app(Settings("sqlite+pysqlite:///:memory:", "redis://unused", "INFO", ["http://localhost"], "x" * 32))
    paths = {rule.rule for rule in app.url_map.iter_rules()}
    assert "/api/v1/environment/sources" in paths
    assert "/api/v1/environment/observations" in paths
