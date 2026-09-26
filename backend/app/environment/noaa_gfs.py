"""NOAA GFS 0.25 degree forecast adapter.

Uses the NOMADS GRIB filter so each request downloads only four fields and a
small geographic window.  The adapter returns forecasts; ``observed_at`` is
the model run time and ``valid_to`` is the selected forecast valid time.
"""

from __future__ import annotations

import hashlib
import math
import os
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

import numpy as np
import xarray as xr
import cfgrib

from app.config import ProviderConfiguration
from app.environment.providers import (
    EnvironmentalDomain, EnvironmentalProviderAdapter, GeographicPoint,
    NormalizedEnvironmentalObservation, ObservationProvenance, ObservationStatus,
    ProviderFetchRequest, ProviderUnavailableError,
)

PROVIDER_NAME = "noaa_gfs"
PRODUCT = "NOAA Global Forecast System (GFS) 0.25 degree"
DATASET_ID = "GFS_0P25"
REQUIRED_VARIABLES = {"u10": ("u10", "10u", "ugrd10m"), "v10": ("v10", "10v", "vgrd10m"), "t2m": ("t2m", "2t", "tmp2m"), "prmsl": ("prmsl", "msl", "prmslmsl")}


class ProviderDownloadError(Exception):
    pass


class ProviderDataError(Exception):
    pass


class Downloader(Protocol):
    def download(self, url: str, timeout_seconds: int) -> bytes: ...


class HttpDownloader:
    def download(self, url: str, timeout_seconds: int) -> bytes:
        try:
            with urlopen(url, timeout=timeout_seconds) as response:  # noqa: S310 - validated configured endpoint
                return response.read()
        except HTTPError as exc:
            if exc.code == 404:
                raise ProviderDownloadError("FILE_NOT_FOUND") from exc
            raise ProviderDownloadError("HTTP_ERROR") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise ProviderDownloadError("NETWORK_ERROR") from exc


