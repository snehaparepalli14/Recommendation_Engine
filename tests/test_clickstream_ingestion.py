from __future__ import annotations

import logging
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from recomart.config import ProjectConfig
from recomart.ingestion.clickstream import ingest_clickstream


def configuration(root: Path, clickstream_input: Path) -> ProjectConfig:
    return ProjectConfig(root, "https://example.invalid", 1, 1, 0, {}, clickstream_input)


class ClickstreamIngestionTests(unittest.TestCase):
    def test_valid_csv_is_written_to_a_raw_partition(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            csv_path = root / "events.csv"
            csv_path.write_text("event_id,user_id,product_id,event_type,event_timestamp,session_id\ne-1,1,2,view,2026-07-11T09:00:00Z,s-1\n", encoding="utf-8")
            artifact, metadata = ingest_clickstream(configuration(root, csv_path), logging.getLogger("test"), captured_at=datetime(2026, 7, 11, 9, 30, tzinfo=timezone.utc))
            self.assertTrue(artifact.path.exists())
            self.assertEqual(artifact.record_count, 1)
            self.assertEqual(metadata["status"], "success")

    def test_missing_required_column_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            csv_path = root / "events.csv"
            csv_path.write_text("event_id,user_id\ne-1,1\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "missing required columns"):
                ingest_clickstream(configuration(root, csv_path), logging.getLogger("test"))


if __name__ == "__main__":
    unittest.main()
