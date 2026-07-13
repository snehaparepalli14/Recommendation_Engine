from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from recomart.storage import partition_directory, store_json_snapshot


class StorageTests(unittest.TestCase):
    def test_partition_contains_source_entity_and_date(self) -> None:
        instant = datetime(2026, 7, 11, 9, 30, tzinfo=timezone.utc)
        self.assertEqual(
            partition_directory(Path("raw"), "dummyjson", "products", instant),
            Path("raw/dummyjson/products/ingestion_date=2026-07-11"),
        )

    def test_json_snapshot_has_count_and_checksum(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            artifact = store_json_snapshot(
                Path(temporary_directory), "dummyjson", "products", {"products": [{"id": 1}]}, 1,
                datetime(2026, 7, 11, 9, 30, tzinfo=timezone.utc),
            )
            self.assertTrue(artifact.path.exists())
            self.assertEqual(artifact.record_count, 1)
            self.assertEqual(len(artifact.sha256), 64)
            self.assertEqual(json.loads(artifact.path.read_text(encoding="utf-8"))["products"][0]["id"], 1)


if __name__ == "__main__":
    unittest.main()

