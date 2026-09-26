"""NOAA/NSIDC G10016 Version 4 Antarctic daily sea-ice adapter.

This adapter downloads one requested daily NetCDF file only. It deliberately
does not persist data; callers must use the Phase 4A ingestion service.
"""

from __future__ import annotations

import hashlib
import math
import os
import tempfile
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import numpy as np
import xarray as xr
from pyproj import CRS, Transformer

from app.config import ProviderConfiguration
from app.environment.providers import (
    EnvironmentalDomain,
    EnvironmentalProviderAdapter,
    GeographicPoint,
    NormalizedEnvironmentalObservation,
    ObservationProvenance,
    ObservationStatus,
    ProviderFetchRequest,
    ProviderUnavailableError,
)


DATASET_ID = "G10016"
DATASET_VERSION = "4"
PROVIDER_NAME = "noaa_nsidc_g10016"
PRODUCT = (
    "NOAA/NSIDC NRT CDR Passive Microwave Sea Ice Concentration "
    "G10016 V4 Antarctic daily"
)
EXPECTED_CRS = CRS.from_epsg(3412)
SEA_ICE_VARIABLE = "cdr_seaice_conc"


class ProviderDownloadError(Exception):
    pass


class ProviderDataError(Exception):
    pass


class Downloader(Protocol):
    def download(self, url: str, timeout_seconds: int) -> bytes: ...


class HttpDownloader:
    """Small request boundary for future retries, caching, and observability."""

    def download(self, url: str, timeout_seconds: int) -> bytes:
        try:
            with urlopen(
                url,
                timeout=timeout_seconds,
            ) as response:  # noqa: S310 - endpoint is validated configuration
                return response.read()
        except HTTPError as exc:
            if exc.code == 404:
                raise ProviderDownloadError("FILE_NOT_FOUND") from exc
            raise ProviderDownloadError("HTTP_ERROR") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise ProviderDownloadError("NETWORK_ERROR") from exc


