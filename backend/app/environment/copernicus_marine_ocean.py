"""Copernicus Marine global-ocean physics adapter using official bounded subsets."""
from __future__ import annotations

import math
import os
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

import numpy as np
import xarray as xr

from app.config import ProviderConfiguration
from app.environment.providers import (EnvironmentalDomain, EnvironmentalProviderAdapter,
    GeographicPoint, NormalizedEnvironmentalObservation, ObservationProvenance,
    ObservationStatus, ProviderFetchRequest)

PROVIDER_NAME = "copernicus_marine_ocean"
PRODUCT_ID = "GLOBAL_ANALYSISFORECAST_PHY_001_024"
CURRENT_DATASET_ID = "cmems_mod_glo_phy-cur_anfc_0.083deg_PT6H-i"
TEMPERATURE_DATASET_ID = "cmems_mod_glo_phy-thetao_anfc_0.083deg_PT6H-i"


class ProviderDataError(Exception):
    pass


class SubsetClient(Protocol):
    def subset(self, dataset_id: str, variables: list[str], bounds: dict[str, float], output_directory: str) -> Path: ...


class CopernicusMarineClient:
    """Credential boundary; credentials never leave this class in provenance/errors."""
    def __init__(self, username: str, password: str) -> None:
        self.username, self.password = username, password

    def subset(self, dataset_id: str, variables: list[str], bounds: dict[str, float], output_directory: str) -> Path:
        import copernicusmarine
        response = copernicusmarine.subset(dataset_id=dataset_id, variables=variables,
            minimum_longitude=bounds["minimum_longitude"], maximum_longitude=bounds["maximum_longitude"],
            minimum_latitude=bounds["minimum_latitude"], maximum_latitude=bounds["maximum_latitude"],
            minimum_depth=0, maximum_depth=50, output_directory=output_directory,
            output_filename=f"{dataset_id}.nc", username=self.username, password=self.password,
            disable_progress_bar=True)
        path = getattr(response, "file_path", response)
        return Path(path)


