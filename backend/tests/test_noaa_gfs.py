"""Synthetic local GFS grids only; tests never contact NOAA."""

from datetime import UTC, datetime, timedelta
import os

import numpy as np
import pytest
import xarray as xr

from app.config import ProviderConfiguration, Settings
from app.environment.noaa_gfs import NoaaGfsAdapter, ProviderDataError
from app.environment.providers import EnvironmentalDomain, GeographicPoint, ObservationStatus, ProviderFetchRequest

NOW = datetime(2026, 9, 15, 6, tzinfo=UTC)
RUN = datetime(2026, 9, 15, tzinfo=UTC)
CONFIG = ProviderConfiguration("noaa_gfs", True, "https://provider.example/filter", None, 5, 6, 0, 75)


def dataset(*, u: np.ndarray | None = None, temperature_units: str = "K") -> xr.Dataset:
    coords = {"latitude": [-70.25, -70.0], "longitude": [0.0, 0.25], "valid_time": np.datetime64("2026-09-15T06:00:00")}
    values = np.full((2, 2), 5.0) if u is None else u
    return xr.Dataset({
        "u10": xr.DataArray(values, dims=("latitude", "longitude"), attrs={"units": "m s-1"}),
        "v10": xr.DataArray(np.full((2, 2), -5.0), dims=("latitude", "longitude"), attrs={"units": "m s-1"}),
        "t2m": xr.DataArray(np.full((2, 2), 273.15), dims=("latitude", "longitude"), attrs={"units": temperature_units}),
        "prmsl": xr.DataArray(np.full((2, 2), 101325.0), dims=("latitude", "longitude"), attrs={"units": "Pa"}),
    }, coords=coords)


def normalize(grid: xr.Dataset, location: GeographicPoint = GeographicPoint(0, -70)):
    return NoaaGfsAdapter(clock=lambda: NOW)._normalized_from_dataset(grid, "https://provider.example/gfs", location, CONFIG, RUN, 6, "test")


def test_normalizes_gfs_wind_temperature_pressure_and_forecast_provenance():
    wind, temperature, pressure = normalize(dataset())
    assert wind.status == ObservationStatus.LIVE
    assert wind.value["speed"] == pytest.approx(7.0710678)
    assert wind.value["direction_degrees"] == pytest.approx(315)
    assert temperature.value == {"temperature": pytest.approx(0)}
    assert temperature.units == "degC"
    assert pressure.value == {"pressure": pytest.approx(1013.25)}
    assert wind.observed_at == RUN
    assert wind.valid_to == NOW
    assert wind.provenance.details["model_cycle_utc"] == RUN.isoformat()
    assert wind.provenance.details["fallback_used"] is False


def test_nan_exact_grid_cell_uses_bounded_valid_fallback_as_degraded():
    # Requested/direct cell (-70.0, 0.0) is missing.  At this latitude the
    # longitudinal neighbour (-70.0, 0.25) is ~9.5077 km away, closer than
    # the latitudinal neighbour (-70.25, 0.0), which is ~27.8 km away.
    u = np.full((2, 2), 5.0)
    u[1, 0] = np.nan
    observations = normalize(dataset(u=u))
    assert observations[0].status == ObservationStatus.DEGRADED
    assert observations[0].provenance.details["fallback_used"] is True
    assert observations[0].provenance.details["selected_latitude"] == -70.0
    assert observations[0].provenance.details["selected_longitude"] == 0.25
    assert observations[0].provenance.details["fallback_distance_km"] == pytest.approx(9.50773266, abs=1e-6)


def test_no_complete_valid_cell_inside_radius_is_unavailable():
    u = np.full((2, 2), np.nan)
    observation = normalize(dataset(u=u))[0]
    assert observation.status == ObservationStatus.UNAVAILABLE
    assert observation.value is None and observation.units is None


def test_invalid_units_and_required_variables_are_provider_errors():
    with pytest.raises(ProviderDataError, match="UNSUPPORTED_TEMPERATURE_UNITS"):
        normalize(dataset(temperature_units="bananas"))
    with pytest.raises(ProviderDataError, match="MISSING_V10"):
        normalize(dataset().drop_vars("v10"))
    invalid_pressure = dataset()
    invalid_pressure["prmsl"] = invalid_pressure["prmsl"] * 0
    with pytest.raises(ProviderDataError, match="INVALID_SEA_LEVEL_PRESSURE"):
        normalize(invalid_pressure)


def test_stale_forecast_uses_cycle_freshness():
    stale = NoaaGfsAdapter(clock=lambda: RUN + timedelta(hours=7))
    observations = stale._normalized_from_dataset(dataset(), "https://provider.example/gfs", GeographicPoint(0, -70), CONFIG, RUN, 6, "test")
    assert observations[0].status == ObservationStatus.STALE


def test_rejects_non_weather_requests_before_network_access():
    adapter = NoaaGfsAdapter()
    with pytest.raises(ProviderDataError, match="UNSUPPORTED_DOMAIN"):
        adapter.fetch(ProviderFetchRequest(EnvironmentalDomain.SEA_ICE, GeographicPoint(0, -70)), CONFIG)


def test_missing_endpoint_remains_a_provider_error_before_network_access():
    missing_endpoint = ProviderConfiguration("noaa_gfs", True, None, None, 5, 6, 0, 75)
    with pytest.raises(ProviderDataError, match="ENDPOINT_REQUIRED"):
        NoaaGfsAdapter().fetch(ProviderFetchRequest(EnvironmentalDomain.WEATHER, GeographicPoint(0, -70)), missing_endpoint)


def test_noaa_gfs_endpoint_is_loaded_from_environment(monkeypatch):
    endpoint = "https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl"
    monkeypatch.setenv("KURMESH_ENVIRONMENT_PROVIDERS", "noaa_gfs")
    monkeypatch.setenv("KURMESH_ENVIRONMENT_PROVIDER_NOAA_GFS_ENABLED", "true")
    monkeypatch.setenv("KURMESH_ENVIRONMENT_PROVIDER_NOAA_GFS_ENDPOINT", endpoint)
    configuration = Settings.from_environment().provider_configuration("noaa_gfs")
    assert configuration is not None
    assert configuration.enabled is True
    assert configuration.endpoint == endpoint


@pytest.mark.live_provider
def test_live_noaa_gfs_when_explicitly_enabled():
    configuration = Settings.from_environment().provider_configuration("noaa_gfs")
    if not configuration or not configuration.enabled or not configuration.endpoint or os.environ.get("KURMESH_RUN_LIVE_PROVIDER_TESTS") != "true":
        pytest.skip("Set NOAA GFS provider, enabled state, endpoint, and KURMESH_RUN_LIVE_PROVIDER_TESTS=true to contact NOMADS")
    observations = NoaaGfsAdapter().fetch(ProviderFetchRequest(EnvironmentalDomain.WEATHER, GeographicPoint(0, -70)), configuration)
    assert len(observations) == 3
    assert {item.status for item in observations} <= {ObservationStatus.LIVE, ObservationStatus.STALE, ObservationStatus.DEGRADED}
