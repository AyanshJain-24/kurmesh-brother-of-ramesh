"""Provider contracts and normalized data types; this module has no Flask or database dependency."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from app.config import ProviderConfiguration


class ObservationStatus(StrEnum):
    LIVE = "LIVE"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"
    ERROR = "ERROR"
    DEGRADED = "DEGRADED"


class EnvironmentalDomain(StrEnum):
    SEA_ICE = "sea_ice"
    WEATHER = "weather"
    OCEAN_CONDITIONS = "ocean_conditions"


class ProviderUnavailableError(Exception):
    """An adapter could not obtain data, without supplying a fabricated observation."""


@dataclass(frozen=True)
class GeographicPoint:
    longitude: float
    latitude: float

    def __post_init__(self) -> None:
        if not -180 <= self.longitude <= 180 or not -90 <= self.latitude <= 90:
            raise ValueError("Location must be a valid WGS84 longitude/latitude point")


@dataclass(frozen=True)
class ProviderFetchRequest:
    domain: EnvironmentalDomain
    location: GeographicPoint | None = None
    observed_after: datetime | None = None


@dataclass(frozen=True)
class ObservationProvenance:
    provider: str
    product: str | None
    source_reference: str
    checksum: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.provider.strip() or not self.source_reference.strip():
            raise ValueError("Provenance requires a provider and source reference")


@dataclass(frozen=True)
class NormalizedEnvironmentalObservation:
    """A provider-neutral observation, not a database model or API request."""

    observation_type: str
    status: ObservationStatus
    observed_at: datetime | None
    retrieved_at: datetime
    provenance: ObservationProvenance
    value: dict[str, Any] | None = None
    units: str | None = None
    location: GeographicPoint | None = None
    quality: str | None = None
    resolution: str | None = None
    valid_to: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.observation_type.strip() or self.retrieved_at.tzinfo is None:
            raise ValueError("Observation type and timezone-aware retrieval timestamp are required")
        if self.observed_at is not None and self.observed_at.tzinfo is None:
            raise ValueError("Observation timestamp must be timezone-aware")
        if self.status in {ObservationStatus.LIVE, ObservationStatus.STALE, ObservationStatus.DEGRADED}:
            if self.value is None or not self.units:
                raise ValueError("Data-bearing observations require real values and units")
        elif self.value is not None or self.units is not None:
            raise ValueError("Unavailable and error outcomes must not contain observation values")

    @property
    def is_persistable(self) -> bool:
        return self.status in {ObservationStatus.LIVE, ObservationStatus.STALE, ObservationStatus.DEGRADED}


@runtime_checkable
class EnvironmentalProviderAdapter(Protocol):
    """A future provider adapter parses only its own external format into normalized observations."""

    name: str
    supported_domains: frozenset[EnvironmentalDomain]

    def fetch(self, request: ProviderFetchRequest, configuration: ProviderConfiguration) -> tuple[NormalizedEnvironmentalObservation, ...]: ...


class ProviderRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, EnvironmentalProviderAdapter] = {}

    def register(self, adapter: EnvironmentalProviderAdapter) -> None:
        if not isinstance(adapter, EnvironmentalProviderAdapter):
            raise TypeError("Provider adapter does not satisfy the environmental provider contract")
        if adapter.name in self._adapters:
            raise ValueError(f"Provider adapter {adapter.name!r} is already registered")
        self._adapters[adapter.name] = adapter

    def get(self, name: str) -> EnvironmentalProviderAdapter | None:
        return self._adapters.get(name)


@dataclass(frozen=True)
class ProviderCollectionResult:
    observations: tuple[NormalizedEnvironmentalObservation, ...]
    status: ObservationStatus


class ProviderCollectionService:
    """Converts disabled, unavailable, and exceptional adapter execution into explicit non-data outcomes."""

    def __init__(self, registry: ProviderRegistry) -> None:
        self.registry = registry

    def collect(self, provider_name: str, request: ProviderFetchRequest, configuration: ProviderConfiguration | None) -> ProviderCollectionResult:
        adapter = self.registry.get(provider_name)
        if configuration is None or not configuration.enabled:
            return self._outcome(provider_name, request, ObservationStatus.UNAVAILABLE, "PROVIDER_DISABLED")
        if adapter is None:
            return self._outcome(provider_name, request, ObservationStatus.UNAVAILABLE, "ADAPTER_NOT_REGISTERED")
        if request.domain not in adapter.supported_domains:
            return self._outcome(provider_name, request, ObservationStatus.UNAVAILABLE, "DOMAIN_NOT_SUPPORTED")
        try:
            observations = adapter.fetch(request, configuration)
        except ProviderUnavailableError as exc:
            return self._outcome(provider_name, request, ObservationStatus.UNAVAILABLE, str(exc) or "PROVIDER_UNAVAILABLE")
        except Exception as exc:
            # Do not expose exception text: provider errors may include credentials or endpoints.
            return self._outcome(provider_name, request, ObservationStatus.ERROR, "PROVIDER_EXCEPTION", exception_type=type(exc).__name__)
        if not observations:
            return self._outcome(provider_name, request, ObservationStatus.UNAVAILABLE, "NO_OBSERVATION_RETURNED")
        status = ObservationStatus.DEGRADED if any(item.status is ObservationStatus.DEGRADED for item in observations) else max((item.status for item in observations), key=lambda item: {ObservationStatus.LIVE: 0, ObservationStatus.STALE: 1, ObservationStatus.DEGRADED: 2, ObservationStatus.UNAVAILABLE: 3, ObservationStatus.ERROR: 4}[item])
        return ProviderCollectionResult(observations=observations, status=status)

    @staticmethod
    def _outcome(provider: str, request: ProviderFetchRequest, status: ObservationStatus, code: str, **details: str) -> ProviderCollectionResult:
        observation = NormalizedEnvironmentalObservation(
            observation_type=request.domain.value,
            status=status,
            observed_at=None,
            retrieved_at=datetime.now(UTC),
            provenance=ObservationProvenance(provider=provider, product=None, source_reference=f"provider:{provider}", details={"failure_code": code, **details}),
            metadata={"failure_code": code, **details},
        )
        return ProviderCollectionResult((observation,), status)
