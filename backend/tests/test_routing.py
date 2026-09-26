from datetime import UTC, datetime

import pytest

from app.routing.cost import EnvironmentalInput, calculate_risk
from app.routing.generator import ALGORITHM_VERSION, build_candidate_paths, distance_nm, great_circle
from app.routing.service import next_candidate_versions, vessel_speed_knots


def test_generator_returns_three_deterministic_paths_between_real_endpoints():
    origin, destination = (170.0, -70.0), (-170.0, -68.0)
    first, second = build_candidate_paths(origin, destination), build_candidate_paths(origin, destination)
    assert [path.route_type for path in first] == ["DIRECT", "NORTH_BIAS", "SOUTH_BIAS"]
    assert first == second
    assert all(path.coordinates[0] == origin and path.coordinates[-1] == destination for path in first)
    assert ALGORITHM_VERSION == "prototype-risk-routing-v1"


def test_biases_differ_from_direct_path_without_breaking_wgs84_bounds():
    paths = build_candidate_paths((20.0, -70.0), (50.0, -68.0))
    direct, north, south = paths
    assert north.coordinates != direct.coordinates
    assert south.coordinates != direct.coordinates
    assert north.coordinates[len(north.coordinates) // 2][1] > direct.coordinates[len(direct.coordinates) // 2][1]
    assert south.coordinates[len(south.coordinates) // 2][1] < direct.coordinates[len(direct.coordinates) // 2][1]
    assert all(-180 <= lon <= 180 and -90 <= lat <= 90 for path in paths for lon, lat in path.coordinates)


def test_dateline_geometry_and_distance_are_real_and_nonzero():
    coordinates = great_circle((179.0, -70.0), (-179.0, -70.0))
    assert coordinates[0] == (179.0, -70.0)
    assert coordinates[-1] == (-179.0, -70.0)
    assert distance_nm(coordinates) > 1.0
    assert distance_nm(coordinates) < 100.0


def test_distance_uses_nautical_miles():
    # One degree of longitude on the equator is approximately 60 nautical
    # miles; the tolerance accounts for the spherical distance implementation.
    assert distance_nm(great_circle((0.0, 0.0), (1.0, 0.0))) == pytest.approx(60.04, abs=0.1)


def test_invalid_or_identical_endpoints_are_rejected():
    with pytest.raises(ValueError):
        build_candidate_paths((0.0, 91.0), (1.0, 1.0))
    with pytest.raises(ValueError):
        build_candidate_paths((0.0, 0.0), (0.0, 0.0))


class Vessel:
    def __init__(self, specifications):
        self.specifications = specifications


def test_duration_requires_explicit_positive_knots_speed():
    assert vessel_speed_knots(Vessel({})) is None
    assert vessel_speed_knots(Vessel({"cruising_speed_knots": 12})) == 12.0
    assert vessel_speed_knots(Vessel({"speed_knots": 0})) is None


def test_candidate_versions_start_at_one_and_increment_on_regeneration():
    assert next_candidate_versions(None) == (1, 2, 3)
    assert next_candidate_versions(3) == (4, 5, 6)


def _observation(domain, value, units):
    return EnvironmentalInput(domain, "observation", "source", "LIVE", value, units,
                              datetime.now(UTC).isoformat(), None, None, 2.0)


def test_environmental_risk_uses_only_compatible_persisted_values():
    risk, components, warnings = calculate_risk({
        "sea_ice": _observation("sea_ice", {"concentration": 50}, "percent"),
        "weather": _observation("weather", {"wind_speed": 15}, "m s-1"),
        "ocean": _observation("ocean", {"speed": 1}, "m s-1"),
    })
    assert risk == pytest.approx(0.5)
    assert components["availability"] == "AVAILABLE"
    assert warnings == []


def test_environmental_values_change_the_transparent_risk_score():
    low, _, _ = calculate_risk({"sea_ice": _observation("sea_ice", {"concentration": 10}, "percent")})
    high, _, _ = calculate_risk({"sea_ice": _observation("sea_ice", {"concentration": 90}, "percent")})
    assert low == pytest.approx(0.1)
    assert high == pytest.approx(0.9)


def test_unavailable_environment_never_becomes_zero_risk():
    risk, components, warnings = calculate_risk({})
    assert risk is None
    assert components["availability"] == "UNAVAILABLE"
    assert warnings
