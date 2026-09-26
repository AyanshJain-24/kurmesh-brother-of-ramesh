from datetime import UTC, datetime, timedelta

import pytest

from app.config import ProviderConfiguration, Settings
from app.environment.providers import (EnvironmentalDomain, EnvironmentalProviderAdapter, GeographicPoint,
    NormalizedEnvironmentalObservation, ObservationProvenance, ObservationStatus, ProviderCollectionService,
    ProviderFetchRequest, ProviderRegistry)


NOW = datetime(2026, 9, 14, 8, 0, tzinfo=UTC)
CONFIG = ProviderConfiguration("mock_provider", True, "https://provider.example/api", None, 15)


def data_observation(status: ObservationStatus = ObservationStatus.LIVE) -> NormalizedEnvironmentalObservation:
    return NormalizedEnvironmentalObservation(
        observation_type="sea_ice_concentration",
        status=status,
        observed_at=NOW - timedelta(minutes=5),
        retrieved_at=NOW,
        location=GeographicPoint(72.1, 18.9),
        value={"concentration": 0.42},
        units="fraction",
        provenance=ObservationProvenance("mock_provider", "test-product", "test://object/42", checksum="abc", details={"dataset_version": "test-only"}),
        metadata={"coverage": "complete"},
    )


class MockAdapter:
    name = "mock_provider"
    supported_domains = frozenset({EnvironmentalDomain.SEA_ICE, EnvironmentalDomain.WEATHER, EnvironmentalDomain.OCEAN_CONDITIONS})

    def __init__(self, result=(), error: Exception | None = None):
        self.result, self.error = result, error

    def fetch(self, request, configuration):
        if self.error:
            raise self.error
        return self.result


def service(adapter: MockAdapter | None = None) -> ProviderCollectionService:
    registry = ProviderRegistry()
    if adapter:
        registry.register(adapter)
    return ProviderCollectionService(registry)


def request() -> ProviderFetchRequest:
    return ProviderFetchRequest(EnvironmentalDomain.SEA_ICE, GeographicPoint(72.1, 18.9))


def test_adapter_contract_and_normalized_success_preserve_provenance():
    adapter = MockAdapter((data_observation(),))
    assert isinstance(adapter, EnvironmentalProviderAdapter)
    result = service(adapter).collect("mock_provider", request(), CONFIG)
    observation = result.observations[0]
    assert result.status == ObservationStatus.LIVE
    assert observation.provenance.provider == "mock_provider"
    assert observation.provenance.product == "test-product"
    assert observation.provenance.source_reference == "test://object/42"
    assert observation.observed_at == NOW - timedelta(minutes=5)
    assert observation.retrieved_at == NOW
    assert observation.location == GeographicPoint(72.1, 18.9)


def test_disabled_or_missing_adapter_is_explicitly_unavailable_without_values():
    result = service().collect("not_registered", request(), None)
    observation = result.observations[0]
    assert result.status == ObservationStatus.UNAVAILABLE
    assert observation.metadata["failure_code"] == "PROVIDER_DISABLED"
    assert observation.value is None and observation.is_persistable is False


def test_adapter_exception_is_an_explicit_safe_error_without_values():
    result = service(MockAdapter(error=RuntimeError("secret endpoint should not leak"))).collect("mock_provider", request(), CONFIG)
    observation = result.observations[0]
    assert result.status == ObservationStatus.ERROR
    assert observation.metadata == {"failure_code": "PROVIDER_EXCEPTION", "exception_type": "RuntimeError"}
    assert observation.value is None and observation.is_persistable is False


def test_stale_and_degraded_real_observations_remain_distinct_data_bearing_states():
    stale = service(MockAdapter((data_observation(ObservationStatus.STALE),))).collect("mock_provider", request(), CONFIG)
    degraded = service(MockAdapter((data_observation(ObservationStatus.DEGRADED),))).collect("mock_provider", request(), CONFIG)
    assert stale.status == ObservationStatus.STALE and stale.observations[0].is_persistable
    assert degraded.status == ObservationStatus.DEGRADED and degraded.observations[0].is_persistable


def test_normalized_contract_rejects_fake_data_on_failure_states():
    with pytest.raises(ValueError, match="Unavailable and error"):
        NormalizedEnvironmentalObservation("weather", ObservationStatus.UNAVAILABLE, None, NOW, ObservationProvenance("test", None, "test://none"), value={"made_up": True}, units="none")


def test_provider_configuration_validation_and_environment_parsing(monkeypatch):
    monkeypatch.setenv("KURMESH_ENVIRONMENT_PROVIDERS", "mock-provider")
    monkeypatch.setenv("KURMESH_ENVIRONMENT_PROVIDER_MOCK_PROVIDER_ENABLED", "true")
    monkeypatch.setenv("KURMESH_ENVIRONMENT_PROVIDER_MOCK_PROVIDER_ENDPOINT", "https://provider.example/api")
    monkeypatch.setenv("KURMESH_ENVIRONMENT_PROVIDER_MOCK_PROVIDER_MAX_FALLBACK_DISTANCE_KM", "12.5")
    settings = Settings.from_environment()
    assert settings.provider_configuration("mock-provider").enabled is True
    assert settings.provider_configuration("mock-provider").max_fallback_distance_km == 12.5
    assert ProviderConfiguration("mock", True, "https://provider.example", None, 15).max_fallback_distance_km == 75.0
    with pytest.raises(ValueError, match="requires an endpoint"):
        Settings("sqlite://", "redis://", "INFO", ["http://localhost"], "x" * 32, (ProviderConfiguration("bad", True, None, None, 15),)).validate()
    with pytest.raises(ValueError, match="fallback distance"):
        Settings("sqlite://", "redis://", "INFO", ["http://localhost"], "x" * 32, (ProviderConfiguration("bad", True, "https://provider.example", None, 15, max_fallback_distance_km=0),)).validate()
