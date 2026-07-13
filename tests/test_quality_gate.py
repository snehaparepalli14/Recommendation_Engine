from __future__ import annotations

import json
import logging
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from recomart.config import ProjectConfig
from recomart.storage import store_csv_snapshot, store_json_snapshot
from recomart.validation.quality_gate import (
    validate_carts,
    validate_events,
    validate_latest_raw_snapshots,
    validate_products,
    validate_users,
)


def product(identifier: int = 1, **changes: object) -> dict[str, object]:
    record: dict[str, object] = {
        "id": identifier,
        "title": "Item",
        "price": 10.0,
        "category": "test",
        "rating": 4.0,
        "stock": 3,
        "tags": [],
        "images": [],
    }
    record.update(changes)
    return record


def user(identifier: int = 1, **changes: object) -> dict[str, object]:
    record: dict[str, object] = {
        "id": identifier,
        "username": "user",
        "email": "user@example.com",
        "firstName": "First",
        "lastName": "Last",
        "age": 25,
    }
    record.update(changes)
    return record


class EntityValidationTests(unittest.TestCase):
    def test_product_rules(self) -> None:
        errors = validate_products(
            [
                product(1, price=-1, rating=6, stock=-2),
                product(1, title=""),
            ]
        )

        rules = {
            error["rule"]
            for row in errors
            for error in row
        }

        self.assertTrue(
            {"duplicate", "range", "missing_required"}.issubset(rules)
        )

    def test_invalid_email_and_event(self) -> None:
        user_errors = validate_users(
            [user(email="invalid-email")]
        )[0]

        event_errors = validate_events(
            [
                {
                    "event_id": "e1",
                    "user_id": "1",
                    "product_id": "1",
                    "event_type": "wrong",
                    "event_timestamp": "yesterday",
                    "session_id": "s1",
                }
            ],
            {1},
            {1},
        )[0]

        self.assertIn(
            "format",
            {error["rule"] for error in user_errors},
        )
        self.assertIn(
            "format",
            {error["rule"] for error in event_errors},
        )

    def test_unknown_references_and_zero_quantity(self) -> None:
        errors = validate_carts(
            [
                {
                    "id": 1,
                    "userId": 99,
                    "products": [{"id": 88, "quantity": 0}],
                }
            ],
            {1},
            {1},
        )[0]

        rules = {error["rule"] for error in errors}

        self.assertIn("referential_integrity", rules)
        self.assertIn("range", rules)


class ValidationPipelineTests(unittest.TestCase):
    def create_config(
        self,
        root: Path,
        include_errors: bool,
    ) -> ProjectConfig:
        instant = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)

        products = [product(1)]
        users = [user(1)]
        carts = [
            {
                "id": 1,
                "userId": 1,
                "products": [{"id": 1, "quantity": 1}],
                "total": 10,
                "totalProducts": 1,
                "totalQuantity": 1,
            }
        ]
        events = [
            {
                "event_id": "e1",
                "user_id": "1",
                "product_id": "1",
                "event_type": "view",
                "event_timestamp": "2026-07-11T10:00:00Z",
                "session_id": "s1",
            }
        ]

        if include_errors:
            products.append(product(2, price=-5))
            events.append(
                {
                    "event_id": "e2",
                    "user_id": "1",
                    "product_id": "999",
                    "event_type": "wrong",
                    "event_timestamp": "bad",
                    "session_id": "s2",
                }
            )

        raw = root / "data" / "raw"

        store_json_snapshot(
            raw,
            "dummyjson",
            "products",
            {"products": products},
            len(products),
            instant,
        )
        store_json_snapshot(
            raw,
            "dummyjson",
            "users",
            {"users": users},
            len(users),
            instant,
        )
        store_json_snapshot(
            raw,
            "dummyjson",
            "carts",
            {"carts": carts},
            len(carts),
            instant,
        )

        columns = [
            "event_id",
            "user_id",
            "product_id",
            "event_type",
            "event_timestamp",
            "session_id",
        ]

        store_csv_snapshot(
            raw,
            "clickstream",
            "events",
            columns,
            events,
            instant,
        )

        return ProjectConfig(
            project_root=root,
            api_base_url="https://example.invalid",
            api_timeout_seconds=1,
            api_max_attempts=1,
            api_backoff_seconds=0,
            resources={},
            clickstream_input=root / "unused.csv",
        )

    def test_valid_dataset_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = validate_latest_raw_snapshots(
                self.create_config(Path(temp_dir), include_errors=False),
                logging.getLogger("test"),
            )

            self.assertEqual(report["status"], "passed")
            self.assertTrue(Path(report["json_report"]).exists())
            self.assertTrue(Path(report["pdf_report"]).exists())

    def test_invalid_dataset_is_quarantined(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = validate_latest_raw_snapshots(
                self.create_config(Path(temp_dir), include_errors=True),
                logging.getLogger("test"),
            )

            self.assertEqual(
                report["status"],
                "completed_with_issues",
            )

            quarantine_path = Path(
                report["datasets"]["events"]["quarantine_output"]
            )
            quarantine_rows = json.loads(
                quarantine_path.read_text(encoding="utf-8")
            )

            self.assertEqual(len(quarantine_rows), 1)
            self.assertIn("_validation_errors", quarantine_rows[0])
            self.assertIn("_source_row_number", quarantine_rows[0])


if __name__ == "__main__":
    unittest.main()