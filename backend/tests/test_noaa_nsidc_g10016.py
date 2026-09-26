"""Deterministic G10016-format fixtures only; no fixture value is real environmental data."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest
import xarray as xr
from pyproj import Transformer

from app.config import ProviderConfiguration, Settings
from app.environment.noaa_nsidc_g10016 import (EXPECTED_CRS, PRODUCT, ProviderDownloadError,
    NoaaNsidcG10016Adapter)
from app.environment.providers import (EnvironmentalDomain, GeographicPoint, ObservationStatus,
    ProviderCollectionService, ProviderFetchRequest, ProviderRegistry)


OBSERVED = datetime(2026, 9, 12, tzinfo=UTC)
CONFIG = ProviderConfiguration("noaa_nsidc_g10016", True, "https://provider.example/G10016_V4", None, 5, 48, 3)


class FixtureDownloader:
    def __init__(self, payload: bytes | Exception):
        self.payload = payload
        self.urls: list[str] = []

    def download(self, url: str, timeout_seconds: int) -> bytes:
        self.urls.append(url)
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


def antarctic_location() -> GeographicPoint:
    longitude, latitude = Transformer.from_crs(EXPECTED_CRS, "EPSG:4326", always_xy=True).transform(0, -1_000_000)
    return GeographicPoint(longitude, latitude)


def g10016_format_fixture(tmp_path: Path, *, concentration: float = 0.4, values: np.ndarray | None = None, spatial_flag: int = 0, crs_wkt: str | None = None, include_variable: bool = True) -> bytes:
    """Creates a tiny synthetic CF/NetCDF4 test file with G10016's documented variables."""
    coords = {"time": [np.datetime64("2026-09-12T00:00:00")], "y": [-1_025_000.0, -1_000_000.0], "x": [-25_000.0, 0.0, 25_000.0]}
    variables = {"crs": xr.DataArray(0, attrs={"spatial_ref": crs_wkt or EXPECTED_CRS.to_wkt()})}
    if include_variable:
        concentration_values = values if values is not None else np.full((1, 2, 3), concentration, dtype=np.float32)
        variables["cdr_seaice_conc"] = xr.DataArray(concentration_values, dims=("time", "y", "x"), attrs={"units": "1", "long_name": "test-only concentration", "grid_mapping": "crs"})
        variables["cdr_seaice_conc_interp_spatial_flag"] = xr.DataArray(np.full((1, 2, 3), spatial_flag, dtype=np.uint8), dims=("time", "y", "x"))
    file_path = tmp_path / "g10016-format-test-only.nc"
    xr.Dataset(variables, coords=coords, attrs={"title": "test-only G10016-format fixture"}).to_netcdf(file_path, engine="h5netcdf")
    return file_path.read_bytes()


def collection(adapter: NoaaNsidcG10016Adapter):
    registry = ProviderRegistry()
    registry.register(adapter)
    return ProviderCollectionService(registry)


def request() -> ProviderFetchRequest:
    return ProviderFetchRequest(EnvironmentalDomain.SEA_ICE, antarctic_location(), OBSERVED)


def request_at_projected(x: float, y: float) -> ProviderFetchRequest:
    longitude, latitude = Transformer.from_crs(EXPECTED_CRS, "EPSG:4326", always_xy=True).transform(x, y)
    return ProviderFetchRequest(EnvironmentalDomain.SEA_ICE, GeographicPoint(longitude, latitude), OBSERVED)


def test_parses_g10016_format_fixture_and_preserves_antartic_crs_provenance(tmp_path):
    downloader = FixtureDownloader(g10016_format_fixture(tmp_path))
    adapter = NoaaNsidcG10016Adapter(downloader, clock=lambda: OBSERVED + timedelta(hours=8))
    result = collection(adapter).collect(adapter.name, request(), CONFIG)
    observation = result.observations[0]
    assert result.status == ObservationStatus.LIVE
    assert observation.value == {"concentration": pytest.approx(0.4)}
    assert observation.location == antarctic_location()
    assert observation.provenance.product == PRODUCT
    assert observation.provenance.details["dataset_id"] == "G10016"
    assert observation.provenance.details["dataset_version"] == "4"
    assert observation.provenance.details["crs"] == "EPSG:3412"
    assert observation.provenance.details["projected_x_m"] == 0.0
    assert observation.provenance.details["fallback_used"] is False
    assert observation.provenance.details["fallback_method"] == "exact_nearest_grid_cell"
    assert downloader.urls == ["https://provider.example/G10016_V4/south/daily/2026/sic_pss25_20260912_am2_icdr_v04r00.nc"]