class CopernicusMarineOceanAdapter:
    name = PROVIDER_NAME
    supported_domains = frozenset({EnvironmentalDomain.OCEAN_CONDITIONS})

    def __init__(self, client: SubsetClient | None = None, clock: Callable[[], datetime] | None = None) -> None:
        self.client, self.clock = client, clock or (lambda: datetime.now(UTC))

    def fetch(self, request: ProviderFetchRequest, configuration: ProviderConfiguration) -> tuple[NormalizedEnvironmentalObservation, ...]:
        if request.domain is not EnvironmentalDomain.OCEAN_CONDITIONS:
            raise ProviderDataError("UNSUPPORTED_DOMAIN")
        if request.location is None:
            raise ProviderDataError("LOCATION_REQUIRED")
        if not configuration.endpoint:
            raise ProviderDataError("ENDPOINT_REQUIRED")
        client = self.client or self._authenticated_client()
        bounds = self._bounds(request.location, configuration.max_fallback_distance_km)
        with tempfile.TemporaryDirectory() as directory:
            current_path = client.subset(CURRENT_DATASET_ID, ["uo", "vo"], bounds, directory)
            temperature_path = client.subset(TEMPERATURE_DATASET_ID, ["thetao"], bounds, directory)
            try:
                with xr.open_dataset(current_path, engine="h5netcdf") as current, xr.open_dataset(temperature_path, engine="h5netcdf") as temperature:
                    return self._normalized(current, temperature, request.location, configuration, bounds)
            except (OSError, ValueError, KeyError) as exc:
                raise ProviderDataError("MALFORMED_OCEAN_DATA") from exc

    @staticmethod
    def _authenticated_client() -> CopernicusMarineClient:
        username, password = os.getenv("COPERNICUSMARINE_SERVICE_USERNAME"), os.getenv("COPERNICUSMARINE_SERVICE_PASSWORD")
        if not username or not password:
            raise ProviderDataError("CREDENTIALS_REQUIRED")
        return CopernicusMarineClient(username, password)

    @staticmethod
    def _bounds(point: GeographicPoint, radius_km: float) -> dict[str, float]:
        delta = max(0.0834, radius_km / 100)
        return {"minimum_longitude": max(-180, point.longitude-delta), "maximum_longitude": min(180, point.longitude+delta),
                "minimum_latitude": max(-90, point.latitude-delta), "maximum_latitude": min(90, point.latitude+delta)}

    def _normalized(self, current: xr.Dataset, temperature: xr.Dataset, requested: GeographicPoint, configuration: ProviderConfiguration, bounds: dict[str, float]) -> tuple[NormalizedEnvironmentalObservation, ...]:
        if not {"uo", "vo"} <= set(current) or "thetao" not in temperature:
            raise ProviderDataError("MISSING_REQUIRED_VARIABLE")
        current_coordinates = self._coordinates(current)
        temperature_coordinates = self._coordinates(temperature)
        lat, lon, depth = current_coordinates
        temperature_lat, temperature_lon, temperature_depth = temperature_coordinates
        if not self._same_horizontal_grid(current, temperature, current_coordinates, temperature_coordinates):
            raise ProviderDataError("INCOMPATIBLE_GRID_COORDINATES")
        cur = current[["uo", "vo"]].isel(time=-1) if "time" in current.dims else current[["uo", "vo"]]
        temp = temperature[["thetao"]].isel(time=-1) if "time" in temperature.dims else temperature[["thetao"]]
        observed_at = self._time(current)
        if self._time(temperature) != observed_at:
            raise ProviderDataError("INCOMPATIBLE_OBSERVATION_TIME")
        selected = self._select(cur, temp, (lat, lon, depth), (temperature_lat, temperature_lon, temperature_depth), requested, configuration.max_fallback_distance_km)
        if selected is None:
            return (self._unavailable(requested, configuration.max_fallback_distance_km, bounds),)
        current_depth_index, temperature_depth_index, y, x, distance = selected
        u = float(cur.uo.isel({depth: current_depth_index, lat: y, lon: x}).values)
        v = float(cur.vo.isel({depth: current_depth_index, lat: y, lon: x}).values)
        theta = float(temp.thetao.isel({temperature_depth: temperature_depth_index, temperature_lat: y, temperature_lon: x}).values)
        if not all(math.isfinite(value) for value in (u, v, theta)):
            raise ProviderDataError("INVALID_OCEAN_VALUE")
        temp_c = self._celsius(theta, temp.thetao.attrs.get("units"))
        if str(cur.uo.attrs.get("units")).lower() not in {"m s-1", "m/s", "m s**-1"} or str(cur.vo.attrs.get("units")).lower() not in {"m s-1", "m/s", "m s**-1"}:
            raise ProviderDataError("UNSUPPORTED_CURRENT_UNITS")
        latitudes, longitudes, depths = (np.asarray(cur.coords[name].values, dtype=float) for name in (lat, lon, depth))
        retrieved_at = self.clock().astimezone(UTC)
        status = ObservationStatus.DEGRADED if distance is not None else (ObservationStatus.LIVE if retrieved_at-observed_at <= timedelta(hours=configuration.freshness_hours) else ObservationStatus.STALE)
        selected_lon = self._longitude(longitudes[x])
        details = {"product_id": PRODUCT_ID, "current_dataset_id": CURRENT_DATASET_ID, "temperature_dataset_id": TEMPERATURE_DATASET_ID,
            "requested_longitude": requested.longitude, "requested_latitude": requested.latitude, "selected_longitude": selected_lon, "selected_latitude": float(latitudes[y]), "selected_depth_m": float(depths[current_depth_index]),
            "source_variables": ["uo", "vo", "thetao"], "source_units": {"uo": cur.uo.attrs.get("units"), "vo": cur.vo.attrs.get("units"), "thetao": temp.thetao.attrs.get("units")},
            "normalized_units": {"ocean_current": "m s-1", "sea_water_temperature": "degC"}, "fallback_used": distance is not None, "fallback_distance_km": distance,
            "max_fallback_distance_km": configuration.max_fallback_distance_km, "subset_bounds": bounds, "access_method": "copernicusmarine.subset", "observation_time_utc": observed_at.isoformat()}
        provenance = ObservationProvenance("Copernicus Marine", PRODUCT_ID, configuration.endpoint or "copernicusmarine", details=details)
        common = {"status": status, "observed_at": observed_at, "retrieved_at": retrieved_at, "provenance": provenance, "location": GeographicPoint(selected_lon, float(latitudes[y])), "resolution": "0.083 degree", "metadata": {"forecast": True, "selected_depth_m": float(depths[current_depth_index])}}
        speed = math.hypot(u, v)
        direction = (math.degrees(math.atan2(u, v)) + 360) % 360  # direction current flows toward, clockwise from north
        return (NormalizedEnvironmentalObservation("ocean_current", value={"u_component": u, "v_component": v, "speed": speed, "direction_degrees": direction}, units="m s-1", **common),
                NormalizedEnvironmentalObservation("sea_water_temperature", value={"temperature": temp_c}, units="degC", **common))

    @staticmethod
    def _coordinates(dataset: xr.Dataset) -> tuple[str, str, str]:
        lat = next((name for name in ("latitude", "lat") if name in dataset.coords), None); lon = next((name for name in ("longitude", "lon") if name in dataset.coords), None); depth = next((name for name in ("depth", "depthu", "deptht") if name in dataset.coords), None)
        if not lat or not lon or not depth or any(dataset[name].ndim != 1 for name in (lat, lon, depth)):
            raise ProviderDataError("INVALID_COORDINATES")
        return lat, lon, depth

    @staticmethod
    def _same_horizontal_grid(current: xr.Dataset, temperature: xr.Dataset, current_coordinates: tuple[str, str, str], temperature_coordinates: tuple[str, str, str]) -> bool:
        current_lat, current_lon, _ = current_coordinates
        temperature_lat, temperature_lon, _ = temperature_coordinates
        return (
            np.array_equal(current.coords[current_lat].values, temperature.coords[temperature_lat].values)
            and np.array_equal(current.coords[current_lon].values, temperature.coords[temperature_lon].values)
        )

    @classmethod
    def _select(cls, cur: xr.Dataset, temp: xr.Dataset, current_coordinates: tuple[str, str, str], temperature_coordinates: tuple[str, str, str], requested: GeographicPoint, radius_km: float) -> tuple[int, int, int, int, float | None] | None:
        lat, lon, depth = current_coordinates
        temperature_lat, temperature_lon, temperature_depth = temperature_coordinates
        latitudes, longitudes, depths = (np.asarray(cur.coords[name].values, dtype=float) for name in (lat, lon, depth))
        yy, xx = np.meshgrid(latitudes, longitudes, indexing="ij"); distances = cls._distance(requested.latitude, requested.longitude, yy, xx)
        direct_y, direct_x = np.unravel_index(np.argmin(distances), distances.shape)
        temperature_depths = np.asarray(temp.coords[temperature_depth].values, dtype=float)
        shared_depths = sorted(
            ((float(value), current_index, temperature_index)
             for current_index, value in enumerate(depths)
             for temperature_index, temperature_value in enumerate(temperature_depths)
             if np.isclose(value, temperature_value, rtol=0, atol=1e-6)),
            key=lambda item: item[0],
        )
        for _, current_depth_index, temperature_depth_index in shared_depths:
            valid = np.isfinite(cur.uo.isel({depth: current_depth_index}).values) & np.isfinite(cur.vo.isel({depth: current_depth_index}).values) & np.isfinite(temp.thetao.isel({temperature_depth: temperature_depth_index}).values)
            if not valid.any(): continue
            nearest = np.where(valid, distances, np.inf); y, x = np.unravel_index(np.argmin(nearest), nearest.shape)
            if nearest[y, x] <= radius_km:
                return int(current_depth_index), int(temperature_depth_index), int(y), int(x), (None if (y, x) == (direct_y, direct_x) else float(nearest[y, x]))
        return None

    @staticmethod
    def _distance(lat: float, lon: float, grid_lat: np.ndarray, grid_lon: np.ndarray) -> np.ndarray:
        dlat=np.radians(grid_lat-lat); dlon=np.radians((grid_lon-lon+180)%360-180); a=np.sin(dlat/2)**2+math.cos(math.radians(lat))*np.cos(np.radians(grid_lat))*np.sin(dlon/2)**2
        return 6371.0088*2*np.arctan2(np.sqrt(a),np.sqrt(1-a))

    @staticmethod
    def _celsius(value: float, units: object) -> float:
        if str(units).lower() in {"k", "kelvin"}: return value-273.15
        if str(units).lower() in {"c", "degc", "celsius", "degree_celsius"}: return value
        raise ProviderDataError("UNSUPPORTED_TEMPERATURE_UNITS")

    @staticmethod
    def _time(dataset: xr.Dataset) -> datetime:
        value = dataset.coords.get("time")
        if value is None: raise ProviderDataError("MISSING_OBSERVATION_TIME")
        raw=value.values.reshape(-1)[-1]
        return datetime.fromtimestamp(raw.astype("datetime64[s]").astype(int), UTC)

    @staticmethod
    def _longitude(value: float) -> float: return value-360 if value>180 else value

    def _unavailable(self, requested: GeographicPoint, radius: float, bounds: dict[str, float]) -> NormalizedEnvironmentalObservation:
        return NormalizedEnvironmentalObservation("ocean_conditions", ObservationStatus.UNAVAILABLE, None, self.clock().astimezone(UTC), ObservationProvenance("Copernicus Marine", PRODUCT_ID, "copernicusmarine", details={"requested_longitude": requested.longitude, "requested_latitude": requested.latitude, "max_fallback_distance_km": radius, "subset_bounds": bounds, "failure_code": "NO_VALID_CELL_WITHIN_FALLBACK_RADIUS"}), metadata={"failure_code": "NO_VALID_CELL_WITHIN_FALLBACK_RADIUS"})


assert isinstance(CopernicusMarineOceanAdapter(), EnvironmentalProviderAdapter)
