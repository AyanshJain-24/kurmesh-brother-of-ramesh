import sys
import hashlib
import json
import tempfile
from pathlib import Path
import unittest

try:
    import numpy as np
except ImportError:  # The normal Phase 5D test command supplies the local dependency path.
    np = None

from ml.training.phase5d_baselines import RegressionMetrics, RidgeSufficientStatistics, _write_artifact
from ml.review.phase5e_artifact_review import load_ridge
from ml.packaging.phase5f_artifacts import package_artifact, sha256_file


@unittest.skipIf(np is None, "numpy is required for Phase 5D numerical tests")
class RidgeBaselineTests(unittest.TestCase):
    def test_train_only_statistics_recover_linear_relation(self) -> None:
        train_x = np.asarray([[0.0], [1.0], [2.0], [3.0]])
        train_y = np.asarray([[1.0], [3.0], [5.0], [7.0]])
        stats = RidgeSufficientStatistics(1, 1)
        stats.add(train_x, train_y)
        model = stats.fit(0.0)
        self.assertAlmostEqual(float(model.predict(np.asarray([[4.0]]))[0, 0]), 9.0)
        self.assertAlmostEqual(float(model.mean_x[0]), 1.5)

    def test_metrics_and_two_component_magnitude_error(self) -> None:
        metric = RegressionMetrics(2)
        metric.add(np.asarray([[3.0, 4.0]]), np.asarray([[0.0, 0.0]]))
        result = metric.result(["dx", "dy"])
        self.assertEqual(result["sample_count"], 1)
        self.assertEqual(result["mae"], {"dx": 3.0, "dy": 4.0})
        self.assertEqual(result["mean_absolute_displacement_magnitude_error"], 5.0)

    def test_serialized_model_is_deterministic(self) -> None:
        stats = RidgeSufficientStatistics(1, 1)
        stats.add(np.asarray([[0.0], [1.0]]), np.asarray([[0.0], [1.0]]))
        first = stats.fit(1.0).serializable(["x"], ["y"])
        second = stats.fit(1.0).serializable(["x"], ["y"])
        self.assertEqual(first, second)

    def test_artifact_metadata_carries_matching_sha256(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = _write_artifact(Path(temporary), "model", {"coefficient": 1.0}, {"feature_names": ["x"]})
            artifact = Path(result["artifact"])
            metadata = json.loads(Path(result["metadata"]).read_text(encoding="utf-8"))
            self.assertEqual(result["sha256"], hashlib.sha256(artifact.read_bytes()).hexdigest())
            self.assertEqual(metadata["artifact_sha256"], result["sha256"])

    def test_clean_loader_validates_artifact_dimensions(self) -> None:
        payload = {
            "model_type": "ridge_closed_form_standardized", "alpha": 1.0,
            "feature_names": ["x"], "target_names": ["y"], "feature_mean": [0.0],
            "feature_scale_train_only": [1.0], "target_mean_train_only": [0.0],
            "coefficients": [[2.0]],
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "model.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual(float(load_ridge(path).predict(np.asarray([[3.0]]))[0, 0]), 6.0)

    def test_portable_package_preserves_model_and_manifest_hash(self) -> None:
        model = {
            "model_type": "ridge_closed_form_standardized", "alpha": 1.0,
            "feature_names": ["x"], "target_names": ["y"], "feature_mean": [0.0],
            "feature_scale_train_only": [1.0], "target_mean_train_only": [0.0], "coefficients": [[2.0]],
        }
        metadata = {
            "target_definition": "y", "horizon": "1 day", "splits": {"train": "a", "validation": "b", "test": "c"},
            "sample_counts": {"train": 1, "validation": 1, "test": 1}, "hyperparameters": {"selected_alpha": 1.0},
            "library_versions": {"numpy": "test"}, "random_seed": None, "training_timestamp_utc": "2026-01-01T00:00:00Z",
        }
        manifest = {"dataset": {"name": "Test Dataset", "version": "1", "product_type": "test"}}
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            model_path, metadata_path, manifest_path, output_path = (directory / "model.json", directory / "metadata.json", directory / "manifest.json", directory / "portable.json")
            model_path.write_text(json.dumps(model), encoding="utf-8")
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            result = package_artifact(model_path, metadata_path, manifest_path, "data/manifests/test.json", output_path, "docs/ml/PHASE_5C_PREPROCESSING.md", "v1", "v1")
            package = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertTrue(result["model_parameters_preserved"])
            self.assertEqual(package["model"], model)
            self.assertEqual(package["provenance"]["dataset"]["manifest_sha256"], sha256_file(manifest_path))
            self.assertEqual(float(load_ridge(output_path).predict(np.asarray([[3.0]]))[0, 0]), 6.0)

    def test_portable_package_rejects_machine_local_provenance(self) -> None:
        model = {
            "model_type": "ridge_closed_form_standardized", "alpha": 1.0,
            "feature_names": ["x"], "target_names": ["y"], "feature_mean": [0.0],
            "feature_scale_train_only": [1.0], "target_mean_train_only": [0.0], "coefficients": [[2.0]],
        }
        metadata = {
            "target_definition": "%TEMP%/must-not-appear", "horizon": "1 day",
            "splits": {"train": "a", "validation": "b", "test": "c"},
            "sample_counts": {"train": 1, "validation": 1, "test": 1},
            "hyperparameters": {"selected_alpha": 1.0}, "library_versions": {"numpy": "test"},
            "random_seed": None, "training_timestamp_utc": "2026-01-01T00:00:00Z",
        }
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            model_path, metadata_path, manifest_path = directory / "model.json", directory / "metadata.json", directory / "manifest.json"
            model_path.write_text(json.dumps(model), encoding="utf-8")
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
            manifest_path.write_text(json.dumps({"dataset": {"name": "Test", "version": "1"}}), encoding="utf-8")
            with self.assertRaises(ValueError):
                package_artifact(model_path, metadata_path, manifest_path, "data/manifests/test.json", directory / "portable.json", "docs/ml/PHASE_5C_PREPROCESSING.md", "v1", "v1")


if __name__ == "__main__":
    unittest.main()