def test_stale_and_degraded_classification_are_explicit(tmp_path):
    stale = NoaaNsidcG10016Adapter(FixtureDownloader(g10016_format_fixture(tmp_path)), clock=lambda: OBSERVED + timedelta(days=3))
    stale_config = ProviderConfiguration("noaa_nsidc_g10016", True, CONFIG.endpoint, None, 5, 24, 3)
    stale_result = collection(stale).collect(stale.name, request(), stale_config)
    degraded = NoaaNsidcG10016Adapter(FixtureDownloader(g10016_format_fixture(tmp_path, spatial_flag=1)), clock=lambda: OBSERVED + timedelta(hours=1))
    degraded_result = collection(degraded).collect(degraded.name, request(), CONFIG)
    assert stale_result.status == ObservationStatus.STALE
    assert degraded_result.status == ObservationStatus.DEGRADED


@pytest.mark.parametrize("payload", [ProviderDownloadError("NETWORK_ERROR"), b"not-a-netcdf-file"])
def test_network_or_malformed_data_returns_error_without_observation_values(payload):
    adapter = NoaaNsidcG10016Adapter(FixtureDownloader(payload), clock=lambda: OBSERVED)
    result = collection(adapter).collect(adapter.name, request(), CONFIG)
    assert result.status == ObservationStatus.ERROR
    assert result.observations[0].value is None
    assert result.observations[0].is_persistable is False


def test_missing_variable_invalid_value_and_unexpected_crs_are_rejected(tmp_path):
    adapter = NoaaNsidcG10016Adapter(FixtureDownloader(g10016_format_fixture(tmp_path, include_variable=False)), clock=lambda: OBSERVED)
    assert collection(adapter).collect(adapter.name, request(), CONFIG).status == ObservationStatus.ERROR
    invalid = NoaaNsidcG10016Adapter(FixtureDownloader(g10016_format_fixture(tmp_path, concentration=1.1)), clock=lambda: OBSERVED)
    assert collection(invalid).collect(invalid.name, request(), CONFIG).status == ObservationStatus.ERROR
    unexpected = NoaaNsidcG10016Adapter(FixtureDownloader(g10016_format_fixture(tmp_path, crs_wkt="EPSG:4326")), clock=lambda: OBSERVED)
    assert collection(unexpected).collect(unexpected.name, request(), CONFIG).status == ObservationStatus.ERROR


def test_nan_exact_cell_uses_nearest_valid_cell_and_records_degraded_provenance(tmp_path):
    values = np.full((1, 2, 3), np.nan, dtype=np.float32)
    values[0, 1, 2] = 1.0  # x=25 km, y=-1000 km; nearest real observation.
    adapter = NoaaNsidcG10016Adapter(FixtureDownloader(g10016_format_fixture(tmp_path, values=values)), clock=lambda: OBSERVED + timedelta(hours=1))
    result = collection(adapter).collect(adapter.name, request(), CONFIG)
    observation = result.observations[0]
    assert result.status == ObservationStatus.DEGRADED
    assert observation.value == {"concentration": 1.0}
    assert observation.location == GeographicPoint(*Transformer.from_crs(EXPECTED_CRS, "EPSG:4326", always_xy=True).transform(25_000, -1_000_000))
    assert observation.provenance.details["fallback_used"] is True
    assert observation.provenance.details["fallback_method"] == "nearest_valid_grid_cell"
    assert observation.provenance.details["fallback_distance_km"] == pytest.approx(25.0)
    assert observation.provenance.details["max_fallback_distance_km"] == 75.0
    assert observation.provenance.details["requested_projected_x_m"] == pytest.approx(0.0, abs=1e-6)
    assert observation.provenance.details["selected_projected_x_m"] == 25_000.0


