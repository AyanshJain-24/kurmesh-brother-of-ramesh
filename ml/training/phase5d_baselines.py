"""Train reproducible, CPU-only Phase 5D Ridge baselines from validated data.

The implementation is deliberately dependency-light: Ridge sufficient
statistics are accumulated from chronological train blocks, then validation
selects alpha. Test blocks are evaluated once after that selection. No feature
matrix, raw data, prediction set, or model output is written into the repo.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import sys
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from math import cos, pi, sin
from pathlib import Path
from statistics import median
from typing import Any, Iterable

from ml.preprocessing.contracts import ICEBERG_SPLIT, SEA_ICE_HORIZON_DAYS, SEA_ICE_LAGS_DAYS, SEA_ICE_SPLIT
from ml.preprocessing.iceberg import build_iceberg_examples, parse_iceberg_rows


def _np() -> Any:
    import numpy as np  # type: ignore[import-not-found]
    return np


@dataclass
class RidgeSufficientStatistics:
    feature_count: int
    target_count: int

    def __post_init__(self) -> None:
        np = _np()
        self.count = 0
        self.sum_x = np.zeros(self.feature_count, dtype=np.float64)
        self.sum_xx = np.zeros((self.feature_count, self.feature_count), dtype=np.float64)
        self.sum_y = np.zeros(self.target_count, dtype=np.float64)
        self.sum_xy = np.zeros((self.feature_count, self.target_count), dtype=np.float64)

    def add(self, features: Any, targets: Any) -> None:
        if len(features) == 0:
            return
        self.count += len(features)
        self.sum_x += features.sum(axis=0)
        self.sum_xx += features.T @ features
        self.sum_y += targets.sum(axis=0)
        self.sum_xy += features.T @ targets

    def fit(self, alpha: float) -> "StandardizedRidge":
        np = _np()
        if self.count == 0:
            raise ValueError("cannot fit without train examples")
        mean_x = self.sum_x / self.count
        mean_y = self.sum_y / self.count
        centered_xx = self.sum_xx - np.outer(self.sum_x, self.sum_x) / self.count
        centered_xy = self.sum_xy - np.outer(self.sum_x, self.sum_y) / self.count
        scale_x = np.sqrt(np.maximum(np.diag(centered_xx) / self.count, 0.0))
        scale_x[scale_x == 0] = 1.0
        standardized_xx = centered_xx / np.outer(scale_x, scale_x)
        standardized_xy = centered_xy / scale_x[:, None]
        coefficients = np.linalg.solve(standardized_xx + alpha * np.eye(self.feature_count), standardized_xy)
        return StandardizedRidge(alpha, mean_x, scale_x, mean_y, coefficients)


@dataclass(frozen=True)
class StandardizedRidge:
    alpha: float
    mean_x: Any
    scale_x: Any
    mean_y: Any
    coefficients: Any

    def predict(self, features: Any) -> Any:
        return self.mean_y + ((features - self.mean_x) / self.scale_x) @ self.coefficients

    def serializable(self, feature_names: list[str], target_names: list[str]) -> dict[str, Any]:
        return {
            "model_type": "ridge_closed_form_standardized",
            "alpha": self.alpha,
            "feature_names": feature_names,
            "target_names": target_names,
            "feature_mean": self.mean_x.tolist(),
            "feature_scale_train_only": self.scale_x.tolist(),
            "target_mean_train_only": self.mean_y.tolist(),
            "coefficients": self.coefficients.tolist(),
        }


@dataclass
class RegressionMetrics:
    target_count: int

    def __post_init__(self) -> None:
        np = _np()
        self.count = 0
        self.absolute = np.zeros(self.target_count, dtype=np.float64)
        self.squared = np.zeros(self.target_count, dtype=np.float64)
        self.signed = np.zeros(self.target_count, dtype=np.float64)
        self.magnitude_absolute = 0.0

    def add(self, prediction: Any, target: Any) -> None:
        np = _np()
        error = prediction - target
        self.count += len(target)
        self.absolute += np.abs(error).sum(axis=0)
        self.squared += (error**2).sum(axis=0)
        self.signed += error.sum(axis=0)
        if self.target_count == 2:
            self.magnitude_absolute += np.abs(np.linalg.norm(prediction, axis=1) - np.linalg.norm(target, axis=1)).sum()

    def result(self, target_names: list[str]) -> dict[str, Any]:
        np = _np()
        if self.count == 0:
            raise ValueError("cannot calculate metrics without examples")
        values = {
            "sample_count": self.count,
            "mae": dict(zip(target_names, (self.absolute / self.count).tolist())),
            "rmse": dict(zip(target_names, np.sqrt(self.squared / self.count).tolist())),
            "mean_signed_error": dict(zip(target_names, (self.signed / self.count).tolist())),
        }
        if self.target_count == 2:
            values["mean_absolute_displacement_magnitude_error"] = self.magnitude_absolute / self.count
        return values


SEA_FEATURES = ["sic_lag_0_days", "sic_lag_1_days", "sic_lag_2_days", "sic_lag_3_days", "sic_lag_7_days", "x_m", "y_m", "day_of_year_sin", "day_of_year_cos"]
ICEBERG_FEATURES = ["current_x_m", "current_y_m", "previous_dx_m", "previous_dy_m", "previous_delta_longitude_deg", "day_of_year_sin", "day_of_year_cos"]


class SeaIceBlockSource:
    """LRU-backed source of strictly eligible real sea-ice example blocks."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.cache: OrderedDict[date, tuple[Any, Any, Any, Any, Any]] = OrderedDict()
        self.x_grid: Any | None = None
        self.y_grid: Any | None = None

    def _path(self, day: date) -> Path:
        return self.data_dir / f"sic_pss25_{day:%Y%m%d}_F17_v06r00.nc"

    @staticmethod
    def _field(file: Any, name: str) -> Any:
        if name in file:
            return file[name]
        matches: list[Any] = []
        file.visititems(lambda path, item: matches.append(item) if path.rsplit("/", 1)[-1] == name else None)
        if len(matches) != 1:
            raise KeyError(f"required NetCDF field {name!r} is absent or ambiguous")
        return matches[0]

    def _load(self, day: date) -> tuple[Any, Any, Any, Any, Any]:
        np = _np()
        if day in self.cache:
            self.cache.move_to_end(day)
            return self.cache[day]
        path = self._path(day)
        if not path.exists():
            raise FileNotFoundError(path)
        import h5py  # type: ignore[import-not-found]
        with h5py.File(path, "r") as file:
            arrays = tuple(np.asarray(self._field(file, field)[()]).squeeze() for field in (
                "cdr_seaice_conc", "cdr_seaice_conc_qa_flag", "cdr_seaice_conc_interp_spatial_flag",
                "cdr_seaice_conc_interp_temporal_flag", "surface_type_mask",
            ))
            if self.x_grid is None:
                x, y = np.asarray(self._field(file, "x")[()]), np.asarray(self._field(file, "y")[()])
                self.x_grid = np.broadcast_to(x, (len(y), len(x))).ravel().astype(np.float64)
                self.y_grid = np.broadcast_to(y[:, None], (len(y), len(x))).ravel().astype(np.float64)
        self.cache[day] = arrays
        if len(self.cache) > 8:
            self.cache.popitem(last=False)
        return arrays

    @staticmethod
    def _eligible(arrays: tuple[Any, Any, Any, Any, Any]) -> Any:
        raw, qa, spatial, temporal, surface = arrays
        return (raw <= 100) & (raw != 255) & (qa == 0) & (spatial == 0) & (temporal == 0) & (surface == 50)

    def blocks(self) -> Iterable[tuple[str, date, Any, Any, Any]]:
        np = _np()
        for ordinal in range((date(2024, 12, 24) - date(2021, 1, 8)).days + 1):
            issue = date(2021, 1, 8) + timedelta(days=ordinal)
            target_date = issue + timedelta(days=SEA_ICE_HORIZON_DAYS)
            feature_dates = tuple(issue - timedelta(days=lag) for lag in SEA_ICE_LAGS_DAYS)
            if not SEA_ICE_SPLIT.accepts_example(target_date, feature_dates):
                continue
            arrays = [self._load(day) for day in (*feature_dates, target_date)]
            eligible = self._eligible(arrays[0]).copy()
            for array in arrays[1:]:
                eligible &= self._eligible(array)
            mask = eligible.ravel()
            if not mask.any():
                continue
            angle = 2 * pi * issue.timetuple().tm_yday / 365.25
            x = self.x_grid[mask]
            y = self.y_grid[mask]
            values = [(array[0].ravel()[mask].astype(np.float64) * 0.01) for array in arrays]
            features = np.column_stack([*values[:5], x, y, np.full(len(x), sin(angle)), np.full(len(x), cos(angle))])
            target = values[5][:, None]
            yield SEA_ICE_SPLIT.classify(target_date), target_date, features, target, values[0][:, None]


