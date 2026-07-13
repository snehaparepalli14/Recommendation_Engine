"""Stage 4 analytics warehouse and recommendation feature engineering."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb

from recomart.config import ProjectConfig


PROCESSED_DATASETS = (
    "products",
    "users",
    "carts",
    "cart_items",
    "events",
    "interactions",
    "product_popularity",
)


def latest_processed_file(processed_dir: Path, dataset: str) -> Path:
    candidates = list(
        processed_dir.glob(
            f"preparation_date=*/{dataset}_*.parquet"
        )
    )

    if not candidates:
        raise FileNotFoundError(
            f"No processed Parquet file found for dataset: {dataset}"
        )

    return max(candidates, key=lambda path: path.name)


def sql_path(path: Path) -> str:
    """Return a SQL-safe, forward-slash path."""
    return path.resolve().as_posix().replace("'", "''")


def load_parquet_table(
    connection: duckdb.DuckDBPyConnection,
    table_name: str,
    source_path: Path,
) -> None:
    connection.execute(
        f"""
        CREATE OR REPLACE TABLE {table_name} AS
        SELECT *
        FROM read_parquet('{sql_path(source_path)}')
        """
    )


def build_feature_tables(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        CREATE OR REPLACE TABLE feature_user_activity AS
        SELECT
            users.user_id,
            COUNT(interactions.product_id) AS interaction_count,
            COUNT(DISTINCT interactions.product_id)
                AS distinct_product_count,
            COALESCE(SUM(interactions.quantity), 0)
                AS total_interaction_quantity,
            COALESCE(
                AVG(products.rating),
                0.0
            ) AS average_interacted_product_rating,
            COUNT(
                DISTINCT CAST(interactions.event_timestamp AS DATE)
            ) AS active_event_days
        FROM dim_users AS users
        LEFT JOIN fact_interactions AS interactions
            ON users.user_id = interactions.user_id
        LEFT JOIN dim_products AS products
            ON interactions.product_id = products.product_id
        GROUP BY users.user_id
        """
    )

    connection.execute(
        """
        CREATE OR REPLACE TABLE feature_product_popularity AS
        SELECT
            products.product_id,
            products.category,
            products.category_code,
            products.price,
            products.price_normalized,
            products.rating AS catalogue_rating,
            COUNT(interactions.user_id) AS interaction_count,
            COUNT(DISTINCT interactions.user_id) AS unique_user_count,
            COALESCE(SUM(interactions.quantity), 0)
                AS total_interaction_quantity
        FROM dim_products AS products
        LEFT JOIN fact_interactions AS interactions
            ON products.product_id = interactions.product_id
        GROUP BY
            products.product_id,
            products.category,
            products.category_code,
            products.price,
            products.price_normalized,
            products.rating
        """
    )

    connection.execute(
        """
        CREATE OR REPLACE TABLE feature_user_product AS
        SELECT
            user_id,
            product_id,
            COUNT(*) AS interaction_count,
            SUM(quantity) AS total_quantity,
            SUM(
                CASE event_type
                    WHEN 'view' THEN 1
                    WHEN 'click' THEN 2
                    WHEN 'cart' THEN 3
                    WHEN 'purchase' THEN 4
                    ELSE 1
                END
            ) AS weighted_interaction_score,
            MAX(event_timestamp) AS last_event_timestamp
        FROM fact_interactions
        GROUP BY user_id, product_id
        """
    )

    connection.execute(
        """
        CREATE OR REPLACE TABLE feature_product_cooccurrence AS
        SELECT
            first_item.product_id AS product_id_left,
            second_item.product_id AS product_id_right,
            COUNT(DISTINCT first_item.cart_id) AS cart_cooccurrence_count
        FROM fact_cart_items AS first_item
        INNER JOIN fact_cart_items AS second_item
            ON first_item.cart_id = second_item.cart_id
            AND first_item.product_id < second_item.product_id
        GROUP BY
            first_item.product_id,
            second_item.product_id
        """
    )

    connection.execute(
        """
        CREATE OR REPLACE TABLE feature_metadata AS
        SELECT *
        FROM (
            VALUES
                (
                    'interaction_count',
                    'user',
                    'fact_interactions',
                    'Number of observed user-product interactions.'
                ),
                (
                    'average_interacted_product_rating',
                    'user',
                    'fact_interactions, dim_products',
                    'Average catalogue rating of products observed for a user.'
                ),
                (
                    'weighted_interaction_score',
                    'user_product',
                    'fact_interactions',
                    'Event-weighted implicit preference score: view=1, click=2, cart=3, purchase=4.'
                ),
                (
                    'cart_cooccurrence_count',
                    'product_pair',
                    'fact_cart_items',
                    'Number of distinct carts containing both products.'
                ),
                (
                    'interaction_count',
                    'product',
                    'fact_interactions',
                    'Number of observed interactions for a product.'
                )
        ) AS metadata(
            feature_name,
            entity,
            source_tables,
            description
        )
        """
    )