class NoaaNsidcG10016Adapter:
    name = PROVIDER_NAME
    supported_domains = frozenset({EnvironmentalDomain.SEA_ICE})

    def __init__(
        self,
        downloader: Downloader | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.downloader = downloader or HttpDownloader()
        self.clock = clock or (lambda: datetime.now(UTC))

    def fetch(
        self,
        request: ProviderFetchRequest,
        configuration: ProviderConfiguration,
    ) -> tuple[NormalizedEnvironmentalObservation, ...]:
        if request.domain is not EnvironmentalDomain.SEA_ICE:
            raise ProviderDataError("UNSUPPORTED_DOMAIN")

        if request.location is None or request.location.latitude >= 0:
            raise ProviderDataError("ANTARCTIC_LOCATION_REQUIRED")

        if configuration.endpoint is None:
            raise ProviderDataError("ENDPOINT_REQUIRED")

        endpoint = configuration.endpoint

        file_date, url, payload = self._download_latest(
            endpoint,
            configuration,
            request.observed_after,
        )

        return (
            self._parse(
                payload,
                url,
                file_date,
                request.location,
                configuration.freshness_hours,
                configuration.max_fallback_distance_km,
            ),
        )

    def _download_latest(
        self,
        endpoint: str,
        configuration: ProviderConfiguration,
        observed_after: datetime | None,
    ) -> tuple[date, str, bytes]:
        start = (observed_after or self.clock()).astimezone(UTC).date()

        last_error: ProviderDownloadError | None = None

        for offset in range(configuration.lookback_days + 1):
            candidate = start - timedelta(days=offset)
            url = self._file_url(endpoint, candidate)

            try:
                return (
                    candidate,
                    url,
                    self.downloader.download(
                        url,
                        configuration.timeout_seconds,
                    ),
                )
            except ProviderDownloadError as exc:
                last_error = exc

                if str(exc) != "FILE_NOT_FOUND":
                    raise

        raise ProviderUnavailableError("FILE_NOT_FOUND") from last_error

    @staticmethod
    def _file_url(endpoint: str, day: date) -> str:
        filename = f"sic_pss25_{day:%Y%m%d}_am2_icdr_v04r00.nc"

        return (
            f"{endpoint.rstrip('/')}"
            f"/south/daily/{day:%Y}/{filename}"
        )

    def _parse(
        self,
        payload: bytes,
        source_url: str,
        expected_day: date,
        request_location: GeographicPoint,
        freshness_hours: int,
        max_fallback_distance_km: float,
    ) -> NormalizedEnvironmentalObservation:
        if not payload:
            raise ProviderDataError("EMPTY_FILE")

        path = self._write_temporary_file(payload)

        try:
            with xr.open_dataset(
                path,
                engine="h5netcdf",
                decode_cf=True,
                mask_and_scale=True,
            ) as dataset:
                return self._normalized_from_dataset(
                    dataset,
                    source_url,
                    expected_day,
                    request_location,
                    freshness_hours,
                    max_fallback_distance_km,
                    hashlib.sha256(payload).hexdigest(),
                )

        except (OSError, ValueError, KeyError) as exc:
            raise ProviderDataError("MALFORMED_NETCDF") from exc

        finally:
            path.unlink(missing_ok=True)

    @staticmethod
    def _write_temporary_file(payload: bytes) -> Path:
        descriptor, name = tempfile.mkstemp(suffix=".nc")

        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)

        return Path(name)

    def _normalized_from_dataset(
        self,
        dataset: xr.Dataset,
        source_url: str,
        expected_day: date,
        request_location: GeographicPoint,
        freshness_hours: int,
        max_fallback_distance_km: float,
        checksum: str,
    ) -> NormalizedEnvironmentalObservation:
        if SEA_ICE_VARIABLE not in dataset:
            raise ProviderDataError("MISSING_SEA_ICE_VARIABLE")

        variable = dataset[SEA_ICE_VARIABLE]

        crs = self._extract_crs(dataset, variable)

        if crs != EXPECTED_CRS:
            raise ProviderDataError("UNEXPECTED_CRS")

        if "x" not in dataset or "y" not in dataset:
            raise ProviderDataError("MISSING_PROJECTED_COORDINATES")

        transformer = Transformer.from_crs(
            "EPSG:4326",
            EXPECTED_CRS,
            always_xy=True,
        )

        requested_x, requested_y = transformer.transform(
            request_location.longitude,
            request_location.latitude,
        )

        exact_selected = variable.sel(
            x=requested_x,
            y=requested_y,
            method="nearest",
        )

        if "time" in exact_selected.dims:
            exact_selected = exact_selected.isel(time=0)

        exact_concentration = float(exact_selected.values)
        selected = exact_selected
        fallback_used = False
        fallback_distance_km: float | None = None

        if math.isfinite(exact_concentration) and not 0 <= exact_concentration <= 1:
            raise ProviderDataError("INVALID_SEA_ICE_VALUE")

        if math.isfinite(exact_concentration):
            concentration = exact_concentration
        else:
            # A NaN/fill value is a missing satellite observation, not malformed
            # provider data. Search only the bounded local grid for a real value.
            fallback = self._nearest_valid_cell(
                variable, requested_x, requested_y, max_fallback_distance_km,
            )
            if fallback is None:
                return self._unavailable_observation(
                    source_url=source_url,
                    checksum=checksum,
                    request_location=request_location,
                    requested_x=requested_x,
                    requested_y=requested_y,
                    max_fallback_distance_km=max_fallback_distance_km,
                )
            selected, concentration, fallback_distance_km = fallback
            fallback_used = True

        selected_x = float(selected.coords["x"].values)
        selected_y = float(selected.coords["y"].values)

        inverse = Transformer.from_crs(
            EXPECTED_CRS,
            "EPSG:4326",
            always_xy=True,
        )

        longitude, latitude = inverse.transform(
            selected_x,
            selected_y,
        )

        location = GeographicPoint(
            longitude,
            latitude,
        )

        observed_at = self._observation_time(
            dataset,
            expected_day,
        )

        retrieved_at = self.clock().astimezone(UTC)

        status = (
            ObservationStatus.LIVE
            if retrieved_at - observed_at
            <= timedelta(hours=freshness_hours)
            else ObservationStatus.STALE
        )

        qa = self._selected_optional(
            dataset,
            "cdr_seaice_conc_qa_flag",
            selected_x,
            selected_y,
        )

        spatial_interpolated = self._selected_optional(
            dataset,
            "cdr_seaice_conc_interp_spatial_flag",
            selected_x,
            selected_y,
        )

        temporal_interpolated = self._selected_optional(
            dataset,
            "cdr_seaice_conc_interp_temporal_flag",
            selected_x,
            selected_y,
        )

        if (
            spatial_interpolated not in (None, 0)
            or temporal_interpolated not in (None, 0)
        ):
            status = ObservationStatus.DEGRADED
        if fallback_used:
            status = ObservationStatus.DEGRADED

        return NormalizedEnvironmentalObservation(
            observation_type="sea_ice_concentration",
            status=status,
            observed_at=observed_at,
            retrieved_at=retrieved_at,
            provenance=ObservationProvenance(
                provider="NOAA/NSIDC",
                product=PRODUCT,
                source_reference=source_url,
                checksum=f"sha256:{checksum}",
                details={
                    "dataset_id": DATASET_ID,
                    "dataset_version": DATASET_VERSION,
                    "hemisphere": "south",
                    "crs": "EPSG:3412",
                    "variable": SEA_ICE_VARIABLE,
                    "projected_x_m": selected_x,
                    "projected_y_m": selected_y,
                    "requested_longitude": request_location.longitude,
                    "requested_latitude": request_location.latitude,
                    "requested_projected_x_m": requested_x,
                    "requested_projected_y_m": requested_y,
                    "selected_projected_x_m": selected_x,
                    "selected_projected_y_m": selected_y,
                    "fallback_used": fallback_used,
                    "fallback_method": "nearest_valid_grid_cell" if fallback_used else "exact_nearest_grid_cell",
                    "fallback_distance_km": fallback_distance_km,
                    "max_fallback_distance_km": max_fallback_distance_km,
                    "qa_flag": qa,
                    "spatial_interpolation_flag": spatial_interpolated,
                    "temporal_interpolation_flag": temporal_interpolated,
                },
            ),
            value={"concentration": concentration},
            units=str(variable.attrs.get("units", "1")),
            location=location,
            quality="qa_flag_present" if qa is not None else None,
            resolution="25 km",
            metadata={
                "source_crs": "EPSG:3412",
                "grid_mapping": variable.attrs.get("grid_mapping"),
                "variable_long_name": variable.attrs.get("long_name"),
                "dataset_title": dataset.attrs.get("title"),
            },
        )

    @staticmethod
    def _nearest_valid_cell(
        variable: xr.DataArray,
        requested_x: float,
        requested_y: float,
        max_fallback_distance_km: float,
    ) -> tuple[xr.DataArray, float, float] | None:
        """Select the closest real value inside a bounded EPSG:3412 radius."""
        radius_m = max_fallback_distance_km * 1_000
        x_values = np.asarray(variable.coords["x"].values, dtype=float)
        y_values = np.asarray(variable.coords["y"].values, dtype=float)
        x_indexes = np.flatnonzero(np.abs(x_values - requested_x) <= radius_m)
        y_indexes = np.flatnonzero(np.abs(y_values - requested_y) <= radius_m)
        if x_indexes.size == 0 or y_indexes.size == 0:
            return None

        values = variable.isel(time=0) if "time" in variable.dims else variable
        local_values = np.asarray(values.isel(x=x_indexes, y=y_indexes).values, dtype=float)
        local_x, local_y = np.meshgrid(x_values[x_indexes], y_values[y_indexes])
        distances_m = np.hypot(local_x - requested_x, local_y - requested_y)
        valid = (
            np.isfinite(local_values)
            & (local_values >= 0)
            & (local_values <= 1)
            & (distances_m <= radius_m)
        )
        if not valid.any():
            return None

        candidate_distances = np.where(valid, distances_m, np.inf)
        minimum_distance_m = float(candidate_distances.min())
        # Projection round trips can make geometrically equal grid distances differ
        # by sub-micrometres. Treat those as a tie and choose the lowest projected
        # x, then lowest projected y, independent of array traversal order.
        tied = np.argwhere(
            valid
            & np.isclose(
                candidate_distances,
                minimum_distance_m,
                rtol=0,
                atol=1e-6,
            )
        )
        tie_order = np.lexsort((local_y[tied[:, 0], tied[:, 1]], local_x[tied[:, 0], tied[:, 1]]))
        y_index, x_index = tied[tie_order[0]]
        selected = values.isel(y=int(y_indexes[y_index]), x=int(x_indexes[x_index]))
        return selected, float(selected.values), float(candidate_distances[y_index, x_index] / 1_000)

    def _unavailable_observation(
        self,
        *,
        source_url: str,
        checksum: str,
        request_location: GeographicPoint,
        requested_x: float,
        requested_y: float,
        max_fallback_distance_km: float,
    ) -> NormalizedEnvironmentalObservation:
        return NormalizedEnvironmentalObservation(
            observation_type="sea_ice_concentration",
            status=ObservationStatus.UNAVAILABLE,
            observed_at=None,
            retrieved_at=self.clock().astimezone(UTC),
            provenance=ObservationProvenance(
                provider="NOAA/NSIDC",
                product=PRODUCT,
                source_reference=source_url,
                checksum=f"sha256:{checksum}",
                details={
                    "dataset_id": DATASET_ID,
                    "dataset_version": DATASET_VERSION,
                    "crs": "EPSG:3412",
                    "requested_longitude": request_location.longitude,
                    "requested_latitude": request_location.latitude,
                    "requested_projected_x_m": requested_x,
                    "requested_projected_y_m": requested_y,
                    "fallback_used": False,
                    "fallback_method": "nearest_valid_grid_cell",
                    "max_fallback_distance_km": max_fallback_distance_km,
                    "failure_code": "NO_VALID_CELL_WITHIN_FALLBACK_RADIUS",
                },
            ),
            metadata={"failure_code": "NO_VALID_CELL_WITHIN_FALLBACK_RADIUS"},
        )

    @staticmethod
    def _extract_crs(
        dataset: xr.Dataset,
        variable: xr.DataArray,
    ) -> CRS:
        mapping_name = variable.attrs.get(
            "grid_mapping",
            "crs",
        )

        if mapping_name not in dataset:
            raise ProviderDataError("MISSING_CRS")

        attributes = dataset[mapping_name].attrs

        # NOAA/NSIDC explicitly provides:
        # urn:ogc:def:crs:EPSG::3412
        srid = attributes.get("srid")

        if srid is not None:
            srid_text = str(srid)
            prefix = "urn:ogc:def:crs:EPSG::"

            if srid_text.startswith(prefix):
                try:
                    epsg_code = int(
                        srid_text[len(prefix):]
                    )
                    return CRS.from_epsg(epsg_code)
                except ValueError as exc:
                    raise ProviderDataError(
                        "INVALID_CRS"
                    ) from exc

        try:
            for attribute_name in (
                "crs_wkt",
                "spatial_ref",
            ):
                wkt = attributes.get(attribute_name)

                if wkt:
                    crs = CRS.from_wkt(str(wkt))

                    epsg_code = crs.to_epsg()

                    if epsg_code is not None:
                        return CRS.from_epsg(epsg_code)

                    return crs

            return CRS.from_cf(attributes)

        except Exception as exc:
            raise ProviderDataError("INVALID_CRS") from exc

    @staticmethod
    def _observation_time(
        dataset: xr.Dataset,
        expected_day: date,
    ) -> datetime:
        if "time" not in dataset or dataset["time"].size == 0:
            return datetime.combine(
                expected_day,
                datetime.min.time(),
                tzinfo=UTC,
            )

        value = dataset["time"].values.reshape(-1)[0]

        if isinstance(value, np.datetime64):
            return datetime.fromtimestamp(
                value.astype("datetime64[s]").astype(int),
                tz=UTC,
            )

        if hasattr(value, "item"):
            value = value.item()

        if isinstance(value, datetime):
            return value.replace(
                tzinfo=value.tzinfo or UTC,
            ).astimezone(UTC)

        raise ProviderDataError("INVALID_OBSERVATION_TIME")

    @staticmethod
    def _selected_optional(
        dataset: xr.Dataset,
        name: str,
        x: float,
        y: float,
    ) -> int | None:
        if name not in dataset:
            return None

        value = dataset[name].sel(
            x=x,
            y=y,
            method="nearest",
        )

        if "time" in value.dims:
            value = value.isel(time=0)

        return int(value.values)


assert isinstance(
    NoaaNsidcG10016Adapter(),
    EnvironmentalProviderAdapter,
)
