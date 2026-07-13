from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from recomart.config import ProjectConfig
from recomart.orchestration.prefect_flow import (
    write_orchestration_summary,
)


class OrchestrationTests(unittest.TestCase):
    def test_orchestration_summary_contains_status_and_stages(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)

            config = ProjectConfig(
                project_root=root,
                api_base_url="https://example.invalid",
                api_timeout_seconds=1,
                api_max_attempts=1,
                api_backoff_seconds=0,
                resources={},
                clickstream_input=root / "unused.csv",
            )

            summary_path = write_orchestration_summary(
                config=config,
                run_id="test-run",
                status="success",
                stages={
                    "validation": {"status": "success"},
                    "model_training": {"status": "success"},
                },
            )

            self.assertTrue(summary_path.exists())

            with summary_path.open("r", encoding="utf-8") as handle:
                summary = json.load(handle)

            self.assertEqual(summary["orchestrator"], "Prefect")
            self.assertEqual(summary["status"], "success")
            self.assertIn("validation", summary["stages"])
            self.assertIn("model_training", summary["stages"])


if __name__ == "__main__":
    unittest.main()