def table_counts(
    connection: duckdb.DuckDBPyConnection,
) -> dict[str, int]:
    tables = (
        "dim_products",
        "dim_users",
        "fact_carts",
        "fact_cart_items",
        "fact_events",
        "fact_interactions",
        "feature_user_activity",
        "feature_product_popularity",
        "feature_user_product",
        "feature_product_cooccurrence",
        "feature_metadata",
    )

    return {
        table_name: int(
            connection.execute(
                f"SELECT COUNT(*) FROM {table_name}"
            ).fetchone()[0]
        )
        for table_name in tables
    }


def run_feature_engineering(
    config: ProjectConfig,
    logger: logging.Logger,
) -> dict[str, Any]:
    """Load Stage 3 data into DuckDB and create recommendation features."""
    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc)

    logger.info(
        "pipeline_started run_id=%s stage=feature_engineering",
        run_id,
    )

    processed_dir = config.project_root / "data" / "processed"
    source_paths = {
        dataset: latest_processed_file(processed_dir, dataset)
        for dataset in PROCESSED_DATASETS
    }

    warehouse_dir = config.project_root / "data" / "warehouse"
    warehouse_dir.mkdir(parents=True, exist_ok=True)
    database_path = warehouse_dir / "recomart.db"

    reports_dir = config.project_root / "reports" / "features"
    reports_dir.mkdir(parents=True, exist_ok=True)
    summary_path = reports_dir / f"feature_summary_{run_id}.json"

    connection = duckdb.connect(str(database_path))

    try:
        load_parquet_table(
            connection,
            "dim_products",
            source_paths["products"],
        )
        load_parquet_table(
            connection,
            "dim_users",
            source_paths["users"],
        )
        load_parquet_table(
            connection,
            "fact_carts",
            source_paths["carts"],
        )
        load_parquet_table(
            connection,
            "fact_cart_items",
            source_paths["cart_items"],
        )
        load_parquet_table(
            connection,
            "fact_events",
            source_paths["events"],
        )
        load_parquet_table(
            connection,
            "fact_interactions",
            source_paths["interactions"],
        )

        build_feature_tables(connection)
        counts = table_counts(connection)

    finally:
        connection.close()

    summary: dict[str, Any] = {
        "project": "RecoMart",
        "stage": "feature_engineering_and_transformation",
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "warehouse_database": str(database_path),
        "source_files": {
            dataset: str(path)
            for dataset, path in source_paths.items()
        },
        "table_row_counts": counts,
        "feature_logic": {
            "user_activity": (
                "Counts interactions, distinct products, total quantity, "
                "active event days, and the average catalogue rating of "
                "products interacted with."
            ),
            "product_popularity": (
                "Counts interactions, unique users, total quantity, and "
                "retains category, price, and catalogue-rating attributes."
            ),
            "user_product": (
                "Calculates a weighted implicit-feedback score using "
                "view=1, click=2, cart=3, purchase=4."
            ),
            "product_cooccurrence": (
                "Counts product pairs appearing together in distinct carts."
            ),
        },
        "summary_report": str(summary_path),
    }

    with summary_path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)
        handle.write("\n")

    logger.info(
        "pipeline_finished run_id=%s stage=feature_engineering "
        "database=%s",
        run_id,
        database_path,
    )

    return summary