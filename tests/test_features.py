from __future__ import annotations

import logging
import tempfile
import unittest
from pathlib import Path

import duckdb
import pandas as pd

from recomart.config import ProjectConfig
from recomart.features.warehouse import run_feature_engineering


class FeatureEngineeringTests(unittest.TestCase):
    def write_parquet(
        self,
        root: Path,
        name: str,
        rows: list[dict[str, object]],
    ) -> None:
        directory = (
            root
            / "data"
            / "processed"
            / "preparation_date=2026-07-13"
        )
        directory.mkdir(parents=True, exist_ok=True)

        pd.DataFrame(rows).to_parquet(
            directory / f"{name}_test.parquet",
            index=False,
        )

    def test_warehouse_and_features_are_created(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)

            self.write_parquet(
                root,
                "products",
                [
                    {
                        "product_id": 1,
                        "title": "Product One",
                        "category": "electronics",
                        "category_code": 0,
                        "price": 100.0,
                        "price_normalized": 0.0,
                        "rating": 4.0,
                    },
                    {
                        "product_id": 2,
                        "title": "Product Two",
                        "category": "books",
                        "category_code": 1,
                        "price": 200.0,
                        "price_normalized": 1.0,
                        "rating": 5.0,
                    },
                ],
            )
            self.write_parquet(
                root,
                "users",
                [{"user_id": 1, "username": "student"}],
            )
            self.write_parquet(
                root,
                "carts",
                [{"cart_id": 1, "user_id": 1, "total": 300.0}],
            )
            self.write_parquet(
                root,
                "cart_items",
                [
                    {"cart_id": 1, "user_id": 1, "product_id": 1, "quantity": 1},
                    {"cart_id": 1, "user_id": 1, "product_id": 2, "quantity": 2},
                ],
            )
            self.write_parquet(
                root,
                "events",
                [
                    {
                        "event_id": "event-1",
                        "user_id": 1,
                        "product_id": 1,
                        "event_type": "view",
                        "event_timestamp": "2026-07-13T10:00:00Z",
                        "session_id": "session-1",
                    }
                ],
            )
            self.write_parquet(
                root,
                "interactions",
                [
                    {
                        "user_id": 1,
                        "product_id": 1,
                        "event_type": "view",
                        "event_timestamp": "2026-07-13T10:00:00Z",
                        "session_id": "session-1",
                        "quantity": 1,
                        "source": "clickstream",
                        "observed_interaction": 1,
                    },
                    {
                        "user_id": 1,
                        "product_id": 2,
                        "event_type": "cart",
                        "event_timestamp": None,
                        "session_id": None,
                        "quantity": 2,
                        "source": "cart_snapshot",
                        "observed_interaction": 1,
                    },
                ],
            )
            self.write_parquet(
                root,
                "product_popularity",
                [{"product_id": 1, "interaction_count": 1}],
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

            summary = run_feature_engineering(
                config,
                logging.getLogger("test"),
            )

            self.assertEqual(
                summary["table_row_counts"]["dim_products"],
                2,
            )
            self.assertEqual(
                summary["table_row_counts"]["feature_user_product"],
                2,
            )
            self.assertEqual(
                summary["table_row_counts"]["feature_product_cooccurrence"],
                1,
            )

            connection = duckdb.connect(
                summary["warehouse_database"],
                read_only=True,
            )
            try:
                score = connection.execute(
                    """
                    SELECT weighted_interaction_score
                    FROM feature_user_product
                    WHERE user_id = 1 AND product_id = 2
                    """
                ).fetchone()[0]
            finally:
                connection.close()

            self.assertEqual(score, 3)


if __name__ == "__main__":
    unittest.main()