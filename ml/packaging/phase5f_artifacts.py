"""Wrap existing Phase 5D model JSON in immutable, repository-relative provenance.

The original model payload is copied as a JSON object without transformation.
No estimator is fitted, no raw dataset is embedded, and no production component
is used by this module.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ARTIFACT_SCHEMA_VERSION = 1


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _reject_local_path(value: Any) -> None:
    if isinstance(value, dict):
        for item in value.values():
            _reject_local_path(item)
    elif isinstance(value, list):
        for item in value:
            _reject_local_path(item)
    elif isinstance(value, str):
        lowered = value.lower()
        if "%temp%" in lowered or "\\users\\" in lowered or ":\\" in lowered:
            raise ValueError(f"machine-local path is forbidden in portable package: {value!r}")


def package_artifact(
    model_path: Path,
    legacy_metadata_path: Path,
    manifest_path: Path,
    manifest_repository_path: str,
    output_path: Path,
    preprocessing_contract_path: str,
    feature_schema_version: str,
    model_version: str,
) -> dict[str, Any]:
    """Create a deterministic envelope while preserving the exact model object."""
    model = _read_json(model_path)
    legacy = _read_json(legacy_metadata_path)
    manifest = _read_json(manifest_path)
    required_model = {"model_type", "alpha", "feature_names", "target_names", "feature_mean", "feature_scale_train_only", "target_mean_train_only", "coefficients"}
    if set(model) != required_model:
        raise ValueError("unexpected legacy model schema")
    if not manifest_repository_path.startswith("data/manifests/"):
        raise ValueError("manifest reference must be repository-relative")
    provenance = {
        "dataset": {
            "name": manifest["dataset"]["name"],
            "version": str(manifest["dataset"]["version"]),
            "product_type": manifest["dataset"].get("product_type", manifest["dataset"].get("format")),
            "manifest_repository_path": manifest_repository_path,
            "manifest_sha256": sha256_file(manifest_path),
        },
        "preprocessing_contract": {"repository_path": preprocessing_contract_path, "version": "phase5c-v1"},
        "feature_schema_version": feature_schema_version,
        "target_definition": legacy["target_definition"],
        "forecast_horizon": legacy["horizon"],
        "splits": legacy["splits"],
        "sample_counts": legacy["sample_counts"],
        "model_type": model["model_type"],
        "model_version": model_version,
        "hyperparameters": legacy["hyperparameters"],
        "library_versions": legacy["library_versions"],
        "random_seed": legacy["random_seed"],
        "training_timestamp_utc": legacy["training_timestamp_utc"],
        "operational_status": "OFFLINE_EXPERIMENT_ONLY",
    }
    package = {
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "package_type": "kurmesh_phase5_portable_model_package",
        "model": model,
        "provenance": provenance,
    }
    _reject_local_path(package)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(package, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "output_path": str(output_path),
        "package_sha256": sha256_file(output_path),
        "legacy_model_sha256": sha256_file(model_path),
        "manifest_sha256": provenance["dataset"]["manifest_sha256"],
        "model_parameters_preserved": package["model"] == model,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sea-model", type=Path, required=True)
    parser.add_argument("--sea-metadata", type=Path, required=True)
    parser.add_argument("--iceberg-model", type=Path, required=True)
    parser.add_argument("--iceberg-metadata", type=Path, required=True)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    arguments = parser.parse_args()
    root = arguments.repository_root
    results = {
        "sea_ice": package_artifact(
            arguments.sea_model, arguments.sea_metadata,
            root / "data/manifests/phase5b_sea_ice_manifest.json", "data/manifests/phase5b_sea_ice_manifest.json",
            arguments.output_directory / "sea_ice_ridge.portable.json", "docs/ml/PHASE_5C_PREPROCESSING.md",
            "phase5d-sea-ice-v1", "phase5d-ridge-v1",
        ),
        "iceberg": package_artifact(
            arguments.iceberg_model, arguments.iceberg_metadata,
            root / "data/manifests/phase5b_iceberg_manifest.json", "data/manifests/phase5b_iceberg_manifest.json",
            arguments.output_directory / "iceberg_ridge.portable.json", "docs/ml/PHASE_5C_PREPROCESSING.md",
            "phase5d-iceberg-v1", "phase5d-ridge-v1",
        ),
    }
    print(json.dumps(results, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
