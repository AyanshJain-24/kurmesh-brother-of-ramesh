"""WGS84 great-circle-style geometry generation for prototype candidates."""
from __future__ import annotations

from dataclasses import dataclass
from math import acos, asin, atan2, cos, degrees, radians, sin, sqrt

EARTH_RADIUS_M = 6_371_008.8
METRES_PER_NAUTICAL_MILE = 1_852.0
ALGORITHM_VERSION = "prototype-risk-routing-v1"


@dataclass(frozen=True)
class CandidatePath:
    """A generated route candidate. Coordinates are WGS84 [longitude, latitude]."""

    route_type: str
    coordinates: tuple[tuple[float, float], ...]


def _normalise_longitude(longitude: float) -> float:
    return ((longitude + 180.0) % 360.0) - 180.0


def _vector(point: tuple[float, float]) -> tuple[float, float, float]:
    longitude, latitude = map(radians, point)
    return cos(latitude) * cos(longitude), cos(latitude) * sin(longitude), sin(latitude)


def _point(vector: tuple[float, float, float]) -> tuple[float, float]:
    x, y, z = vector
    return _normalise_longitude(degrees(atan2(y, x))), degrees(atan2(z, sqrt(x * x + y * y)))


def great_circle(origin: tuple[float, float], destination: tuple[float, float], points: int = 13) -> tuple[tuple[float, float], ...]:
    """Interpolate a dateline-safe WGS84 great-circle line, including endpoints."""
    if points < 2:
        raise ValueError("points must be at least two")
    first, last = _vector(origin), _vector(destination)
    dot = max(-1.0, min(1.0, sum(a * b for a, b in zip(first, last))))
    angle = acos(dot)
    if angle < 1e-12:
        return tuple(origin for _ in range(points - 1)) + (destination,)
    # Antipodal routes have no unique great circle.  Keep a deterministic
    # dateline-safe interpolation instead of creating undefined geometry.
    if abs(sin(angle)) < 1e-12:
        longitude_delta = _normalise_longitude(destination[0] - origin[0])
        return tuple((_normalise_longitude(origin[0] + longitude_delta * index / (points - 1)),
                      origin[1] + (destination[1] - origin[1]) * index / (points - 1)) for index in range(points))
    result = []
    for index in range(points):
        fraction = index / (points - 1)
        left = sin((1.0 - fraction) * angle) / sin(angle)
        right = sin(fraction * angle) / sin(angle)
        result.append(_point(tuple(left * a + right * b for a, b in zip(first, last))))
    result[0], result[-1] = origin, destination
    return tuple(result)


def _biased_path(origin: tuple[float, float], destination: tuple[float, float], latitude_offset: float) -> tuple[tuple[float, float], ...]:
    midpoint = great_circle(origin, destination, 3)[1]
    # The bias is bounded so it remains a valid maritime WGS84 path.  It is
    # deliberately geometric only; it is not an environmental recommendation.
    waypoint = (midpoint[0], max(-89.0, min(89.0, midpoint[1] + latitude_offset)))
    first = great_circle(origin, waypoint, 7)
    second = great_circle(waypoint, destination, 7)
    return first[:-1] + second


def build_candidate_paths(origin: tuple[float, float], destination: tuple[float, float]) -> tuple[CandidatePath, ...]:
    """Create the three deterministic prototype paths between real endpoints."""
    _validate_point(origin, "origin")
    _validate_point(destination, "destination")
    if origin == destination:
        raise ValueError("origin and destination must be different")
    return (
        CandidatePath("DIRECT", great_circle(origin, destination)),
        CandidatePath("NORTH_BIAS", _biased_path(origin, destination, 3.0)),
        CandidatePath("SOUTH_BIAS", _biased_path(origin, destination, -3.0)),
    )


def _validate_point(point: tuple[float, float], label: str) -> None:
    longitude, latitude = point
    if not -180.0 <= longitude <= 180.0 or not -90.0 <= latitude <= 90.0:
        raise ValueError(f"{label} must be a valid WGS84 longitude/latitude point")


def distance_nm(coordinates: tuple[tuple[float, float], ...]) -> float:
    """Return summed WGS84 spherical segment distance in nautical miles."""
    total_metres = 0.0
    for (longitude_a, latitude_a), (longitude_b, latitude_b) in zip(coordinates, coordinates[1:]):
        phi_a, phi_b = radians(latitude_a), radians(latitude_b)
        delta_phi = radians(latitude_b - latitude_a)
        delta_lambda = radians(_normalise_longitude(longitude_b - longitude_a))
        haversine = sin(delta_phi / 2) ** 2 + cos(phi_a) * cos(phi_b) * sin(delta_lambda / 2) ** 2
        total_metres += 2 * EARTH_RADIUS_M * asin(min(1.0, sqrt(haversine)))
    return total_metres / METRES_PER_NAUTICAL_MILE
