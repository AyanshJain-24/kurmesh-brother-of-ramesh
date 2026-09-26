"""Run the Phase 5F clean, offline portable-artifact verification.

The temporary bundle deliberately contains only the portable artifact JSON
files and their repository-relative provenance documents.  Real, validated
held-out examples are read separately for a prediction-only smoke test; the
original Phase 5D artifact directory is never an input to this program.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any


EXPECTED = {
    "sea_ice": {
        "artifact": "sea_ice_ridge.portable.json",
        "manifest": "phase5b_sea_ice_manifest.json",
        "features": [
            "sic_lag_0_days", "sic_lag_1_days", "sic_lag_2_days",
            "sic_lag_3_days", "sic_lag_7_days", "x_m", "y_m",
            "day_of_year_sin", "day_of_year_cos",
        ],
        "targets": ["sic_t_plus_7_days"],
        "alpha": 0.1,
    },
    "iceberg": {
        "artifact": "iceberg_ridge.portable.json",
        "manifest": "phase5b_iceberg_manifest.json",
        "features": [
            "current_x_m", "current_y_m", "previous_dx_m", "previous_dy_m",
            "previous_delta_longitude_deg", "day_of_year_sin", "day_of_year_cos",
        ],
        "targets": ["dx_m", "dy_m"],
        "alpha": 10.0,
    },
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _strings(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [item for child in value.values() for item in _strings(child)]
    if isinstance(value, list):
        return [item for child in value for item in _strings(child)]
    return [value] if isinstance(value, str) else []


def _has_secret_key(value: Any) -> bool:
    if isinstance(value, dict):
        return any(re.search(r"(?:password|secret|token|api[_-]?key|credential)", key, re.I) or _has_secret_key(item)
                   for key, item in value.items())
    if isinstance(value, list):
        return any(_has_secret_key(item) for item in value)
    return False


def _assert(condition: bool, label: str, result: dict[str, Any]) -> None:
    result["checks"][label] = "PASS" if condition else "FAIL"
    if not condition:
        raise ValueError(label)


def _copy_clean_bundle(source: Path, repository: Path, clean: Path) -> None:
    if clean.exists():
        raise FileExistsError(f"clean portability directory must not already exist: {clean}")
    for category, expected in EXPECTED.items():
        artifact = source / expected["artifact"]
        if not artifact.is_file():
            raise FileNotFoundError(artifact)
        destination = clean / "artifacts" / expected["artifact"]
        destination.parent.mkdir(parents=True, exist_ok=False) if not destination.parent.exists() else None
        shutil.copy2(artifact, destination)
        manifest = repository / "data" / "manifests" / expected["manifest"]
        destination_manifest = clean / "data" / "manifests" / expected["manifest"]
        destination_manifest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(manifest, destination_manifest)
    contract = repository / "docs" / "ml" / "PHASE_5C_PREPROCESSING.md"
    destination_contract = clean / "docs" / "ml" / contract.name
    destination_contract.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(contract, destination_contract)


def _load_and_validate(clean: Path, category: str, result: dict[str, Any]) -> Any:
    import numpy as np  # type: ignore[import-not-found]
    from ml.review.phase5e_artifact_review import load_ridge

    expected = EXPECTED[category]
    path = clean / "artifacts" / expected["artifact"]
    payload = json.loads(path.read_text(encoding="utf-8"))
    model, provenance = payload["model"], payload["provenance"]
    prefix = f"{category}."
    _assert(payload.get("artifact_schema_version") == 1, prefix + "artifact_schema", result)
    _assert(model["model_type"] == "ridge_closed_form_standardized", prefix + "model_type", result)
    _assert(model["feature_names"] == expected["features"], prefix + "feature_schema", result)
    _assert(model["target_names"] == expected["targets"], prefix + "target_schema", result)
    _assert(model["alpha"] == expected["alpha"], prefix + "hyperparameters", result)
    _assert(len(model["coefficients"]) == len(expected["features"]), prefix + "feature_count", result)
    _assert(all(len(row) == len(expected["targets"]) for row in model["coefficients"]), prefix + "target_dimensions", result)
    _assert(all(np.isfinite(value) for row in model["coefficients"] for value in row), prefix + "finite_parameters", result)
    manifest = clean / provenance["dataset"]["manifest_repository_path"]
    _assert(manifest.is_file(), prefix + "manifest_resolves", result)
    _assert(_sha256(manifest) == provenance["dataset"]["manifest_sha256"], prefix + "manifest_sha256", result)
    contract = clean / provenance["preprocessing_contract"]["repository_path"]
    _assert(contract.is_file(), prefix + "preprocessing_contract_resolves", result)
    strings = _strings(payload)
    _assert(not any("%temp%" in value.lower() or re.match(r"^[a-zA-Z]:[\\/]", value) or "\\users\\" in value.lower() for value in strings), prefix + "no_local_paths", result)
    _assert(not any(value.lower().endswith((".nc", ".csv", ".zip")) for value in strings), prefix + "no_raw_dataset_embedded", result)
    _assert(not _has_secret_key(payload), prefix + "no_secrets", result)
    loaded = load_ridge(path)
    _assert(loaded.coefficients.shape == (len(expected["features"]), len(expected["targets"])), prefix + "deserializes", result)
    result["artifacts"][category] = {"path": str(path), "sha256": _sha256(path), "model_type": model["model_type"]}
    return loaded


def _smoke_sea(model: Any, data_directory: Path, result: dict[str, Any]) -> None:
    import numpy as np  # type: ignore[import-not-found]
    from ml.training.phase5d_baselines import SeaIceBlockSource

    for split, target_date, features, target, _ in SeaIceBlockSource(data_directory).blocks():
        if split == "test":
            prediction = model.predict(features[:16])
            _assert(prediction.shape == target[:16].shape and bool(np.isfinite(prediction).all()), "sea_ice.deterministic_held_out_inference", result)
            result["smoke_tests"]["sea_ice"] = {"target_date": target_date.isoformat(), "sample_count": 16, "prediction_shape": list(prediction.shape)}
            return
    raise ValueError("sea_ice held-out examples unavailable")


def _smoke_iceberg(model: Any, stats_directory: Path, result: dict[str, Any]) -> None:
    import numpy as np  # type: ignore[import-not-found]
    from pyproj import Transformer  # type: ignore[import-not-found]
    from ml.preprocessing.contracts import ICEBERG_SPLIT
    from ml.preprocessing.iceberg import build_iceberg_examples, parse_iceberg_rows

    projector = Transformer.from_crs("EPSG:4326", "EPSG:3412", always_xy=True).transform
    for csv_path in sorted(stats_directory.glob("*.csv")):
        with csv_path.open(newline="", encoding="utf-8") as source:
            examples = build_iceberg_examples(parse_iceberg_rows(csv_path.stem, csv.DictReader(source)).observations, ICEBERG_SPLIT, projector)
        test = next((example for example in examples if example.split == "test"), None)
        if test is not None:
            features = np.asarray([[test.features[name] for name in EXPECTED["iceberg"]["features"]]], dtype=np.float64)
            prediction = model.predict(features)
            _assert(prediction.shape == (1, 2) and bool(np.isfinite(prediction).all()), "iceberg.deterministic_held_out_inference", result)
            result["smoke_tests"]["iceberg"] = {"track_id": test.track_id, "target_date": test.target_date.isoformat(), "sample_count": 1, "prediction_shape": list(prediction.shape)}
            return
    raise ValueError("iceberg held-out examples unavailable")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--portable-source", type=Path, required=True)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--clean-directory", type=Path, required=True)
    parser.add_argument("--sea-ice-dir", type=Path, required=True)
    parser.add_argument("--iceberg-dir", type=Path, required=True)
    parser.add_argument("--dependency-path", type=Path, action="append", default=[])
    arguments = parser.parse_args()
    for dependency in arguments.dependency_path:
        sys.path.insert(0, str(dependency))
    result: dict[str, Any] = {"checks": {}, "artifacts": {}, "smoke_tests": {}}
    _copy_clean_bundle(arguments.portable_source, arguments.repository_root, arguments.clean_directory)
    sea = _load_and_validate(arguments.clean_directory, "sea_ice", result)
    iceberg = _load_and_validate(arguments.clean_directory, "iceberg", result)
    _smoke_sea(sea, arguments.sea_ice_dir, result)
    _smoke_iceberg(iceberg, arguments.iceberg_dir, result)
    result["original_phase5d_artifact_directory_required"] = False
    result["status"] = "PASS"
    report = arguments.clean_directory / "portability_report.json"
    report.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
