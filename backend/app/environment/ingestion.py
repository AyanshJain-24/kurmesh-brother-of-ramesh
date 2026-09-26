"""Persistence bridge for normalized provider observations; adapters never import this module."""

from dataclasses import dataclass

from geoalchemy2.elements import WKTElement
from sqlalchemy.orm import Session

from app.environment.providers import NormalizedEnvironmentalObservation
from app.models import EnvironmentObservation, EnvironmentSource, ProvenanceRecord
from app.repositories import EnvironmentRepository


@dataclass(frozen=True)
class IngestionResult:
    observation_id: str | None
    persisted: bool
    reason: str | None = None


class EnvironmentalObservationIngestionService:
    """Persists only sourced data-bearing outcomes inside a caller-owned transaction."""

    def __init__(self, session: Session) -> None:
        self.repository = EnvironmentRepository(session)

    def persist(self, normalized: NormalizedEnvironmentalObservation) -> IngestionResult:
        if not normalized.is_persistable:
            return IngestionResult(None, False, f"{normalized.status.value} outcomes contain no observation data")

        product = normalized.provenance.product or normalized.observation_type
        source = self.repository.source_by_provider_and_product(normalized.provenance.provider, product)
        if source is None:
            source = self.repository.add_source(EnvironmentSource(
                provider=normalized.provenance.provider,
                source=product,
                metadata_json={"provider_metadata": normalized.metadata},
            ))
        location = None
        if normalized.location is not None:
            location = WKTElement(f"POINT({normalized.location.longitude} {normalized.location.latitude})", srid=4326)
        observation = self.repository.add_observation(EnvironmentObservation(
            source_id=source.id,
            observation_type=normalized.observation_type,
            status=normalized.status.value,
            value=normalized.value,
            units=normalized.units,
            quality=normalized.quality,
            resolution=normalized.resolution,
            retrieved_at=normalized.retrieved_at,
            valid_from=normalized.observed_at,
            valid_to=normalized.valid_to,
            location=location,
        ))
        self.repository.add_provenance(ProvenanceRecord(
            entity_type="EnvironmentObservation",
            entity_id=observation.id,
            source_type="environment_provider",
            source_reference=normalized.provenance.source_reference,
            retrieved_at=normalized.retrieved_at,
            source_timestamp=normalized.observed_at,
            checksum=normalized.provenance.checksum,
            details={"provider": normalized.provenance.provider, "product": normalized.provenance.product, **normalized.provenance.details},
        ))
        return IngestionResult(str(observation.id), True)