@pytest.mark.parametrize("radius_km", [10, 24.9])
def test_nan_exact_cell_without_valid_observation_inside_radius_is_unavailable(tmp_path, radius_km):
    values = np.full((1, 2, 3), np.nan, dtype=np.float32)
    values[0, 1, 2] = 0.6
    config = ProviderConfiguration(
        CONFIG.name, CONFIG.enabled, CONFIG.endpoint, CONFIG.api_key,
        CONFIG.timeout_seconds, CONFIG.freshness_hours, CONFIG.lookback_days,
        radius_km,
    )
    adapter = NoaaNsidcG10016Adapter(FixtureDownloader(g10016_format_fixture(tmp_path, values=values)), clock=lambda: OBSERVED)
    result = collection(adapter).collect(adapter.name, request(), config)
    observation = result.observations[0]
    assert result.status == ObservationStatus.UNAVAILABLE
    assert observation.value is None
    assert observation.units is None
    assert observation.provenance.details["failure_code"] == "NO_VALID_CELL_WITHIN_FALLBACK_RADIUS"


def test_fallback_selects_lowest_projected_x_for_effectively_equal_distances(tmp_path):
    values = np.full((1, 2, 3), np.nan, dtype=np.float32)
    values[0, 1, 0] = 0.2
    values[0, 1, 2] = 0.8
    adapter = NoaaNsidcG10016Adapter(FixtureDownloader(g10016_format_fixture(tmp_path, values=values)), clock=lambda: OBSERVED)
    # The requested x=0 cell is missing; equal-distance cells select x=-25 km first.
    result = collection(adapter).collect(adapter.name, request(), CONFIG)
    assert result.observations[0].value == {"concentration": pytest.approx(0.2)}
    assert result.observations[0].provenance.details["selected_projected_x_m"] == -25_000.0


def test_fallback_handles_grid_edge_without_out_of_bounds_indexing(tmp_path):
    values = np.full((1, 2, 3), np.nan, dtype=np.float32)
    values[0, 1, 1] = 0.4
    adapter = NoaaNsidcG10016Adapter(FixtureDownloader(g10016_format_fixture(tmp_path, values=values)), clock=lambda: OBSERVED)
    result = collection(adapter).collect(adapter.name, request_at_projected(-25_000, -1_000_000), CONFIG)
    observation = result.observations[0]
    assert observation.status == ObservationStatus.DEGRADED
    assert observation.value == {"concentration": pytest.approx(0.4)}
    assert observation.provenance.details["selected_projected_x_m"] == 0.0


def test_missing_daily_files_produce_unavailable_not_fake_observations():
    adapter = NoaaNsidcG10016Adapter(FixtureDownloader(ProviderDownloadError("FILE_NOT_FOUND")), clock=lambda: OBSERVED)
    result = collection(adapter).collect(adapter.name, request(), CONFIG)
    assert result.status == ObservationStatus.UNAVAILABLE
    assert result.observations[0].value is None
    assert result.observations[0].is_persistable is False


@pytest.mark.live_provider
def test_live_noaa_nsidc_request_when_explicitly_enabled():
    settings = Settings.from_environment()
    config = settings.provider_configuration("noaa_nsidc_g10016")
    if not config or not config.enabled or __import__("os").environ.get("KURMESH_RUN_LIVE_PROVIDER_TESTS") != "true":
        pytest.skip("Set enabled NOAA configuration and KURMESH_RUN_LIVE_PROVIDER_TESTS=true to contact NSIDC")
    adapter = NoaaNsidcG10016Adapter()
    result = collection(adapter).collect(adapter.name, ProviderFetchRequest(EnvironmentalDomain.SEA_ICE, GeographicPoint(0, -70)), config)
    assert result.status in {ObservationStatus.LIVE, ObservationStatus.STALE, ObservationStatus.DEGRADED}
