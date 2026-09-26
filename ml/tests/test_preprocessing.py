from datetime import date, timedelta
import unittest

from ml.preprocessing.contracts import ChronologicalSplit, DateRange
from ml.preprocessing.iceberg import (
    IcebergObservation,
    build_iceberg_examples,
    normalize_longitude_difference,
    parse_iceberg_rows,
)
from ml.preprocessing.sea_ice import SeaIceCellRecord, build_sea_ice_examples


def split() -> ChronologicalSplit:
    return ChronologicalSplit(
        DateRange(date(2021, 1, 1), date(2021, 1, 20)),
        DateRange(date(2021, 1, 21), date(2021, 1, 22)),
        DateRange(date(2021, 1, 23), date(2021, 2, 10)),
        DateRange(date(2021, 2, 11), date(2021, 2, 12)),
        DateRange(date(2021, 2, 13), date(2021, 3, 1)),
    )


class SeaIcePreprocessingTests(unittest.TestCase):
    def record(self, day: date, raw: int = 50, **changes: object) -> SeaIceCellRecord:
        values = dict(
            observation_date=day, x_index=1, y_index=2, x_m=25_000.0, y_m=-25_000.0,
            raw_concentration=raw, qa_flag=0, spatial_interpolation_flag=0,
            temporal_interpolation_flag=0, surface_type_mask=50,
        )
        values.update(changes)
        return SeaIceCellRecord(**values)

    def test_fill_scaling_and_quality_exclusion(self) -> None:
        self.assertIsNone(self.record(date(2021, 1, 1), 255).decoded_concentration())
        self.assertEqual(self.record(date(2021, 1, 1), 50).decoded_concentration(), 0.5)
        self.assertEqual(self.record(date(2021, 1, 1), 101).exclusion_reason(), "out_of_documented_range")
        self.assertEqual(self.record(date(2021, 1, 1), qa_flag=1).exclusion_reason(), "qa_flag")
        self.assertEqual(
            self.record(date(2021, 1, 1), spatial_interpolation_flag=1).exclusion_reason(),
            "spatial_interpolation_flag",
        )
        self.assertEqual(
            self.record(date(2021, 1, 1), temporal_interpolation_flag=1).exclusion_reason(),
            "temporal_interpolation_flag",
        )
        self.assertEqual(self.record(date(2021, 1, 1), surface_type_mask=75).exclusion_reason(), "surface_type_mask")

    def test_future_target_is_not_a_feature(self) -> None:
        issue = date(2021, 1, 8)
        records = [self.record(issue - timedelta(days=lag), 10 + lag) for lag in (0, 1, 2, 3, 7)]
        records.append(self.record(issue + timedelta(days=7), 80))
        examples = build_sea_ice_examples(records, split())
        self.assertEqual(len(examples), 1)
        example = examples[0]
        self.assertEqual(example.target_concentration, 0.8)
        self.assertNotIn("sic_lag_7_days_target", example.features)
        self.assertNotIn(0.8, example.features.values())

    def test_cross_split_feature_window_is_rejected(self) -> None:
        # Target falls on the first validation day, but t-7 lies in embargo.
        issue = date(2021, 1, 16)
        records = [self.record(issue - timedelta(days=lag)) for lag in (0, 1, 2, 3, 7)]
        records.append(self.record(issue + timedelta(days=7)))
        self.assertEqual(build_sea_ice_examples(records, split()), [])


class IcebergPreprocessingTests(unittest.TestCase):
    def test_parser_excludes_invalid_dates_and_deduplicates(self) -> None:
        parsed = parse_iceberg_rows("A1", [
            {"date": "2021002", "date_gap": "1", "flags": "1", "lat": "-70", "lon": "179"},
            {"date": "bad", "date_gap": "1", "flags": "1", "lat": "-70", "lon": "0"},
            {"date": "2021001", "date_gap": "1", "flags": "1", "lat": "-71", "lon": "178"},
            {"date": "2021002", "date_gap": "1", "flags": "1", "lat": "-70", "lon": "179"},
        ])
        self.assertEqual(parsed.malformed_date_rows, 1)
        self.assertEqual(parsed.duplicate_date_rows, 1)
        self.assertEqual([row.observation_date for row in parsed.observations], [date(2021, 1, 1), date(2021, 1, 2)])

    def test_parser_excludes_invalid_coordinates(self) -> None:
        parsed = parse_iceberg_rows("A1", [
            {"date": "2021001", "date_gap": "1", "flags": "1", "lat": "-91", "lon": "0"},
            {"date": "2021002", "date_gap": "1", "flags": "1", "lat": "-70", "lon": "180"},
        ])
        self.assertEqual(parsed.invalid_coordinate_rows, 2)
        self.assertEqual(parsed.observations, ())

    def test_dateline_normalization(self) -> None:
        self.assertEqual(normalize_longitude_difference(179, -179), 2)
        self.assertEqual(normalize_longitude_difference(-179, 179), -2)

    def test_past_only_trajectory_features_and_target(self) -> None:
        track = [
            IcebergObservation("A1", date(2021, 1, 1), 1, 1, -70, 178),
            IcebergObservation("A1", date(2021, 1, 2), 1, 1, -69, 179),
            IcebergObservation("A1", date(2021, 1, 3), 1, 1, -68, -179),
        ]
        examples = build_iceberg_examples(track, split(), lambda lon, lat: (lon * 1000, lat * 1000))
        self.assertEqual(len(examples), 1)
        example = examples[0]
        self.assertEqual(example.features["previous_dx_m"], 1000)
        self.assertEqual(example.features["previous_delta_longitude_deg"], 1)
        self.assertEqual(example.target_dx_m, -358000)
        self.assertNotIn("target_dx_m", example.features)

    def test_cross_split_track_window_is_rejected(self) -> None:
        track = [
            IcebergObservation("A1", date(2021, 1, 20), 1, 1, -70, 0),
            IcebergObservation("A1", date(2021, 1, 21), 1, 1, -70, 1),
            IcebergObservation("A1", date(2021, 1, 23), 1, 1, -70, 2),
        ]
        self.assertEqual(build_iceberg_examples(track, split(), lambda lon, lat: (lon, lat)), [])


if __name__ == "__main__":
    unittest.main()
