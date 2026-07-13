from __future__ import annotations

import json
import logging
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from recomart.config import ProjectConfig
from recomart.preparation.prepare_eda import (
    clean_carts,
    clean_events,
    clean_products,
    clean_users,
    create_interactions,
    run_preparation_and_eda,
)


class PreparationUnitTests(unittest.TestCase):
    def test_product_cleaning_flattens_fields_and_tags(self) -> None:
        products = clean_products(
            [
                {
                    "id": 1,
                    "title": "Test Product",
                    "description": "Example",
                    "category": " Electronics ",
                    "brand": None,
                    "price": 99.5,
                    "rating": 4.5,
                    "stock": 10,
                    "tags": ["new", "popular"],
                    "thumbnail": "image.png",
                    "dimensions": {
                        "width": 10,
                        "height": 20,
                        "depth": 5,
                    },
                }
            ]
        )

        self.assertEqual(products.loc[0, "product_id"], 1)
        self.assertEqual(products.loc[0, "category"], "electronics")
        self.assertEqual(products.loc[0, "brand"], "unknown")
        self.assertEqual(products.loc[0, "tags"], "new|popular")
        self.assertEqual(products.loc[0, "dimension_width"], 10)

    def test_user_cleaning_excludes_sensitive_fields(self) -> None:
        users = clean_users(
            [
                {
                    "id": 1,
                    "username": "student",
                    "firstName": "Asha",
                    "lastName": "Kumar",
                    "email": "asha@example.com",
                    "age": 25,
                    "gender": "Female",
                    "password": "must_not_be_kept",
                    "ssn": "must_not_be_kept",
                    "bank": {"cardNumber": "must_not_be_kept"},
                    "address": {
                        "city": "Mumbai",
                        "state": "Maharashtra",
                        "country": "India",
                    },
                    "company": {"department": "Engineering"},
                }
            ]
        )

        self.assertEqual(users.loc[0, "user_id"], 1)
        self.assertEqual(users.loc[0, "gender"], "female")
        self.assertEqual(users.loc[0, "city"], "Mumbai")
        self.assertNotIn("password", users.columns)
        self.assertNotIn("ssn", users.columns)
        self.assertNotIn("bank", users.columns)

    def test_cart_cleaning_flattens_cart_products(self) -> None:
        carts, cart_items = clean_carts(
            [
                {
                    "id": 10,
                    "userId": 1,
                    "total": 100,
                    "discountedTotal": 90,
                    "totalProducts": 2,
                    "totalQuantity": 3,
                    "products": [
                        {
                            "id": 3,
                            "quantity": 2,
                            "total": 60,
                            "discountedTotal": 55,
                        },
                        {
                            "id": 4,
                            "quantity": 1,
                            "total": 40,
                            "discountedTotal": 35,
                        },
                    ],
                }
            ]
        )

        self.assertEqual(len(carts), 1)
        self.assertEqual(len(cart_items), 2)
        self.assertEqual(cart_items.loc[0, "cart_id"], 10)
        self.assertEqual(cart_items.loc[0, "product_id"], 3)
        self.assertEqual(cart_items.loc[0, "quantity"], 2)

    def test_event_cleaning_and_interaction_creation(self) -> None:
        events = clean_events(
            [
                {
                    "event_id": "e1",
                    "user_id": "1",
                    "product_id": "2",
                    "event_type": "VIEW",
                    "event_timestamp": "2026-07-13T10:00:00Z",
                    "session_id": "s1",
                }
            ]
        )

        _, cart_items = clean_carts(
            [
                {
                    "id": 1,
                    "userId": 1,
                    "products": [
                        {
                            "id": 2,
                            "quantity": 3,
                            "total": 100,
                            "discountedTotal": 90,
                        }
                    ],
                }
            ]
        )

        interactions = create_interactions(events, cart_items)

        self.assertEqual(events.loc[0, "event_type"], "view")
        self.assertEqual(len(interactions), 2)
        self.assertEqual(
            set(interactions["source"]),
            {"clickstream", "cart_snapshot"},
        )


class PreparationPipelineTests(unittest.TestCase):
    def write_prepared_file(
        self,
        root: Path,
        entity: str,
        records: list[dict[str, object]],
    ) -> None:
        directory = (
            root
            / "data"
            / "prepared"
            / entity
            / "validation_date=2026-07-13"
        )
        directory.mkdir(parents=True, exist_ok=True)

        path = directory / f"{entity}_test.json"

        with path.open("w", encoding="utf-8") as handle:
            json.dump(records, handle)

    def test_pipeline_creates_parquet_outputs_plots_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)

            self.write_prepared_file(
                root,
                "products",
                [
                    {
                        "id": 1,
                        "title": "Test Product",
                        "description": "Example product",
                        "category": "electronics",
                        "brand": "Example Brand",
                        "price": 100.0,
                        "rating": 4.5,
                        "stock": 10,
                        "tags": ["test"],
                        "thumbnail": "image.png",
                        "dimensions": {
                            "width": 10,
                            "height": 20,
                            "depth": 5,
                        },
                    }
                ],
            )

            self.write_prepared_file(
                root,
                "users",
                [
                    {
                        "id": 1,
                        "username": "student",
                        "firstName": "Asha",
                        "lastName": "Kumar",
                        "email": "asha@example.com",
                        "age": 25,
                        "gender": "female",
                        "address": {
                            "city": "Mumbai",
                            "state": "Maharashtra",
                            "country": "India",
                        },
                        "company": {"department": "Engineering"},
                        "password": "excluded",
                    }
                ],
            )

            self.write_prepared_file(
                root,
                "carts",
                [
                    {
                        "id": 1,
                        "userId": 1,
                        "total": 100,
                        "discountedTotal": 90,
                        "totalProducts": 1,
                        "totalQuantity": 2,
                        "products": [
                            {
                                "id": 1,
                                "quantity": 2,
                                "total": 100,
                                "discountedTotal": 90,
                            }
                        ],
                    }
                ],
            )

            self.write_prepared_file(
                root,
                "events",
                [
                    {
                        "event_id": "e1",
                        "user_id": "1",
                        "product_id": "1",
                        "event_type": "view",
                        "event_timestamp": "2026-07-13T10:00:00Z",
                        "session_id": "s1",
                    }
                ],
            )

            config = ProjectConfig(
                project_root=root,
                api_base_url="https://example.invalid",
                api_timeout_seconds=1,
                api_max_attempts=1,
                api_backoff_seconds=0,
                resources={},
                clickstream_input=root / "unused.csv",
            )

            summary = run_preparation_and_eda(
                config,
                logging.getLogger("test"),
            )

            self.assertEqual(summary["row_counts"]["products"], 1)
            self.assertEqual(summary["row_counts"]["cart_items"], 1)
            self.assertEqual(summary["row_counts"]["interactions"], 2)

            for output_path in summary["processed_outputs"].values():
                self.assertTrue(Path(output_path).exists())

            for plot_path in summary["plots"]:
                self.assertTrue(Path(plot_path).exists())

            self.assertEqual(len(summary["plots"]), 7)
            self.assertTrue(Path(summary["summary_report"]).exists())

            products_path = Path(
                summary["processed_outputs"]["products"]
            )
            saved_products = pd.read_parquet(products_path)

            self.assertEqual(len(saved_products), 1)
            self.assertNotIn("password", saved_products.columns)


if __name__ == "__main__":
    unittest.main()