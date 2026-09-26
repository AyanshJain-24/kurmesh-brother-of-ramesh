"""Acquire and validate the frozen G02202 V6 daily subset outside Git.

This is a pre-training validator, not a training-data writer. It downloads only
the 2021--2024 Antarctic daily objects to a caller-selected local directory,
emits a metadata-only local manifest, and calculates example eligibility using
the same Phase 5C strict policy. It never serializes a feature table or model.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ml.preprocessing.contracts import SEA_ICE_HORIZON_DAYS, SEA_ICE_LAGS_DAYS, SEA_ICE_SPLIT

BASE_URL = "https://noaadata.apps.nsidc.org/NOAA/G02202_V6/south/daily"
REQUIRED_FIELDS = (
    "cdr_seaice_conc",
    "cdr_seaice_conc_qa_flag",
    "cdr_seaice_conc_interp_spatial_flag",
    "cdr_seaice_conc_interp_temporal_flag",
    "surface_type_mask",
    "x",
    "y",
    "time",
    "crs",
)
REASON_NAMES = {
    0: "eligible",
    1: "fill_value",
    2: "out_of_documented_range",
    3: "qa_flag",
    4: "spatial_interpolation_flag",
    5: "temporal_interpolation_flag",
    6: "surface_type_mask",
}


def _h5py() -> Any:
    try:
        import h5py  # type: ignore[import-not-found]
        import numpy as np  # type: ignore[import-not-found]
    except ImportError as error:
        raise RuntimeError(
            "This validator requires h5py and numpy supplied outside the repository. "
            "Use --h5py-path with the local dependency directory."
        ) from error
    return h5py, np


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _date_range(start: date, end: date) -> list[date]:
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def _url_for(day: date) -> str:
    # F17 is the documented filename platform token for this frozen 2021--2024
    # interval. A request failure is reported as missing, never substituted.
    filename = f"sic_pss25_{day:%Y%m%d}_F17_v06r00.nc"
    return f"{BASE_URL}/{day:%Y}/{filename}"


def _dataset(file: Any, name: str) -> Any:
    if name in file:
        return file[name]
    matches: list[Any] = []
    file.visititems(lambda path, item: matches.append(item) if path.rsplit("/", 1)[-1] == name else None)
    if len(matches) != 1:
        raise KeyError(f"required field {name!r} is absent or ambiguous")
    return matches[0]


def _scalar_attr(dataset: Any, name: str, default: Any = None) -> Any:
    value = dataset.attrs.get(name, default)
    if hasattr(value, "size") and value.size == 1:
        value = value.item()
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return value


def _text_attrs(dataset: Any) -> str:
    values = []
    for value in dataset.attrs.values():
        if isinstance(value, bytes):
            values.append(value.decode("utf-8", errors="replace"))
        elif isinstance(value, str):
            values.append(value)
    return " ".join(values)


def _download(url: str, destination: Path) -> tuple[bool, str | None]:
    if destination.exists():
        return True, None
    partial = destination.with_suffix(destination.suffix + ".part")
    request = Request(url, headers={"User-Agent": "KURMESH-Phase5C1-validation/1.0"})
    try:
        with urlopen(request, timeout=90) as response, partial.open("wb") as output:
            if response.status != 200:
                return False, f"HTTP {response.status}"
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
        # Windows Defender may briefly scan a newly closed NetCDF object.
        for attempt in range(10):
            try:
                partial.replace(destination)
                return True, None
            except PermissionError:
                if attempt == 9:
                    raise
                time.sleep(0.5)
    except HTTPError as error:
        try:
            partial.unlink(missing_ok=True)
        except PermissionError:
            pass
        return False, f"HTTP {error.code}"
    except (URLError, TimeoutError, OSError) as error:
        # A concurrent security scan can move the completed file just before
        # pathlib observes the rename. Treat it as success only when the final
        # filename now exists; it will still undergo full NetCDF validation.
        if destination.exists():
            return True, None
        try:
            partial.unlink(missing_ok=True)
        except PermissionError:
            pass
        return False, f"{type(error).__name__}: {error}"


@dataclass
class FileResult:
    day: date
    url: str
    path: Path
    sha256: str
    reason_codes: Any
    metadata: dict[str, Any]


def _inspect_file(day: date, url: str, path: Path, baseline: dict[str, Any] | None) -> FileResult:
    h5py, np = _h5py()
    with h5py.File(path, "r") as file:
        datasets = {name: _dataset(file, name) for name in REQUIRED_FIELDS}
        concentration = datasets["cdr_seaice_conc"]
        raw = np.asarray(concentration[()]).squeeze()
        qa = np.asarray(datasets["cdr_seaice_conc_qa_flag"][()]).squeeze()
        spatial = np.asarray(datasets["cdr_seaice_conc_interp_spatial_flag"][()]).squeeze()
        temporal = np.asarray(datasets["cdr_seaice_conc_interp_temporal_flag"][()]).squeeze()
        surface = np.asarray(datasets["surface_type_mask"][()]).squeeze()
        x = np.asarray(datasets["x"][()])
        y = np.asarray(datasets["y"][()])
        time_values = np.asarray(datasets["time"][()]).reshape(-1)

        if raw.shape != (332, 316) or any(array.shape != raw.shape for array in (qa, spatial, temporal, surface)):
            raise ValueError(f"unexpected data shape: concentration={raw.shape}")
        fill_value = int(_scalar_attr(concentration, "_FillValue"))
        scale_factor = float(_scalar_attr(concentration, "scale_factor"))
        units = _scalar_attr(concentration, "units")
        valid_range = [int(value) for value in _scalar_attr(concentration, "valid_range")]
        if fill_value != 255 or scale_factor != 0.01 or units != "1" or valid_range != [0, 100]:
            raise ValueError("concentration decoding metadata differs from the Phase 5B contract")
        if time_values.size != 1:
            raise ValueError(f"expected one daily timestamp, found {time_values.size}")
        time_units = _scalar_attr(datasets["time"], "units")
        if time_units != "days since 1970-01-01":
            raise ValueError(f"unexpected time units: {time_units!r}")
        decoded_day = date(1970, 1, 1) + timedelta(days=int(time_values[0]))
        if decoded_day != day:
            raise ValueError(f"filename date {day} disagrees with NetCDF time {decoded_day}")
        crs_text = _text_attrs(datasets["crs"])
        if "3412" not in crs_text:
            raise ValueError("EPSG:3412 marker missing from CRS metadata")

        x_hash = hashlib.sha256(x.tobytes()).hexdigest()
        y_hash = hashlib.sha256(y.tobytes()).hexdigest()
        grid = {"shape": list(raw.shape), "x_sha256": x_hash, "y_sha256": y_hash, "crs_text": crs_text}
        if baseline is not None and grid != baseline:
            raise ValueError("grid metadata differs from the first validated file")

        reason_codes = np.zeros(raw.shape, dtype=np.uint8)
        # This ordering mirrors SeaIceCellRecord.exclusion_reason exactly.
        reason_codes[raw == fill_value] = 1
        reason_codes[(reason_codes == 0) & ((raw < 0) | (raw > 100))] = 2
        reason_codes[(reason_codes == 0) & (qa != 0)] = 3
        reason_codes[(reason_codes == 0) & (spatial != 0)] = 4
        reason_codes[(reason_codes == 0) & (temporal != 0)] = 5
        reason_codes[(reason_codes == 0) & (surface != 50)] = 6

        metadata = {
            "date": day.isoformat(),
            "url": url,
            "file_size_bytes": path.stat().st_size,
            "sha256": _sha256(path),
            "netcdf_time_days_since_1970_01_01": int(time_values[0]),
            "valid_sic_cells": int(np.count_nonzero((raw >= 0) & (raw <= 100))),
            "fill_cells": int(np.count_nonzero(raw == fill_value)),
            "reason_counts": {REASON_NAMES[key]: int(value) for key, value in enumerate(np.bincount(reason_codes.ravel(), minlength=7))},
            "qa_flag_distribution": {str(key): int(value) for key, value in zip(*np.unique(qa, return_counts=True))},
            "spatial_interpolation_distribution": {str(key): int(value) for key, value in zip(*np.unique(spatial, return_counts=True))},
            "temporal_interpolation_distribution": {str(key): int(value) for key, value in zip(*np.unique(temporal, return_counts=True))},
            "surface_type_mask_distribution": {str(key): int(value) for key, value in zip(*np.unique(surface, return_counts=True))},
        }
    return FileResult(day, url, path, metadata["sha256"], reason_codes, metadata)


def _dry_run(results: dict[date, FileResult]) -> dict[str, Any]:
    _, np = _h5py()
    counts = Counter()
    rejections = Counter()
    candidate_dates: list[str] = []
    valid_dates: list[str] = []
    for issue_day in sorted(results):
        target_day = issue_day + timedelta(days=SEA_ICE_HORIZON_DAYS)
        feature_days = tuple(issue_day - timedelta(days=lag) for lag in SEA_ICE_LAGS_DAYS)
        if not SEA_ICE_SPLIT.accepts_example(target_day, feature_days):
            continue
        required_days = (*feature_days, target_day)
        if any(day not in results for day in required_days):
            rejections["missing_required_file"] += 104_912
            continue
        candidate_dates.append(target_day.isoformat())
        first_reason = np.zeros((332, 316), dtype=np.uint8)
        for required_day in required_days:
            daily_reason = results[required_day].reason_codes
            first_reason[(first_reason == 0) & (daily_reason != 0)] = daily_reason[(first_reason == 0) & (daily_reason != 0)]
        split = SEA_ICE_SPLIT.classify(target_day)
        valid = int(np.count_nonzero(first_reason == 0))
        counts[f"{split}_candidates"] += int(first_reason.size)
        counts[f"{split}_valid_examples"] += valid
        counts["candidate_cells"] += int(first_reason.size)
        counts["valid_examples"] += valid
        for code, amount in enumerate(np.bincount(first_reason.ravel(), minlength=7)):
            if code:
                rejections[REASON_NAMES[code]] += int(amount)
        if valid:
            valid_dates.append(target_day.isoformat())
    return {
        "candidate_target_date_count": len(candidate_dates),
        "candidate_target_date_first_last": [candidate_dates[0], candidate_dates[-1]] if candidate_dates else None,
        "target_dates_with_any_valid_example": len(valid_dates),
        "valid_target_date_first_last": [valid_dates[0], valid_dates[-1]] if valid_dates else None,
        "feature_count": 9,
        "feature_shape_per_example": [9],
        "target_shape_per_example": [],
        "counts": dict(counts),
        "rejections": dict(rejections),
    }


def run(
    download_dir: Path,
    manifest_path: Path,
    start: date = date(2021, 1, 1),
    end: date = date(2024, 12, 31),
    download_workers: int = 1,
) -> dict[str, Any]:
    download_dir.mkdir(parents=True, exist_ok=True)
    missing: dict[str, str] = {}
    malformed: dict[str, str] = {}
    files: list[dict[str, Any]] = []
    results: dict[date, FileResult] = {}
    baseline_grid: dict[str, Any] | None = None
    aggregate_flags: dict[str, Counter[str]] = {"qa": Counter(), "spatial": Counter(), "temporal": Counter(), "surface": Counter()}

    requested = _date_range(start, end)
    download_jobs = [(day, _url_for(day), download_dir / f"sic_pss25_{day:%Y%m%d}_F17_v06r00.nc") for day in requested]
    # Resume existing complete files and parallelize only independent network
    # requests. Inspection remains deterministic and sorted by calendar date.
    with ThreadPoolExecutor(max_workers=download_workers) as executor:
        downloaded = list(executor.map(lambda job: (*job, *_download(job[1], job[2])), download_jobs))

    for day, url, destination, success, error in downloaded:
        if not success:
            missing[day.isoformat()] = error or "download failed"
            continue
        try:
            result = _inspect_file(day, url, destination, baseline_grid)
            if baseline_grid is None:
                baseline_grid = {
                    "shape": [332, 316],
                    "x_sha256": _sha256_grid(destination, "x"),
                    "y_sha256": _sha256_grid(destination, "y"),
                    "crs_text": _crs_text(destination),
                }
        except (OSError, KeyError, ValueError, RuntimeError) as error:
            malformed[day.isoformat()] = f"{type(error).__name__}: {error}"
            continue
        results[day] = result
        files.append(result.metadata)
        for target, source in (("qa", "qa_flag_distribution"), ("spatial", "spatial_interpolation_distribution"), ("temporal", "temporal_interpolation_distribution"), ("surface", "surface_type_mask_distribution")):
            aggregate_flags[target].update(result.metadata[source])

    manifest = {
        "manifest_version": 1,
        "purpose": "Local-only Phase 5C.1 full-corpus pre-training validation; raw NetCDF is not stored in Git.",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": {"id": "G02202", "version": "6", "hemisphere": "south", "base_url": BASE_URL},
        "requested_interval": [start.isoformat(), end.isoformat()],
        "eligibility_policy": {"qa_flag": [0], "spatial_interpolation_flag": [0], "temporal_interpolation_flag": [0], "surface_type_mask": [50]},
        "files_successfully_validated": len(files),
        "missing_dates": missing,
        "malformed_dates": malformed,
        "grid": baseline_grid,
        "aggregate_flag_distributions": {name: dict(values) for name, values in aggregate_flags.items()},
        "files": files,
        "dry_run": _dry_run(results),
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def _sha256_grid(path: Path, field: str) -> str:
    h5py, _ = _h5py()
    with h5py.File(path, "r") as file:
        return hashlib.sha256(_dataset(file, field)[()].tobytes()).hexdigest()


def _crs_text(path: Path) -> str:
    h5py, _ = _h5py()
    with h5py.File(path, "r") as file:
        return _text_attrs(_dataset(file, "crs"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--download-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--h5py-path", type=Path, help="Local directory containing h5py and numpy")
    parser.add_argument("--download-workers", type=int, default=1)
    arguments = parser.parse_args()
    if arguments.h5py_path:
        sys.path.insert(0, str(arguments.h5py_path))
    if arguments.download_workers < 1:
        parser.error("--download-workers must be positive")
    manifest = run(arguments.download_dir, arguments.manifest, download_workers=arguments.download_workers)
    print(json.dumps({
        "files_successfully_validated": manifest["files_successfully_validated"],
        "missing_dates": len(manifest["missing_dates"]),
        "malformed_dates": len(manifest["malformed_dates"]),
        "dry_run": manifest["dry_run"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
