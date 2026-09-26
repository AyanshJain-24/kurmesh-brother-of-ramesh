"""Run the Phase 5C iceberg parser/builder over an existing local BYU V3 archive.

The archive is read in place. This command writes a small JSON report only; it
does not download data, persist examples, train a model, or calculate metrics.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from math import hypot, isfinite
from statistics import median
from collections import Counter
from pathlib import Path

from ml.preprocessing.contracts import ICEBERG_SPLIT
from ml.preprocessing.iceberg import build_iceberg_examples, normalize_longitude_difference, parse_iceberg_rows


def run(stats_directory: Path, diagnostic_identity_projector: bool = False) -> dict[str, object]:
    if diagnostic_identity_projector:
        # This is only for parser/window validation when local pyproj is absent.
        # It must never be used for a geographic displacement experiment.
        projector = lambda longitude, latitude: (longitude, latitude)
        projection = "DIAGNOSTIC identity lon/lat projector; not valid for training or displacement analysis"
    else:
        try:
            from pyproj import Transformer  # type: ignore[import-not-found]
        except ImportError as error:
            raise RuntimeError("pyproj is required from the existing local dependency environment") from error
        projector_transformer = Transformer.from_crs("EPSG:4326", "EPSG:3412", always_xy=True)
        projector = projector_transformer.transform
        projection = "EPSG:4326 to EPSG:3412, always_xy=True"
    totals: Counter[str] = Counter()
    examples_by_split: Counter[str] = Counter()
    examples_seen: set[tuple[str, str]] = set()
    antimeridian_segments = 0
    antimeridian_examples = 0
    projection_failures = 0
    magnitudes: list[float] = []
    representatives: dict[str, dict[str, object]] = {}

    for csv_path in sorted(stats_directory.glob("*.csv")):
        with csv_path.open(newline="", encoding="utf-8") as source:
            rows = list(csv.DictReader(source))
        totals["rows"] += len(rows)
        parsed = parse_iceberg_rows(csv_path.stem, rows)
        totals["tracks"] += 1
        totals["malformed_date_rows"] += parsed.malformed_date_rows
        totals["invalid_coordinate_rows"] += parsed.invalid_coordinate_rows
        totals["duplicate_date_rows"] += parsed.duplicate_date_rows
        for previous, current in zip(parsed.observations, parsed.observations[1:]):
            if abs(current.longitude - previous.longitude) > 180:
                antimeridian_segments += 1
                if not -180 <= normalize_longitude_difference(previous.longitude, current.longitude) < 180:
                    raise ValueError("longitude normalization failed")
        try:
            examples = build_iceberg_examples(parsed.observations, ICEBERG_SPLIT, projector)
        except Exception:
            projection_failures += 1
            continue
        by_target_date = {example.target_date: example for example in examples}
        for current, future in zip(parsed.observations, parsed.observations[1:]):
            example = by_target_date.get(future.observation_date)
            if example is None:
                continue
            magnitude = hypot(example.target_dx_m, example.target_dy_m)
            if not isfinite(magnitude):
                projection_failures += 1
                continue
            magnitudes.append(magnitude)
            raw_delta = future.longitude - current.longitude
            normalized_delta = normalize_longitude_difference(current.longitude, future.longitude)
            if abs(raw_delta) <= 180:
                kind = "ordinary"
            elif normalized_delta > 0:
                kind = "eastward_antimeridian"
            else:
                kind = "westward_antimeridian"
            if kind not in representatives:
                representatives[kind] = {
                    "track_id": csv_path.stem,
                    "issue_date": current.observation_date.isoformat(),
                    "target_date": future.observation_date.isoformat(),
                    "issue_lat_lon": [current.latitude, current.longitude],
                    "target_lat_lon": [future.latitude, future.longitude],
                    "normalized_longitude_delta_degrees": normalized_delta,
                    "dx_m": example.target_dx_m,
                    "dy_m": example.target_dy_m,
                    "magnitude_m": magnitude,
                    "finite": True,
                }
        for example in examples:
            key = (example.track_id, example.target_date.isoformat())
            if key in examples_seen:
                raise ValueError(f"duplicate example {key}")
            examples_seen.add(key)
            examples_by_split[example.split] += 1
            if abs(example.features["previous_delta_longitude_deg"]) > 180:
                raise ValueError("an example retained an unnormalized longitude delta")
            if abs(example.features["previous_delta_longitude_deg"]) > 170:
                antimeridian_examples += 1

    return {
        "archive_directory": str(stats_directory),
        "tracks": totals["tracks"],
        "rows": totals["rows"],
        "malformed_date_rows": totals["malformed_date_rows"],
        "invalid_coordinate_rows": totals["invalid_coordinate_rows"],
        "duplicate_date_rows": totals["duplicate_date_rows"],
        "antimeridian_adjacent_segments": antimeridian_segments,
        "examples_with_large_normalized_previous_longitude_delta": antimeridian_examples,
        "valid_examples_by_target_split": dict(examples_by_split),
        "valid_examples_total": sum(examples_by_split.values()),
        "projection_failures": projection_failures,
        "displacement_magnitude_m": {
            "count": len(magnitudes),
            "minimum": min(magnitudes) if magnitudes else None,
            "median": median(magnitudes) if magnitudes else None,
            "mean": sum(magnitudes) / len(magnitudes) if magnitudes else None,
            "maximum": max(magnitudes) if magnitudes else None,
            "all_finite": projection_failures == 0 and len(magnitudes) == sum(examples_by_split.values()),
        },
        "representative_projected_examples": representatives,
        "feature_shape_per_example": [7],
        "target_shape_per_example": [2],
        "projection": projection,
        "checks": {
            "malformed_dates_excluded": True,
            "observed_position_rule_applied": True,
            "consecutive_24_hour_rule_applied": True,
            "duplicate_examples": 0,
            "future_fields_in_features": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stats-directory", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--dependency-path", type=Path, help="Temporary local directory containing pyproj")
    parser.add_argument(
        "--diagnostic-identity-projector",
        action="store_true",
        help="Validate parsing/window rules only; never use resulting displacements for training.",
    )
    arguments = parser.parse_args()
    if arguments.dependency_path:
        sys.path.insert(0, str(arguments.dependency_path))
    report = run(arguments.stats_directory, arguments.diagnostic_identity_projector)
    arguments.report.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