def _select_alpha(statistics: RidgeSufficientStatistics, validation_blocks: list[tuple[Any, Any]], alphas: tuple[float, ...]) -> tuple[StandardizedRidge, dict[str, float]]:
    scores: dict[str, float] = {}
    models = {alpha: statistics.fit(alpha) for alpha in alphas}
    for alpha, model in models.items():
        metric = RegressionMetrics(statistics.target_count)
        for features, target in validation_blocks:
            metric.add(model.predict(features), target)
        result = metric.result([f"target_{index}" for index in range(statistics.target_count)])
        scores[str(alpha)] = sum(result["mae"].values()) / statistics.target_count
    selected = min(alphas, key=lambda alpha: scores[str(alpha)])
    return models[selected], scores


def _write_artifact(directory: Path, name: str, payload: dict[str, Any], metadata: dict[str, Any]) -> dict[str, str]:
    directory.mkdir(parents=True, exist_ok=True)
    artifact = directory / f"{name}.json"
    artifact.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    metadata["artifact_sha256"] = digest
    metadata_path = directory / f"{name}.metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
    return {"artifact": str(artifact), "metadata": str(metadata_path), "sha256": digest}


def train_sea_ice(data_dir: Path, artifact_dir: Path) -> dict[str, Any]:
    import h5py  # type: ignore[import-not-found]
    statistics = RidgeSufficientStatistics(9, 1)
    validation_blocks: list[tuple[Any, Any]] = []
    source = SeaIceBlockSource(data_dir)
    counts: dict[str, int] = {"train": 0, "validation": 0, "test": 0}
    for split, _, features, target, _ in source.blocks():
        counts[split] += len(target)
        if split == "train":
            statistics.add(features, target)
        elif split == "validation":
            validation_blocks.append((features, target))
    model, validation_mae = _select_alpha(statistics, validation_blocks, (0.1, 1.0, 10.0))
    ridge_metrics = RegressionMetrics(1)
    persistence_metrics = RegressionMetrics(1)
    for split, _, features, target, persistence in SeaIceBlockSource(data_dir).blocks():
        if split == "test":
            ridge_metrics.add(model.predict(features), target)
            persistence_metrics.add(persistence, target)
    timestamp = datetime.now(timezone.utc).isoformat()
    metadata = {
        "dataset_id": "G02202_V6_south_2021_2024_strict_phase5c1",
        "dataset_manifest_reference": "%TEMP%/kurmesh-phase5c1/phase5c1_sea_ice_local_manifest.json",
        "feature_names": SEA_FEATURES,
        "target_definition": "same EPSG:3412 source-cell decoded SIC fraction at issue + 7 days",
        "horizon": "7 days",
        "quality_policy": {"qa_flag": 0, "spatial_interpolation_flag": 0, "temporal_interpolation_flag": 0, "surface_type_mask": 50, "fill_value": 255},
        "splits": {"train": "2021-01-15..2023-10-24", "validation": "2023-11-08..2024-05-28", "test": "2024-06-12..2024-12-31"},
        "sample_counts": counts,
        "hyperparameters": {"alphas_considered": [0.1, 1.0, 10.0], "selected_alpha": model.alpha},
        "library_versions": {"python": platform.python_version(), "numpy": _np().__version__, "h5py": h5py.__version__},
        "random_seed": None,
        "training_timestamp_utc": timestamp,
        "operational_status": "OFFLINE_EXPERIMENT_ONLY",
    }
    artifacts = _write_artifact(artifact_dir, "sea_ice_ridge", model.serializable(SEA_FEATURES, ["sic_t_plus_7_days"]), metadata)
    return {"counts": counts, "validation_mae_by_alpha": validation_mae, "persistence_test": persistence_metrics.result(["sic"]), "ridge_test": ridge_metrics.result(["sic"]), "artifacts": artifacts}