class NoaaGfsAdapter:
    name = PROVIDER_NAME
    supported_domains = frozenset({EnvironmentalDomain.WEATHER})

    def __init__(self, downloader: Downloader | None = None, clock: Callable[[], datetime] | None = None) -> None:
        self.downloader = downloader or HttpDownloader()
        self.clock = clock or (lambda: datetime.now(UTC))

    def fetch(self, request: ProviderFetchRequest, configuration: ProviderConfiguration) -> tuple[NormalizedEnvironmentalObservation, ...]:
        if request.domain is not EnvironmentalDomain.WEATHER:
            raise ProviderDataError("UNSUPPORTED_DOMAIN")
        if request.location is None:
            raise ProviderDataError("LOCATION_REQUIRED")
        if not configuration.endpoint:
            raise ProviderDataError("ENDPOINT_REQUIRED")
        run_time, forecast_hour = self._forecast_selection(request.observed_after)
        url = self._file_url(configuration.endpoint, run_time, forecast_hour, request.location, configuration.max_fallback_distance_km)
        payload = self.downloader.download(url, configuration.timeout_seconds)
        return self._parse(payload, url, request.location, configuration, run_time, forecast_hour)

    def _forecast_selection(self, requested_time: datetime | None) -> tuple[datetime, int]:
        """Choose the latest completed six-hour cycle and forecast valid at target."""
        target = (requested_time or self.clock()).astimezone(UTC)
        # GFS files are not assumed ready immediately at cycle time.
        available = self.clock().astimezone(UTC) - timedelta(hours=6)
        base = min(target, available).replace(minute=0, second=0, microsecond=0)
        run = base.replace(hour=(base.hour // 6) * 6)
        lead = max(0, math.ceil((target - run).total_seconds() / 3600))
        return run, lead

    @staticmethod
    def _file_url(endpoint: str, run: datetime, forecast_hour: int, location: GeographicPoint, radius_km: float) -> str:
        # 0.25 degrees is roughly 28 km; request a conservative local window.
        delta = max(0.25, radius_km / 100)
        left = (location.longitude - delta) % 360
        right = (location.longitude + delta) % 360
        if left > right:  # NOMADS subregions do not cross its 0/360 seam.
            left, right = 0, 359.75
        params = {
            "file": f"gfs.t{run:%H}z.pgrb2.0p25.f{forecast_hour:03d}",
            "var_UGRD": "on", "var_VGRD": "on", "var_TMP": "on", "var_PRMSL": "on",
            "lev_10_m_above_ground": "on", "lev_2_m_above_ground": "on", "lev_mean_sea_level": "on",
            "subregion": "", "leftlon": f"{left:.2f}", "rightlon": f"{right:.2f}",
            "toplat": f"{min(90, location.latitude + delta):.2f}", "bottomlat": f"{max(-90, location.latitude - delta):.2f}",
            "dir": f"/gfs.{run:%Y%m%d}/{run:%H}/atmos",
        }
        return f"{endpoint}?{urlencode(params)}"

    def _parse(self, payload: bytes, source_url: str, request_location: GeographicPoint, configuration: ProviderConfiguration, run_time: datetime, forecast_hour: int) -> tuple[NormalizedEnvironmentalObservation, ...]:
        if not payload:
            raise ProviderDataError("EMPTY_FILE")
        descriptor, filename = tempfile.mkstemp(suffix=".grib2")
        path = Path(filename)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
            # Variables are on different GRIB surfaces, so cfgrib separates them.
            # Merge only the filtered message groups returned for this one request.
            datasets = cfgrib.open_datasets(path, indexpath="")
            dataset = xr.merge(datasets, compat="override")
            try:
                return self._normalized_from_dataset(dataset, source_url, request_location, configuration, run_time, forecast_hour, hashlib.sha256(payload).hexdigest())
            finally:
                for item in datasets:
                    item.close()
        except (OSError, ValueError, KeyError) as exc:
            raise ProviderDataError("MALFORMED_GRIB") from exc
        finally:
            path.unlink(missing_ok=True)

    def _normalized_from_dataset(self, dataset: xr.Dataset, source_url: str, request_location: GeographicPoint, configuration: ProviderConfiguration, run_time: datetime, forecast_hour: int, checksum: str) -> tuple[NormalizedEnvironmentalObservation, ...]:
        latitude_name, longitude_name = self._coordinate_names(dataset)
        variables = self._required_variables(dataset)
        selected, fallback_distance_km = self._select_cell(variables, latitude_name, longitude_name, request_location, configuration.max_fallback_distance_km)
        if selected is None:
            return (self._unavailable(source_url, checksum, request_location, configuration.max_fallback_distance_km),)
        y_index, x_index, selected_latitude, selected_longitude = selected
        u, v, temperature, pressure = (float(variables[key].isel({latitude_name: y_index, longitude_name: x_index}).values) for key in ("u10", "v10", "t2m", "prmsl"))
        self._validate_values(u, v, temperature, pressure)
        temperature_c = self._temperature_celsius(temperature, variables["t2m"].attrs.get("units"))
        pressure_hpa = self._pressure_hpa(pressure, variables["prmsl"].attrs.get("units"))
        valid_time = self._valid_time(dataset, run_time, forecast_hour)
        retrieved_at = self.clock().astimezone(UTC)
        status = ObservationStatus.DEGRADED if fallback_distance_km is not None else (ObservationStatus.LIVE if retrieved_at - run_time <= timedelta(hours=configuration.freshness_hours) else ObservationStatus.STALE)
        longitude = self._wgs84_longitude(selected_longitude)
        details = {
            "dataset_id": DATASET_ID, "model_cycle_utc": run_time.isoformat(), "forecast_hour": forecast_hour,
            "forecast_valid_time_utc": valid_time.isoformat(), "requested_longitude": request_location.longitude,
            "requested_latitude": request_location.latitude, "selected_longitude": longitude,
            "selected_latitude": selected_latitude, "source_units": {key: variables[key].attrs.get("units") for key in variables},
            "normalized_units": {"wind": "m s-1", "air_temperature": "degC", "sea_level_pressure": "hPa"},
            "fallback_used": fallback_distance_km is not None, "fallback_method": "nearest_valid_grid_cell" if fallback_distance_km is not None else "exact_nearest_grid_cell",
            "fallback_distance_km": fallback_distance_km, "max_fallback_distance_km": configuration.max_fallback_distance_km,
        }
        provenance = ObservationProvenance("NOAA/NCEP", PRODUCT, source_url, f"sha256:{checksum}", details)
        point = GeographicPoint(longitude, selected_latitude)
        wind_speed = math.hypot(u, v)
        wind_direction = (math.degrees(math.atan2(-u, -v)) + 360) % 360
        common = {"status": status, "observed_at": run_time, "retrieved_at": retrieved_at, "provenance": provenance, "location": point, "resolution": "0.25 degree", "valid_to": valid_time, "metadata": {"forecast": True, "grid_latitude_name": latitude_name, "grid_longitude_name": longitude_name}}
        return (
            NormalizedEnvironmentalObservation("wind", value={"u_component": u, "v_component": v, "speed": wind_speed, "direction_degrees": wind_direction}, units="m s-1", **common),
            NormalizedEnvironmentalObservation("air_temperature", value={"temperature": temperature_c}, units="degC", **common),
            NormalizedEnvironmentalObservation("sea_level_pressure", value={"pressure": pressure_hpa}, units="hPa", **common),
        )

    @staticmethod
    def _coordinate_names(dataset: xr.Dataset) -> tuple[str, str]:
        latitude = next((name for name in ("latitude", "lat") if name in dataset.coords), None)
        longitude = next((name for name in ("longitude", "lon") if name in dataset.coords), None)
        if latitude is None or longitude is None or dataset[latitude].ndim != 1 or dataset[longitude].ndim != 1:
            raise ProviderDataError("INVALID_COORDINATES")
        return latitude, longitude

    @staticmethod
    def _required_variables(dataset: xr.Dataset) -> dict[str, xr.DataArray]:
        result = {}
        for normalized, names in REQUIRED_VARIABLES.items():
            name = next((candidate for candidate in names if candidate in dataset), None)
            if name is None:
                raise ProviderDataError(f"MISSING_{normalized.upper()}")
            result[normalized] = dataset[name]
        return result

    @classmethod
    def _select_cell(cls, variables: dict[str, xr.DataArray], latitude_name: str, longitude_name: str, requested: GeographicPoint, radius_km: float) -> tuple[tuple[int, int, float, float] | None, float | None]:
        latitudes = np.asarray(next(iter(variables.values())).coords[latitude_name].values, dtype=float)
        longitudes = np.asarray(next(iter(variables.values())).coords[longitude_name].values, dtype=float)
        normalized_request_lon = requested.longitude % 360
        lat_grid, lon_grid = np.meshgrid(latitudes, longitudes, indexing="ij")
        distances = cls._haversine_km(requested.latitude, normalized_request_lon, lat_grid, lon_grid)
        valid = np.ones(distances.shape, dtype=bool)
        for value in variables.values():
            values = np.asarray(value.values, dtype=float)
            valid &= np.isfinite(values)
        if not valid.any():
            return None, None
        raw_nearest = float(distances.min())
        raw_tied = np.argwhere(np.isclose(distances, raw_nearest, rtol=0, atol=1e-9))
        raw_order = np.lexsort((lat_grid[raw_tied[:, 0], raw_tied[:, 1]], lon_grid[raw_tied[:, 0], raw_tied[:, 1]]))
        raw_y, raw_x = raw_tied[raw_order[0]]
        nearest = float(np.where(valid, distances, np.inf).min())
        if nearest > radius_km:
            return None, None
        tied = np.argwhere(valid & np.isclose(distances, nearest, rtol=0, atol=1e-9))
        # Deterministic geographic tie-break: lowest normalized longitude, then latitude.
        order = np.lexsort((lat_grid[tied[:, 0], tied[:, 1]], lon_grid[tied[:, 0], tied[:, 1]]))
        y, x = tied[order[0]]
        # The nearest grid cell is the direct observation even when the requested
        # coordinate falls between GFS grid points. Only a missing direct cell is
        # a fallback, not ordinary nearest-neighbour extraction.
        direct = y == raw_y and x == raw_x
        return (int(y), int(x), float(latitudes[y]), float(longitudes[x])), (None if direct else nearest)

    @staticmethod
    def _haversine_km(latitude: float, longitude: float, lat_grid: np.ndarray, lon_grid: np.ndarray) -> np.ndarray:
        dlat = np.radians(lat_grid - latitude)
        dlon = np.radians((lon_grid - longitude + 180) % 360 - 180)
        a = np.sin(dlat / 2) ** 2 + math.cos(math.radians(latitude)) * np.cos(np.radians(lat_grid)) * np.sin(dlon / 2) ** 2
        return 6371.0088 * 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))

    @staticmethod
    def _validate_values(*values: float) -> None:
        if not all(math.isfinite(value) for value in values):
            raise ProviderDataError("INVALID_WEATHER_VALUE")
        if values[-1] <= 0:
            raise ProviderDataError("INVALID_SEA_LEVEL_PRESSURE")

    @staticmethod
    def _temperature_celsius(value: float, units: object) -> float:
        if str(units).lower() in {"k", "kelvin"}:
            return value - 273.15
        if str(units).lower() in {"c", "degc", "celsius"}:
            return value
        raise ProviderDataError("UNSUPPORTED_TEMPERATURE_UNITS")

    @staticmethod
    def _pressure_hpa(value: float, units: object) -> float:
        if str(units).lower() in {"pa", "pascal", "pascals"}:
            return value / 100
        if str(units).lower() in {"hpa", "mbar"}:
            return value
        raise ProviderDataError("UNSUPPORTED_PRESSURE_UNITS")

    @staticmethod
    def _valid_time(dataset: xr.Dataset, run: datetime, forecast_hour: int) -> datetime:
        value = dataset.coords.get("valid_time")
        if value is not None:
            raw = value.values.item() if value.values.size == 1 else value.values.reshape(-1)[0]
            if isinstance(raw, np.datetime64):
                return datetime.fromtimestamp(raw.astype("datetime64[s]").astype(int), UTC)
        return run + timedelta(hours=forecast_hour)

    @staticmethod
    def _wgs84_longitude(value: float) -> float:
        return value - 360 if value > 180 else value

    def _unavailable(self, source_url: str, checksum: str, requested: GeographicPoint, radius_km: float) -> NormalizedEnvironmentalObservation:
        return NormalizedEnvironmentalObservation("weather", ObservationStatus.UNAVAILABLE, None, self.clock().astimezone(UTC), ObservationProvenance("NOAA/NCEP", PRODUCT, source_url, f"sha256:{checksum}", {"dataset_id": DATASET_ID, "requested_longitude": requested.longitude, "requested_latitude": requested.latitude, "max_fallback_distance_km": radius_km, "failure_code": "NO_VALID_CELL_WITHIN_FALLBACK_RADIUS"}), metadata={"failure_code": "NO_VALID_CELL_WITHIN_FALLBACK_RADIUS"})


assert isinstance(NoaaGfsAdapter(), EnvironmentalProviderAdapter)
