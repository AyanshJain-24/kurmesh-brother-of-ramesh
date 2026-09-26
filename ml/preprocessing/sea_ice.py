"""Pure, cell-level G02202 V6 feature construction.

NetCDF decoding belongs in the authorised local acquisition runner.  This
module consumes decoded values so tests and later jobs share the same explicit
missing-value, quality, target, and split rules without adding a dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from math import cos, pi, sin
from typing import Iterable

from .contracts import ChronologicalSplit, SEA_ICE_HORIZON_DAYS, SEA_ICE_LAGS_DAYS


@dataclass(frozen=True)
class SeaIceQualityPolicy:
    """G02202 V6 ancillary allow-lists verified in the official user guide.

    The V6 guide documents 0 as no spatial/temporal interpolation, QA values
    as sums of condition bits (therefore 0 has no listed condition), and 50 as
    the Ocean surface-mask class. The strict policy keeps only those values.
    """

    accepted_qa_flags: frozenset[int] = frozenset({0})
    accepted_spatial_interpolation_flags: frozenset[int] = frozenset({0})
    accepted_temporal_interpolation_flags: frozenset[int] = frozenset({0})
    accepted_surface_type_masks: frozenset[int] = frozenset({50})


STRICT_QUALITY_POLICY = SeaIceQualityPolicy()


@dataclass(frozen=True)
class SeaIceCellRecord:
    observation_date: date
    x_index: int
    y_index: int
    x_m: float
    y_m: float
    raw_concentration: int
    fill_value: int = 255
    qa_flag: int | None = None
    spatial_interpolation_flag: int | None = None
    temporal_interpolation_flag: int | None = None
    surface_type_mask: int | None = None

    def decoded_concentration(self) -> float | None:
        """Decode G02202's uint8 scale without turning missing data into zero."""
        if self.raw_concentration == self.fill_value:
            return None
        if not 0 <= self.raw_concentration <= 100:
            return None
        return self.raw_concentration * 0.01

    def exclusion_reason(self, policy: SeaIceQualityPolicy = STRICT_QUALITY_POLICY) -> str | None:
        if self.raw_concentration == self.fill_value:
            return "fill_value"
        if not 0 <= self.raw_concentration <= 100:
            return "out_of_documented_range"
        if self.qa_flag not in policy.accepted_qa_flags:
            return "qa_flag"
        if self.spatial_interpolation_flag not in policy.accepted_spatial_interpolation_flags:
            return "spatial_interpolation_flag"
        if self.temporal_interpolation_flag not in policy.accepted_temporal_interpolation_flags:
            return "temporal_interpolation_flag"
        if self.surface_type_mask not in policy.accepted_surface_type_masks:
            return "surface_type_mask"
        return None


@dataclass(frozen=True)
class SeaIceExample:
    target_date: date
    split: str
    cell: tuple[int, int]
    features: dict[str, float]
    target_concentration: float


def _seasonal_features(value: date) -> dict[str, float]:
    angle = 2 * pi * value.timetuple().tm_yday / 365.25
    return {"day_of_year_sin": sin(angle), "day_of_year_cos": cos(angle)}


def build_sea_ice_examples(
    records: Iterable[SeaIceCellRecord],
    split: ChronologicalSplit,
    policy: SeaIceQualityPolicy = STRICT_QUALITY_POLICY,
) -> list[SeaIceExample]:
    """Build only complete, quality-approved windows on a stable source cell.

    `target_date` is issue date plus seven days.  Feature windows cannot span a
    train/validation/test boundary, and the future target never enters the
    feature mapping.
    """
    by_cell: dict[tuple[int, int], dict[date, SeaIceCellRecord]] = {}
    for record in records:
        cell_records = by_cell.setdefault((record.x_index, record.y_index), {})
        if record.observation_date in cell_records:
            raise ValueError("duplicate sea-ice cell/date record")
        cell_records[record.observation_date] = record

    examples: list[SeaIceExample] = []
    for cell, cell_records in sorted(by_cell.items()):
        for issue_date in sorted(cell_records):
            target_date = issue_date + timedelta(days=SEA_ICE_HORIZON_DAYS)
            input_dates = tuple(issue_date - timedelta(days=lag) for lag in SEA_ICE_LAGS_DAYS)
            if not split.accepts_example(target_date, input_dates):
                continue
            required_records = [cell_records.get(day) for day in (*input_dates, target_date)]
            if any(record is None or record.exclusion_reason(policy) for record in required_records):
                continue
            input_records = required_records[:-1]
            target_record = required_records[-1]
            assert target_record is not None
            features = {
                "x_m": input_records[0].x_m,
                "y_m": input_records[0].y_m,
                **_seasonal_features(issue_date),
            }
            for lag, record in zip(SEA_ICE_LAGS_DAYS, input_records):
                assert record is not None
                features[f"sic_lag_{lag}_days"] = record.decoded_concentration()  # type: ignore[assignment]
            examples.append(
                SeaIceExample(
                    target_date=target_date,
                    split=split.classify(target_date),
                    cell=cell,
                    features=features,
                    target_concentration=target_record.decoded_concentration(),  # type: ignore[arg-type]
                )
            )
    return examples