def train_iceberg(stats_directory: Path, artifact_dir: Path) -> dict[str, Any]:
    import numpy as np  # type: ignore[import-not-found]
    import pyproj  # type: ignore[import-not-found]
    from pyproj import Transformer  # type: ignore[import-not-found]
    projector = Transformer.from_crs("EPSG:4326", "EPSG:3412", always_xy=True).transform
    grouped: list[Any] = []
    for path in sorted(stats_directory.glob("*.csv")):
        with path.open(newline="", encoding="utf-8") as source:
            grouped.extend(parse_iceberg_rows(path.stem, csv.DictReader(source)).observations)
    examples = build_iceberg_examples(grouped, ICEBERG_SPLIT, projector)
    by_split: dict[str, list[Any]] = {"train": [], "validation": [], "test": []}
    for example in examples:
        by_split[example.split].append(example)
    def matrices(items: list[Any]) -> tuple[Any, Any, Any]:
        features = np.asarray([[item.features[name] for name in ICEBERG_FEATURES] for item in items], dtype=np.float64)
        target = np.asarray([[item.target_dx_m, item.target_dy_m] for item in items], dtype=np.float64)
        baseline = features[:, [2, 3]]
        return features, target, baseline
    train_x, train_y, _ = matrices(by_split["train"])
    validation_x, validation_y, _ = matrices(by_split["validation"])
    test_x, test_y, test_baseline = matrices(by_split["test"])
    statistics = RidgeSufficientStatistics(7, 2)
    statistics.add(train_x, train_y)
    model, validation_mae = _select_alpha(statistics, [(validation_x, validation_y)], (0.1, 1.0, 10.0))
    ridge_metric, baseline_metric = RegressionMetrics(2), RegressionMetrics(2)
    ridge_metric.add(model.predict(test_x), test_y)
    baseline_metric.add(test_baseline, test_y)
    timestamp = datetime.now(timezone.utc).isoformat()
    metadata = {
        "dataset_id": "BYU_NIC_Antarctic_Iceberg_Tracking_V3_phase5c1",
        "dataset_manifest_reference": "data/manifests/phase5b_iceberg_manifest.json",
        "feature_names": ICEBERG_FEATURES,
        "target_definition": "EPSG:3412 dx/dy from issue position to observed position at +24 hours",
        "horizon": "24 hours",
        "projection": "EPSG:4326 to EPSG:3412, always_xy=True",
        "splits": {"train": "1992-01-03..2011-05-02", "validation": "2011-05-06..2015-06-27", "test": "2015-07-01..2019-08-14"},
        "sample_counts": {name: len(items) for name, items in by_split.items()},
        "hyperparameters": {"alphas_considered": [0.1, 1.0, 10.0], "selected_alpha": model.alpha},
        "library_versions": {"python": platform.python_version(), "numpy": np.__version__, "pyproj": pyproj.__version__},
        "random_seed": None,
        "training_timestamp_utc": timestamp,
        "operational_status": "OFFLINE_EXPERIMENT_ONLY",
    }
    artifacts = _write_artifact(artifact_dir, "iceberg_ridge", model.serializable(ICEBERG_FEATURES, ["dx_m", "dy_m"]), metadata)
    return {"counts": {name: len(items) for name, items in by_split.items()}, "validation_mae_by_alpha": validation_mae, "constant_velocity_test": baseline_metric.result(["dx_m", "dy_m"]), "ridge_test": ridge_metric.result(["dx_m", "dy_m"]), "artifacts": artifacts}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sea-ice-dir", type=Path, required=True)
    parser.add_argument("--iceberg-dir", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--dependency-path", type=Path, action="append", default=[])
    arguments = parser.parse_args()
    for dependency in arguments.dependency_path:
        sys.path.insert(0, str(dependency))
    results = {"sea_ice": train_sea_ice(arguments.sea_ice_dir, arguments.artifact_dir), "iceberg": train_iceberg(arguments.iceberg_dir, arguments.artifact_dir)}
    arguments.report.write_text(json.dumps(results, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(results, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
