"""Startup-loaded, deterministic inference for the reviewed Phase 5F artifact."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


FEATURE_NAMES = (
    "current_x_m",
    "current_y_m",
    "previous_dx_m",
    "previous_dy_m",
    "previous_delta_longitude_deg",
    "day_of_year_sin",
    "day_of_year_cos",
)
TARGET_NAMES = ("dx_m", "dy_m")
ARTIFACT_SCHEMA_VERSION = 1


class ModelUnavailable(Exception):
    """The configured offline artifact cannot safely be used."""


@dataclass(frozen=True)
class IcebergRidgeModel:
    artifact_sha256: str
    feature_mean: tuple[float, ...]
    feature_scale: tuple[float, ...]
    target_mean: tuple[float, ...]
    coefficients: tuple[tuple[float, ...], ...]

    @classmethod
    def load(cls, configured_path: str | None) -> "IcebergRidgeModel":
        if not configured_path:
            raise ModelUnavailable("ARTIFACT_PATH_NOT_CONFIGURED")
        path = Path(configured_path)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ModelUnavailable("ARTIFACT_UNREADABLE") from exc
        try:
            if payload.get("artifact_schema_version") != ARTIFACT_SCHEMA_VERSION:
                raise ValueError("artifact schema")
            model = payload["model"]
            if model["model_type"] != "ridge_closed_form_standardized":
                raise ValueError("model type")
            if tuple(model["feature_names"]) != FEATURE_NAMES or tuple(model["target_names"]) != TARGET_NAMES:
                raise ValueError("feature or target contract")
            feature_mean = tuple(float(value) for value in model["feature_mean"])
            feature_scale = tuple(float(value) for value in model["feature_scale_train_only"])
            target_mean = tuple(float(value) for value in model["target_mean_train_only"])
            coefficients = tuple(tuple(float(value) for value in row) for row in model["coefficients"])
            if not (
                len(feature_mean) == len(feature_scale) == len(coefficients) == len(FEATURE_NAMES)
                and len(target_mean) == len(TARGET_NAMES)
                and all(len(row) == len(TARGET_NAMES) for row in coefficients)
                and all(math.isfinite(value) for values in (feature_mean, feature_scale, target_mean) for value in values)
                and all(math.isfinite(value) for row in coefficients for value in row)
                and all(value != 0 for value in feature_scale)
            ):
                raise ValueError("numeric dimensions")
        except (KeyError, TypeError, ValueError) as exc:
            raise ModelUnavailable("ARTIFACT_CONTRACT_INVALID") from exc
        return cls(
            artifact_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            feature_mean=feature_mean,
            feature_scale=feature_scale,
            target_mean=target_mean,
            coefficients=coefficients,
        )

    def predict(self, supplied_features: Mapping[str, float]) -> dict[str, float]:
        if set(supplied_features) != set(FEATURE_NAMES):
            raise ValueError("feature keys do not match the frozen Phase 5F contract")
        values = tuple(float(supplied_features[name]) for name in FEATURE_NAMES)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("feature values must be finite")
        predictions = tuple(
            self.target_mean[target_index] + sum(
                ((value - self.feature_mean[feature_index]) / self.feature_scale[feature_index])
                * self.coefficients[feature_index][target_index]
                for feature_index, value in enumerate(values)
            )
            for target_index in range(len(TARGET_NAMES))
        )
        if not all(math.isfinite(value) for value in predictions):
            raise ValueError("prediction is not finite")
        return dict(zip(TARGET_NAMES, predictions))


@dataclass(frozen=True)
class IcebergDemoModelService:
    model: IcebergRidgeModel | None
    unavailable_reason: str | None = None

    @classmethod
    def startup(cls, configured_path: str | None) -> "IcebergDemoModelService":
        try:
            return cls(IcebergRidgeModel.load(configured_path))
        except ModelUnavailable as exc:
            return cls(None, str(exc))

    @property
    def available(self) -> bool:
        return self.model is not None

    def predict(self, supplied_features: Mapping[str, float]) -> dict[str, float]:
        if self.model is None:
            raise ModelUnavailable(self.unavailable_reason or "MODEL_UNAVAILABLE")
        return self.model.predict(supplied_features)
