"""Deterministic BYU/NIC V3 trajectory parsing and example construction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from math import cos, pi, sin
from typing import Callable, Iterable, Mapping

from .contracts import ChronologicalSplit

Projector = Callable[[float, float], tuple[float, float]]


@dataclass(frozen=True)
class IcebergObservation:
    track_id: str
    observation_date: date
    date_gap: int
    flags: int
    latitude: float
    longitude: float
    size: float | None = None

    @property
    def observed_position(self) -> bool:
        return bool(self.flags & 1)


@dataclass(frozen=True)
class IcebergParseResult:
    observations: tuple[IcebergObservation, ...]
    malformed_date_rows: int
    invalid_coordinate_rows: int
    duplicate_date_rows: int


@dataclass(frozen=True)
class IcebergExample:
    track_id: str
    target_date: date
    split: str
    features: dict[str, float]
    target_dx_m: float
    target_dy_m: float


def normalize_longitude_difference(current: float, future: float) -> float:
    """Return future-current in [-180, 180), including antimeridian crossings."""
    return ((future - current + 180.0) % 360.0) - 180.0


def _parse_yyyydoy(value: object) -> date | None:
    text = str(value).strip()
    if len(text) != 7 or not text.isdigit():
        return None
    try:
        parsed = datetime.strptime(text, "%Y%j").date()
    except ValueError:
        return None
    return parsed if parsed.strftime("%Y%j") == text else None


def parse_iceberg_rows(track_id: str, rows: Iterable[Mapping[str, object]]) -> IcebergParseResult:
    """Parse one CSV track, excluding malformed dates/coordinates deterministically."""
    observations: list[IcebergObservation] = []
    malformed_dates = invalid_coordinates = 0
    for row in rows:
        observation_date = _parse_yyyydoy(row.get("date", ""))
        if observation_date is None:
            malformed_dates += 1
            continue
        try:
            latitude = float(row["lat"])
            longitude = float(row["lon"])
            flags = int(str(row["flags"]).strip())
            date_gap = int(str(row["date_gap"]).strip())
        except (KeyError, TypeError, ValueError):
            invalid_coordinates += 1
            continue
        if not -90.0 <= latitude <= 90.0 or not -180.0 <= longitude < 180.0:
            invalid_coordinates += 1
            continue
        size_value = row.get("size")
        try:
            size = float(size_value) if size_value not in (None, "") else None
        except (TypeError, ValueError):
            size = None
        observations.append(IcebergObservation(track_id, observation_date, date_gap, flags, latitude, longitude, size))

    observations.sort(key=lambda observation: observation.observation_date)
    deduplicated: list[IcebergObservation] = []
    duplicate_dates = 0
    for observation in observations:
        if deduplicated and deduplicated[-1].observation_date == observation.observation_date:
            duplicate_dates += 1
            continue
        deduplicated.append(observation)
    return IcebergParseResult(tuple(deduplicated), malformed_dates, invalid_coordinates, duplicate_dates)


def _seasonal_features(value: date) -> dict[str, float]:
    angle = 2 * pi * value.timetuple().tm_yday / 365.25
    return {"day_of_year_sin": sin(angle), "day_of_year_cos": cos(angle)}


def build_iceberg_examples(
    observations: Iterable[IcebergObservation], split: ChronologicalSplit, projector: Projector
) -> list[IcebergExample]:
    """Build observed, consecutive 24-hour displacement examples per track.

    Every example uses a preceding and issue observation as past-only features
    and the following observation solely as its label.  A track may span split
    dates, but no single feature/target window may do so.
    """
    by_track: dict[str, list[IcebergObservation]] = {}
    for observation in observations:
        by_track.setdefault(observation.track_id, []).append(observation)

    examples: list[IcebergExample] = []
    for track_id, track in sorted(by_track.items()):
        track.sort(key=lambda observation: observation.observation_date)
        for previous, current, future in zip(track, track[1:], track[2:]):
            if not (
                current.observation_date - previous.observation_date == timedelta(days=1)
                and future.observation_date - current.observation_date == timedelta(days=1)
                and current.date_gap == 1
                and future.date_gap == 1
                and previous.observed_position
                and current.observed_position
                and future.observed_position
                and split.accepts_example(future.observation_date, (previous.observation_date, current.observation_date))
            ):
                continue
            previous_x, previous_y = projector(previous.longitude, previous.latitude)
            current_x, current_y = projector(current.longitude, current.latitude)
            future_x, future_y = projector(future.longitude, future.latitude)
            features = {
                "current_x_m": current_x,
                "current_y_m": current_y,
                "previous_dx_m": current_x - previous_x,
                "previous_dy_m": current_y - previous_y,
                "previous_delta_longitude_deg": normalize_longitude_difference(previous.longitude, current.longitude),
                **_seasonal_features(current.observation_date),
            }
            examples.append(
                IcebergExample(
                    track_id=track_id,
                    target_date=future.observation_date,
                    split=split.classify(future.observation_date),
                    features=features,
                    target_dx_m=future_x - current_x,
                    target_dy_m=future_y - current_y,
                )
            )
    return examples
