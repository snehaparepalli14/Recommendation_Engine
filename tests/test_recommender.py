from __future__ import annotations

import logging
import tempfile
import unittest
from pathlib import Path

import duckdb

from recomart.config import ProjectConfig
from recomart.models.recommender import (
    recommend_products,
    split_interactions,
    train_recommender,
)


class RecommenderTests(unittest.TestCase):
    def make_config(self, root: Path) -> ProjectConfig:
        return ProjectConfig(
            project_root=root,
            api_base_url="https://example.invalid",
            api_timeout_seconds=1,
            api_max_attempts=1,
            api_backoff_seconds=0,
            resources={},
            clickstream_input=root / "unused.csv",
        )

    def test_split_holds_out_one_product_per_eligible_user(self) -> None:
        interactions = [
            (1, 10, 3.0),
            (1, 11, 2.0),
            (2, 10, 1.0),
            (2, 12, 4.0),
        ]

        training, held_out = split_interactions(interactions, seed=42)

        self.assertEqual(len(held_out), 2)
        self.assertEqual(len(training), 2)

        training_pairs = {
            (user_id, product_id)
            for user_id, product_id, _ in training
        }

        for user_id, product_id in held_out.items():
            self.assertNotIn((user_id, product_id), training_pairs)

    def test_training_creates_model_metrics_and_recommendations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            feature_store_dir = root / "data" / "feature_store"
            warehouse_dir = root / "data" / "warehouse"
            feature_store_dir.mkdir(parents=True)
            warehouse_dir.mkdir(parents=True)

            feature_store_path = (
                feature_store_dir / "recomart_feature_store.db"
            )
            connection = duckdb.connect(str(feature_store_path))

            try:
                connection.execute(
                    """
                    CREATE TABLE user_product_v1 (
                        user_id BIGINT,
                        product_id BIGINT,
                        weighted_interaction_score DOUBLE
                    )
                    """
                )
                connection.execute(
                    """
                    INSERT INTO user_product_v1 VALUES
                    (1, 1, 4.0), (1, 2, 3.0), (1, 3, 2.0),
                    (2, 1, 4.0), (2, 3, 3.0), (2, 4, 2.0),
                    (3, 2, 4.0), (3, 4, 3.0), (3, 5, 2.0)
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE product_popularity_v1 (
                        product_id BIGINT
                    )
                    """
                )
                connection.execute(
                    """
                    INSERT INTO product_popularity_v1 VALUES
                    (1), (2), (3), (4), (5), (6)
                    """
                )
            finally:
                connection.close()

            warehouse_path = warehouse_dir / "recomart.db"
            connection = duckdb.connect(str(warehouse_path))

            try:
                connection.execute(
                    """
                    CREATE TABLE dim_products AS
                    SELECT
                        product_id,
                        'Product ' || CAST(product_id AS VARCHAR) AS title
                    FROM (VALUES (1), (2), (3), (4), (5), (6))
                    AS products(product_id)
                    """
                )
            finally:
                connection.close()

            config = self.make_config(root)

            summary = train_recommender(
                config=config,
                logger=logging.getLogger("test"),
                rank=2,
                top_k=2,
                seed=42,
            )

            self.assertTrue(Path(summary["model_path"]).exists())
            self.assertTrue(
                Path(summary["evaluation_report"]).exists()
            )
            self.assertEqual(
                summary["metrics"]["evaluated_users"],
                3,
            )

            response = recommend_products(
                config=config,
                user_id=1,
                limit=2,
            )

            self.assertEqual(
                response["recommendation_source"],
                "svd_personalized",
            )
            self.assertEqual(
                len(response["recommendations"]),
                2,
            )


if __name__ == "__main__":
    unittest.main()