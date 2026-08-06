from __future__ import annotations

import hashlib
from pathlib import Path
from unittest import TestCase
import tempfile

from core.config import load_settings
from core.utils import (
    ArtifactValidationError,
    file_sha256,
    require_file_artifact,
    require_json_artifact,
    write_json,
)


class ArtifactGateTests(TestCase):
    def test_file_gate_rejects_missing_and_empty_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "artifact.json"
            with self.assertRaisesRegex(ArtifactValidationError, "Missing test artifact"):
                require_file_artifact(path, "test")

            path.touch()
            with self.assertRaisesRegex(ArtifactValidationError, "Empty test artifact"):
                require_file_artifact(path, "test")

    def test_json_gate_checks_payload_type(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "artifact.json"
            write_json(path, [1, 2, 3])

            self.assertEqual(require_json_artifact(path, "test", list), [1, 2, 3])
            with self.assertRaisesRegex(ArtifactValidationError, "expected dict"):
                require_json_artifact(path, "test", dict)

    def test_file_sha256_matches_standard_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "artifact.bin"
            payload = b"stable pipeline artifact"
            path.write_bytes(payload)

            self.assertEqual(file_sha256(path), hashlib.sha256(payload).hexdigest())


class SettingsContractTests(TestCase):
    def test_state_artifact_paths_and_collections_are_distinct(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = load_settings(project_dir=Path(temp_dir))

            self.assertEqual(settings.source_api, "https://api.crossref.org/works")
            self.assertEqual(
                len(
                    {
                        settings.baseline_collection_name,
                        settings.corrupted_collection_name,
                        settings.repaired_collection_name,
                    }
                ),
                3,
            )
            self.assertEqual(
                len(
                    {
                        settings.paths.baseline_freshness_report,
                        settings.paths.corrupted_freshness_report,
                        settings.paths.repaired_freshness_report,
                    }
                ),
                3,
            )
            self.assertEqual(
                len(
                    {
                        settings.paths.baseline_quality_report,
                        settings.paths.corrupted_quality_report,
                        settings.paths.repaired_quality_report,
                    }
                ),
                3,
            )
