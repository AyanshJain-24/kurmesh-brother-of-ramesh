"""Synthetic Copernicus grids; no test contacts the Marine service."""
from datetime import UTC, datetime, timedelta
import os
import numpy as np
import pytest
import xarray as xr

from app.config import ProviderConfiguration
from app.environment.copernicus_marine_ocean import CopernicusMarineOceanAdapter, ProviderDataError
from app.environment.providers import EnvironmentalDomain, GeographicPoint, ObservationStatus, ProviderFetchRequest

RUN=datetime(2026,9,15,tzinfo=UTC); NOW=RUN+timedelta(hours=1)
CONFIG=ProviderConfiguration("copernicus_marine_ocean", True, "https://data.marine.copernicus.eu", None, 60, 24, 0, 75)

def grids(*, u=None, temperature_units="K"):
    coords={"time":[np.datetime64("2026-09-15T00:00:00")],"depth":[0.5,10.0],"latitude":[-70.1,-70.0],"longitude":[0.0,0.1]}
    shape=(1,2,2,2); u=np.full(shape, 3.) if u is None else u
    current=xr.Dataset({"uo":xr.DataArray(u,dims=("time","depth","latitude","longitude"),attrs={"units":"m s-1"}),"vo":xr.DataArray(np.full(shape,4.),dims=("time","depth","latitude","longitude"),attrs={"units":"m s-1"})},coords=coords)
    temperature=xr.Dataset({"thetao":xr.DataArray(np.full(shape,273.15),dims=("time","depth","latitude","longitude"),attrs={"units":temperature_units})},coords=coords)
    return current,temperature

def normalize(current,temperature): return CopernicusMarineOceanAdapter(clock=lambda:NOW)._normalized(current,temperature,GeographicPoint(0,-70),CONFIG,{"minimum_longitude":-.75,"maximum_longitude":.75,"minimum_latitude":-70.75,"maximum_latitude":-69.25})

@pytest.mark.parametrize(("latitude", "expected_minimum", "expected_maximum"), [
    (-85.0, -85.75, -84.25),
    (-89.8, -90.0, -89.05),
    (-70.0, -70.75, -69.25),
])
def test_antarctic_subset_bounds_are_valid_through_the_south_pole(latitude, expected_minimum, expected_maximum):
    bounds=CopernicusMarineOceanAdapter._bounds(GeographicPoint(0, latitude), 75)
    assert bounds["minimum_latitude"] == pytest.approx(expected_minimum)
    assert bounds["maximum_latitude"] == pytest.approx(expected_maximum)
    assert -90 <= bounds["minimum_latitude"] <= bounds["maximum_latitude"] <= 90

def test_normalizes_surface_current_temperature_and_provenance():
    current,temperature=normalize(*grids())
    assert current.status is ObservationStatus.LIVE and current.value["speed"]==pytest.approx(5)
    assert current.value["direction_degrees"]==pytest.approx(36.86989765)
    assert temperature.value=={"temperature":pytest.approx(0)} and temperature.units=="degC"
    assert current.provenance.details["selected_depth_m"]==0.5
    assert current.provenance.details["fallback_used"] is False

def test_nan_direct_cell_uses_nearest_valid_grid_fallback():
    u=np.full((1,2,2,2),3.); u[:,:,1,0]=np.nan
    observation=normalize(*grids(u=u))[0]
    assert observation.status is ObservationStatus.DEGRADED
    assert observation.provenance.details["selected_longitude"]==0.1
    assert observation.provenance.details["fallback_distance_km"]==pytest.approx(3.8,rel=.05)

def test_no_valid_cell_returns_unavailable():
    u=np.full((1,2,2,2),np.nan)
    observation=normalize(*grids(u=u))[0]
    assert observation.status is ObservationStatus.UNAVAILABLE and observation.value is None

def test_reads_thetao_from_temperature_dataset_and_uses_shared_shallowest_depth():
    current,temperature=grids()
    temperature["thetao"] = temperature.thetao + 10
    temperature = temperature.assign_coords(depth=[10.0, 20.0])
    observations=normalize(current,temperature)
    assert observations[1].value == {"temperature": pytest.approx(10)}
    assert observations[0].provenance.details["selected_depth_m"] == 10.0

def test_missing_temperature_variable_and_mismatched_grid_are_not_silently_matched():
    current,temperature=grids()
    with pytest.raises(ProviderDataError,match="MISSING_REQUIRED_VARIABLE"): normalize(current,temperature.drop_vars("thetao"))
    with pytest.raises(ProviderDataError,match="INCOMPATIBLE_GRID_COORDINATES"):
        normalize(current,temperature.assign_coords(longitude=[0.01,0.11]))

def test_stale_missing_variable_invalid_units_and_domain_are_rejected():
    current,temperature=grids(); stale=CopernicusMarineOceanAdapter(clock=lambda:RUN+timedelta(hours=25))
    assert stale._normalized(current,temperature,GeographicPoint(0,-70),CONFIG,{})[0].status is ObservationStatus.STALE
    with pytest.raises(ProviderDataError,match="MISSING_REQUIRED_VARIABLE"): normalize(current.drop_vars("uo"),temperature)
    with pytest.raises(ProviderDataError,match="UNSUPPORTED_TEMPERATURE_UNITS"): normalize(current,grids(temperature_units="bananas")[1])
    with pytest.raises(ProviderDataError,match="UNSUPPORTED_DOMAIN"): CopernicusMarineOceanAdapter().fetch(ProviderFetchRequest(EnvironmentalDomain.WEATHER,GeographicPoint(0,-70)),CONFIG)

def test_missing_endpoint_and_credentials_are_explicit(monkeypatch):
    no_endpoint=ProviderConfiguration("copernicus_marine_ocean",True,None,None,60)
    with pytest.raises(ProviderDataError,match="ENDPOINT_REQUIRED"): CopernicusMarineOceanAdapter().fetch(ProviderFetchRequest(EnvironmentalDomain.OCEAN_CONDITIONS,GeographicPoint(0,-70)),no_endpoint)
    monkeypatch.delenv("COPERNICUSMARINE_SERVICE_USERNAME",raising=False); monkeypatch.delenv("COPERNICUSMARINE_SERVICE_PASSWORD",raising=False)
    with pytest.raises(ProviderDataError,match="CREDENTIALS_REQUIRED"): CopernicusMarineOceanAdapter().fetch(ProviderFetchRequest(EnvironmentalDomain.OCEAN_CONDITIONS,GeographicPoint(0,-70)),CONFIG)


@pytest.mark.live_provider
def test_live_copernicus_ocean_when_fully_configured():
    from app.config import Settings
    config=Settings.from_environment().provider_configuration("copernicus_marine_ocean")
    required=(config and config.enabled and config.endpoint and os.getenv("COPERNICUSMARINE_SERVICE_USERNAME") and os.getenv("COPERNICUSMARINE_SERVICE_PASSWORD") and os.getenv("KURMESH_RUN_LIVE_PROVIDER_TESTS")=="true")
    if not required: pytest.skip("Configure enabled Copernicus provider, endpoint, credentials, and KURMESH_RUN_LIVE_PROVIDER_TESTS=true")
    observations=CopernicusMarineOceanAdapter().fetch(ProviderFetchRequest(EnvironmentalDomain.OCEAN_CONDITIONS,GeographicPoint(0,-70)),config)
    assert len(observations)==2
