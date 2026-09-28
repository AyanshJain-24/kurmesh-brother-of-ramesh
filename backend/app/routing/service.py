"""Persistence-facing orchestration for deterministic prototype candidates."""
from __future__ import annotations

from datetime import UTC, datetime
from math import asin, cos, radians, sin, sqrt
from typing import Any
import uuid

from geoalchemy2.elements import WKTElement
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import EnvironmentObservation, EnvironmentSource, Mission, RouteCandidate, Vessel
from app.routing.cost import EnvironmentalInput, calculate_risk
from app.routing.generator import ALGORITHM_VERSION, CandidatePath, build_candidate_paths, distance_nm

RELEVANCE_CORRIDOR_KM = 250.0
OBSERVATION_DOMAINS = {
    "sea_ice_concentration": "sea_ice",
    # NOAA GFS persists the data-bearing wind record; its aggregate
    # ``weather`` UNAVAILABLE outcome is intentionally not scored.
    "wind": "weather",
    "weather": "weather",
    "ocean_current": "ocean",
}


def _point(session: Session, geometry: Any) -> tuple[float, float] | None:
    if geometry is None:
        return None
    longitude, latitude = session.execute(select(func.ST_X(geometry), func.ST_Y(geometry))).one()
    if longitude is None or latitude is None:
        return None
    return float(longitude), float(latitude)


def mission_endpoints(session: Session, mission: Mission) -> tuple[tuple[float, float], tuple[float, float]]:
    origin, destination = _point(session, mission.origin), _point(session, mission.destination)
    if origin is None or destination is None:
        raise ValueError("Mission origin and destination are required before route generation")
    return origin, destination


def vessel_speed_knots(vessel: Vessel | None) -> float | None:
    if vessel is None:
        return None
    specifications = vessel.specifications or {}
    for key in ("cruising_speed_knots", "service_speed_knots", "speed_knots"):
        value = specifications.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)) and float(value) > 0.0:
            return float(value)
    return None


def _haversine_km(first: tuple[float, float], second: tuple[float, float]) -> float:
    longitude_a, latitude_a = first
    longitude_b, latitude_b = second
    delta_latitude = radians(latitude_b - latitude_a)
    delta_longitude = radians(((longitude_b - longitude_a + 180.0) % 360.0) - 180.0)
    a = sin(delta_latitude / 2) ** 2 + cos(radians(latitude_a)) * cos(radians(latitude_b)) * sin(delta_longitude / 2) ** 2
    return 6_371.0088 * 2 * asin(min(1.0, sqrt(a)))


def _time_relevant(observation: EnvironmentObservation, reference: datetime) -> bool:
    def utc(value: datetime) -> datetime:
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    return (observation.valid_from is None or utc(observation.valid_from) <= reference) and (observation.valid_to is None or utc(observation.valid_to) >= reference)


def _observations_for_path(session: Session, path: CandidatePath, reference: datetime) -> tuple[dict[str, EnvironmentalInput], list[str], dict[str, Any]]:
    rows = session.execute(
        select(EnvironmentObservation, EnvironmentSource)
        .join(EnvironmentSource, EnvironmentObservation.source_id == EnvironmentSource.id)
        .where(EnvironmentObservation.observation_type.in_(tuple(OBSERVATION_DOMAINS)))
        .order_by(EnvironmentObservation.retrieved_at.desc(), EnvironmentObservation.id)
    ).all()
    selected: dict[str, tuple[EnvironmentalInput, dict[str, Any], tuple[float, str]]] = {}
    warnings: list[str] = []
    for observation, source in rows:
        domain = OBSERVATION_DOMAINS[observation.observation_type]
        if not _time_relevant(observation, reference):
            continue
        location = _point(session, observation.location)
        if location is None:
            warnings.append(f"{domain}: observation {observation.id} has no usable location and was not used")
            continue
        distance_km = min(_haversine_km(location, point) for point in path.coordinates)
        if distance_km > RELEVANCE_CORRIDOR_KM:
            continue
        candidate = EnvironmentalInput(
            domain=domain, observation_id=str(observation.id), source_id=str(source.id), status=observation.status,
            value=observation.value or {}, units=observation.units, retrieved_at=observation.retrieved_at.isoformat(),
            valid_from=observation.valid_from.isoformat() if observation.valid_from else None,
            valid_to=observation.valid_to.isoformat() if observation.valid_to else None,
            distance_to_route_km=distance_km,
        )
        ordering = (distance_km, observation.retrieved_at.isoformat())
        if domain not in selected or ordering < selected[domain][2]:
            selected[domain] = (candidate, {
                "observation_id": str(observation.id), "source_id": str(source.id), "provider": source.provider,
                "source": source.source, "status": observation.status, "observation_type": observation.observation_type,
                "value": observation.value, "units": observation.units, "quality": observation.quality,
                "resolution": observation.resolution, "retrieved_at": observation.retrieved_at.isoformat(),
                "valid_from": observation.valid_from.isoformat() if observation.valid_from else None,
                "valid_to": observation.valid_to.isoformat() if observation.valid_to else None,
                "distance_to_route_km": distance_km,
            }, ordering)
    return ({domain: item[0] for domain, item in selected.items()}, warnings,
            {domain: item[1] for domain, item in selected.items()})


def line_wkt(coordinates: tuple[tuple[float, float], ...]) -> WKTElement:
    return WKTElement("LINESTRING(" + ", ".join(f"{longitude:.10f} {latitude:.10f}" for longitude, latitude in coordinates) + ")", srid=4326)


def next_candidate_versions(existing_maximum: int | None, count: int = 3) -> tuple[int, ...]:
    """Return the next unique, ascending candidate versions for one mission."""
    maximum = existing_maximum or 0
    return tuple(range(maximum + 1, maximum + count + 1))


def generate_candidates(session: Session, mission: Mission) -> tuple[list[RouteCandidate], list[str]]:
    """Persist deterministic polar candidates for a valid mission."""
    from app.services.routing_service import default_routing_service
    return default_routing_service.generate_candidates(session, mission)

