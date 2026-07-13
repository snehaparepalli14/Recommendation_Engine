from __future__ import annotations

import logging
import tempfile
import unittest
from pathlib import Path

import duckdb

from recomart.config import ProjectConfig
from recomart.feature_store.store import (
    materialize_feature_store,
    retrieve_features,
)


class FeatureStoreTests(unittest.TestCase):
    def test_versioned_training_and_inference_retrieval_match(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            warehouse_dir = root / "data" / "warehouse"
            warehouse_dir.mkdir(parents=True)

            warehouse_path = warehouse_dir / "recomart.db"
            connection = duckdb.connect(str(warehouse_path))

            try:
                connection.execute(
                    """
                    CREATE TABLE feature_user_activity AS
                    SELECT
                        1 AS user_id,
                        5 AS interaction_count,
                        4 AS distinct_product_count,
                        9 AS total_interaction_quantity,
                        4.2 AS average_interacted_product_rating,
                        2 AS active_event_days
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE feature_product_popularity AS
                    SELECT
                        10 AS product_id,
                        5 AS interaction_count
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE feature_user_product AS
                    SELECT
                        1 AS user_id,
                        10 AS product_id,
                        7 AS weighted_interaction_score
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE feature_product_cooccurrence AS
                    SELECT
                        10 AS product_id_left,
                        11 AS product_id_right,
                        3 AS cart_cooccurrence_count
                    """
                )
            finally:
                connection.close()

            config = ProjectConfig(
                project_root=root,
                api_base_url="https://example.invalid",
                api_timeout_seconds=1,
                api_max_attempts=1,
                api_backoff_seconds=0,
                resources={},
                clickstream_input=root / "unused.csv",
            )

            summary = materialize_feature_store(
                config,
                logging.getLogger("test"),
                version="v1",
            )

            self.assertTrue(
                Path(summary["feature_store_database"]).exists()
            )
            self.assertTrue(Path(summary["registry_path"]).exists())
            self.assertEqual(summary["views"]["user_activity"], 1)

            training = retrieve_features(
                config=config,
                feature_view="user_activity",
                key_values={"user_id": 1},
                consumer="training",
                version="v1",
            )
            inference = retrieve_features(
                config=config,
                feature_view="user_activity",
                key_values={"user_id": 1},
                consumer="inference",
                version="v1",
            )

            self.assertEqual(training["version"], "v1")
            self.assertEqual(inference["version"], "v1")
            self.assertEqual(
                training["records"],
                inference["records"],
            )
            self.assertEqual(
                inference["records"][0]["interaction_count"],
                5,
            )


if __name__ == "__main__":
    unittest.main()