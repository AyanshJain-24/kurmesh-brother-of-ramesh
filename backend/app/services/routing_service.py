"""Service orchestrating polar maritime routing with Polar A* and authentic ML.

Integrates routing.polar_astar with database persistence models, ensuring:
- Authentic ML integration into A* cost calculation.
- Safe DRAFT / UNKNOWN fallback when ML models are missing.
- Safe dictionary mapping to SQLAlchemy RouteCandidate model without type errors.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from geoalchemy2.elements import WKTElement
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Mission, RouteCandidate, Vessel
from routing.polar_astar import PolarAStarRouter, default_router


def _point(session: Session, geometry: Any) -> tuple[float, float] | None:
    if geometry is None:
        return None
    lon, lat = session.execute(select(func.ST_X(geometry), func.ST_Y(geometry))).one()
    if lon is None or lat is None:
        return None
    return float(lon), float(lat)


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
        val = specifications.get(key)
        if isinstance(val, bool):
            continue
        if isinstance(val, (int, float)) and float(val) > 0.0:
            return float(val)
    return None


def line_wkt(coordinates: tuple[tuple[float, float], ...]) -> WKTElement:
    points_str = ", ".join(f"{lon:.10f} {lat:.10f}" for lon, lat in coordinates)
    return WKTElement(f"LINESTRING({points_str})", srid=4326)


def next_candidate_versions(existing_maximum: int | None, count: int = 3) -> tuple[int, ...]:
    maximum = existing_maximum or 0
    return tuple(range(maximum + 1, maximum + count + 1))


class RoutingService:
    """Orchestrates candidate route generation using Polar A*."""

    def __init__(self, router: PolarAStarRouter | None = None):
        self.router = router or default_router

    def generate_candidates(self, session: Session, mission: Mission) -> tuple[list[RouteCandidate], list[str]]:
        """Generate and persist 3 deterministic candidates for a mission."""
        origin, destination = mission_endpoints(session, mission)
        vessel_specs = mission.vessel.specifications if mission.vessel else {}

        paths = self.router.generate_candidate_paths(origin, destination, vessel_specs)

        current_version = session.scalar(
            select(func.max(RouteCandidate.version)).where(RouteCandidate.mission_id == mission.id)
        )
        versions = next_candidate_versions(current_version, len(paths))

        created: list[RouteCandidate] = []
        warnings: list[str] = []

        for version, path in zip(versions, paths):
            coords = path["coordinates"]
            status = path.get("status", "DRAFT")
            risk_data_status = path.get("risk_data_status", "UNKNOWN")

            if risk_data_status == "UNKNOWN":
                warnings.append(
                    f"Route {path['route_type']} (v{version}): ML models unavailable at runtime; route flagged as DRAFT with risk_data_status UNKNOWN."
                )

            metadata = dict(path.get("metadata", {}))

            candidate = RouteCandidate(
                id=uuid.uuid4(),
                mission_id=mission.id,
                version=version,
                geometry=line_wkt(coords),
                prediction_id=None,
                status=status,
                risk_data_status=risk_data_status,
                distance_nm=path.get("distance_nm"),
                estimated_duration_hours=path.get("estimated_duration_hours"),
                risk_score=path.get("risk_score"),
                risk_components=path.get("risk_components", {}),
                environmental_snapshot=path.get("environmental_snapshot", {}),
                algorithm_version=path.get("algorithm_version", "polar-astar-v1"),
                metadata_json=metadata,
            )
            session.add(candidate)
            created.append(candidate)

        return created, sorted(set(warnings))


default_routing_service = RoutingService()


def generate_candidates(session: Session, mission: Mission) -> tuple[list[RouteCandidate], list[str]]:
    """Functional entrypoint for candidate generation."""
    return default_routing_service.generate_candidates(session, mission)
