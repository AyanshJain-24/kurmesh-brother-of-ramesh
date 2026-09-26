"""Clean-load and reproduce Phase 5D test metrics without retraining."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from ml.preprocessing.contracts import ICEBERG_SPLIT
from ml.preprocessing.iceberg import build_iceberg_examples, parse_iceberg_rows
from ml.training.phase5d_baselines import (
    ICEBERG_FEATURES,
    RegressionMetrics,
    SEA_FEATURES,
    SeaIceBlockSource,
    StandardizedRidge,
)

TOLERANCE = 1e-12


def load_ridge(path: Path) -> StandardizedRidge:
    import numpy as np  # type: ignore[import-not-found]
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("artifact_schema_version") == 1 and "model" in payload:
        payload = payload["model"]
    required = {"model_type", "alpha", "feature_names", "target_names", "feature_mean", "feature_scale_train_only", "target_mean_train_only", "coefficients"}
    if set(payload) != required or payload["model_type"] != "ridge_closed_form_standardized":
        raise ValueError(f"unsupported artifact schema: {path}")
    feature_count = len(payload["feature_names"])
    target_count = len(payload["target_names"])
    if not (len(payload["feature_mean"]) == len(payload["feature_scale_train_only"]) == feature_count):
        raise ValueError("feature dimensions disagree")
    coefficients = np.asarray(payload["coefficients"], dtype=np.float64)
    if coefficients.shape != (feature_count, target_count):
        raise ValueError("coefficient dimensions disagree")
    return StandardizedRidge(
        float(payload["alpha"]),
        np.asarray(payload["feature_mean"], dtype=np.float64),
        np.asarray(payload["feature_scale_train_only"], dtype=np.float64),
        np.asarray(payload["target_mean_train_only"], dtype=np.float64),
        coefficients,
    )


def _artifact_info(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("artifact_schema_version") == 1 and "model" in payload:
        payload = payload["model"]
    return {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "model_type": payload["model_type"],
        "feature_count": len(payload["feature_names"]),
        "target_count": len(payload["target_names"]),
        "feature_names": payload["feature_names"],
        "target_names": payload["target_names"],
    }


def review_sea_ice(path: Path, data_dir: Path, max_blocks: int | None = None) -> dict[str, Any]:
    model = load_ridge(path)
    if _artifact_info(path)["feature_names"] != SEA_FEATURES:
        raise ValueError("sea-ice feature order differs from Phase 5D contract")
    ridge, persistence = RegressionMetrics(1), RegressionMetrics(1)
    blocks = 0
    for split, _, features, target, baseline in SeaIceBlockSource(data_dir).blocks():
        if split != "test":
            continue
        ridge.add(model.predict(features), target)
        persistence.add(baseline, target)
        blocks += 1
        if max_blocks is not None and blocks >= max_blocks:
            break
    return {
        "artifact": _artifact_info(path),
        "test_blocks": blocks,
        "ridge": ridge.result(["sic"]),
        "persistence": persistence.result(["sic"]),
    }


def review_iceberg(path: Path, stats_directory: Path, max_examples: int | None = None) -> dict[str, Any]:
    import numpy as np  # type: ignore[import-not-found]
    from pyproj import Transformer  # type: ignore[import-not-found]
    model = load_ridge(path)
    if _artifact_info(path)["feature_names"] != ICEBERG_FEATURES:
        raise ValueError("iceberg feature order differs from Phase 5D contract")
    projector = Transformer.from_crs("EPSG:4326", "EPSG:3412", always_xy=True).transform
    observations: list[Any] = []
    for csv_path in sorted(stats_directory.glob("*.csv")):
        with csv_path.open(newline="", encoding="utf-8") as source:
            observations.extend(parse_iceberg_rows(csv_path.stem, csv.DictReader(source)).observations)
    examples = [item for item in build_iceberg_examples(observations, ICEBERG_SPLIT, projector) if item.split == "test"]
    if max_examples is not None:
        examples = examples[:max_examples]
    features = np.asarray([[item.features[name] for name in ICEBERG_FEATURES] for item in examples], dtype=np.float64)
    target = np.asarray([[item.target_dx_m, item.target_dy_m] for item in examples], dtype=np.float64)
    ridge, baseline = RegressionMetrics(2), RegressionMetrics(2)
    ridge.add(model.predict(features), target)
    baseline.add(features[:, [2, 3]], target)
    return {"artifact": _artifact_info(path), "test_examples": len(examples), "ridge": ridge.result(["dx_m", "dy_m"]), "constant_velocity": baseline.result(["dx_m", "dy_m"])}


def _matches(actual: dict[str, Any], expected: dict[str, Any]) -> dict[str, float]:
    differences: dict[str, float] = {}
    for name, expected_value in expected.items():
        if isinstance(expected_value, dict):
            differences.update({f"{name}.{key}": value for key, value in _matches(actual[name], expected_value).items()})
        elif isinstance(expected_value, (int, float)):
            differences[name] = abs(actual[name] - expected_value)
    return differences


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sea-artifact", type=Path, required=True)
    parser.add_argument("--iceberg-artifact", type=Path, required=True)
    parser.add_argument("--sea-ice-dir", type=Path, required=True)
    parser.add_argument("--iceberg-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--dependency-path", type=Path, action="append", default=[])
    arguments = parser.parse_args()
    for dependency in arguments.dependency_path:
        sys.path.insert(0, str(dependency))
    sea_smoke = review_sea_ice(arguments.sea_artifact, arguments.sea_ice_dir, max_blocks=3)
    iceberg_smoke = review_iceberg(arguments.iceberg_artifact, arguments.iceberg_dir, max_examples=1000)
    sea_full = review_sea_ice(arguments.sea_artifact, arguments.sea_ice_dir)
    iceberg_full = review_iceberg(arguments.iceberg_artifact, arguments.iceberg_dir)
    expected = {
        "sea_ice": {"persistence": {"sample_count": 3791025, "mae": {"sic": 0.06331805778120693}, "rmse": {"sic": 0.1079545905849875}}, "ridge": {"sample_count": 3791025, "mae": {"sic": 0.06895211807531806}, "rmse": {"sic": 0.10362172095374489}}},
        "iceberg": {"constant_velocity": {"sample_count": 59444, "mae": {"dx_m": 2642.7826390212936, "dy_m": 2255.9819571762728}, "rmse": {"dx_m": 25530.483635390694, "dy_m": 12432.674619459876}}, "ridge": {"sample_count": 59444, "mae": {"dx_m": 2393.0721207036186, "dy_m": 2385.7941482778724}, "rmse": {"dx_m": 16450.443795449744, "dy_m": 8742.112554870831}}},
    }
    actual = {"sea_ice": sea_full, "iceberg": iceberg_full}
    differences = _matches({"sea_ice": {"persistence": sea_full["persistence"], "ridge": sea_full["ridge"]}, "iceberg": {"constant_velocity": iceberg_full["constant_velocity"], "ridge": iceberg_full["ridge"]}}, expected)
    report = {"tolerance_absolute": TOLERANCE, "smoke": {"sea_ice": sea_smoke, "iceberg": iceberg_smoke}, "full": actual, "recorded_metric_absolute_differences": differences, "reproduced_within_tolerance": all(value <= TOLERANCE for value in differences.values())}
    arguments.report.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
