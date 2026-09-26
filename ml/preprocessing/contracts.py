"""Frozen time contracts used before any Phase 5 model training.

This module deliberately contains no model, estimator, file downloader, or
application integration.  Dates classify *target* timestamps; an example is
accepted only when all of its feature timestamps are in that same split.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

SplitName = Literal["train", "validation", "test", "embargo", "outside"]


@dataclass(frozen=True)
class DateRange:
    """An inclusive calendar-date interval."""

    start: date
    end: date

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError("date range end precedes start")

    def contains(self, value: date) -> bool:
        return self.start <= value <= self.end


@dataclass(frozen=True)
class ChronologicalSplit:
    """Chronological target-date split with explicit purged intervals."""

    train: DateRange
    first_embargo: DateRange
    validation: DateRange
    second_embargo: DateRange
    test: DateRange

    def __post_init__(self) -> None:
        ranges = (
            self.train,
            self.first_embargo,
            self.validation,
            self.second_embargo,
            self.test,
        )
        if any(left.end >= right.start for left, right in zip(ranges, ranges[1:])):
            raise ValueError("split ranges must be ordered and non-overlapping")

    def classify(self, target_date: date) -> SplitName:
        if self.train.contains(target_date):
            return "train"
        if self.validation.contains(target_date):
            return "validation"
        if self.test.contains(target_date):
            return "test"
        if self.first_embargo.contains(target_date) or self.second_embargo.contains(target_date):
            return "embargo"
        return "outside"

    def accepts_example(self, target_date: date, feature_dates: tuple[date, ...]) -> bool:
        """Reject embargo/outside targets and any cross-split feature window."""
        split = self.classify(target_date)
        return split in {"train", "validation", "test"} and all(
            self.classify(feature_date) == split for feature_date in feature_dates
        )


# G02202 V6 final CDR.  This pre-AMSR2 interval is the first frozen prototype
# interval, not a claim that every calendar day has already been acquired.
SEA_ICE_RAW_INTERVAL = DateRange(date(2021, 1, 1), date(2024, 12, 31))
SEA_ICE_LAGS_DAYS = (0, 1, 2, 3, 7)
SEA_ICE_HORIZON_DAYS = 7
SEA_ICE_SPLIT = ChronologicalSplit(
    train=DateRange(date(2021, 1, 15), date(2023, 10, 24)),
    first_embargo=DateRange(date(2023, 10, 25), date(2023, 11, 7)),
    validation=DateRange(date(2023, 11, 8), date(2024, 5, 28)),
    second_embargo=DateRange(date(2024, 5, 29), date(2024, 6, 11)),
    test=DateRange(date(2024, 6, 12), date(2024, 12, 31)),
)

# The 1976 date in the archive is a documented anomaly.  The initial experiment
# freezes the consistently modern historical interval; exact pair availability
# remains data-dependent and is checked by the builder.
ICEBERG_RAW_INTERVAL = DateRange(date(1992, 1, 1), date(2019, 8, 14))
ICEBERG_HORIZON_DAYS = 1
ICEBERG_SPLIT = ChronologicalSplit(
    train=DateRange(date(1992, 1, 3), date(2011, 5, 2)),
    first_embargo=DateRange(date(2011, 5, 3), date(2011, 5, 5)),
    validation=DateRange(date(2011, 5, 6), date(2015, 6, 27)),
    second_embargo=DateRange(date(2015, 6, 28), date(2015, 6, 30)),
    test=DateRange(date(2015, 7, 1), date(2019, 8, 14)),
)
