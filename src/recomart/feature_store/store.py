"""Versioned feature-store materialisation and retrieval."""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb

from recomart.config import ProjectConfig


FEATURE_VIEWS: dict[str, dict[str, Any]] = {
    "user_activity": {
        "entity": "user",
        "source_table": "feature_user_activity",
        "key_columns": ["user_id"],
        "description": (
            "User activity, quantity, active-day, and average-rating "
            "features derived from observed interactions."
        ),
    },
    "product_popularity": {
        "entity": "product",
        "source_table": "feature_product_popularity",
        "key_columns": ["product_id"],
        "description": (
            "Product popularity, unique-user, quantity, category, "
            "price, and catalogue-rating features."
        ),
    },
    "user_product": {
        "entity": "user_product",
        "source_table": "feature_user_product",
        "key_columns": ["user_id", "product_id"],
        "description": (
            "User-product implicit-feedback features, including the "
            "event-weighted interaction score."
        ),
    },
    "product_cooccurrence": {
        "entity": "product_pair",
        "source_table": "feature_product_cooccurrence",
        "key_columns": ["product_id_left", "product_id_right"],
        "description": (
            "Cart-based product-pair co-occurrence features."
        ),
    },
}


def validate_version(version: str) -> str:
    if not re.fullmatch(r"v[0-9]+", version):
        raise ValueError("Feature-store version must use the form v1, v2, ...")

    return version


def sql_path(path: Path) -> str:
    return path.resolve().as_posix().replace("'", "''")


def feature_store_paths(
    config: ProjectConfig,
    version: str,
) -> tuple[Path, Path, Path]:
    validate_version(version)

    root = config.project_root / "data" / "feature_store"
    registry_dir = root / "registry"
    database_path = root / "recomart_feature_store.db"
    registry_path = registry_dir / f"feature_registry_{version}.json"

    return database_path, registry_dir, registry_path


def storage_table_name(feature_view: str, version: str) -> str:
    validate_version(version)

    if feature_view not in FEATURE_VIEWS:
        raise ValueError(f"Unknown feature view: {feature_view}")

    return f"{feature_view}_{version}"


def table_columns(
    connection: duckdb.DuckDBPyConnection,
    table_name: str,
) -> list[str]:
    return [
        str(row[0])
        for row in connection.execute(
            f"DESCRIBE {table_name}"
        ).fetchall()
    ]


def materialize_feature_store(
    config: ProjectConfig,
    logger: logging.Logger,
    version: str = "v1",
) -> dict[str, Any]:
    """Copy Stage 4 features into a versioned feature-store database."""
    validate_version(version)

    warehouse_path = (
        config.project_root
        / "data"
        / "warehouse"
        / "recomart.db"
    )

    if not warehouse_path.exists():
        raise FileNotFoundError(
            "Stage 4 warehouse does not exist. Run build-features first."
        )

    database_path, registry_dir, registry_path = feature_store_paths(
        config,
        version,
    )
    database_path.parent.mkdir(parents=True, exist_ok=True)
    registry_dir.mkdir(parents=True, exist_ok=True)

    run_id = str(uuid.uuid4())
    generated_at = datetime.now(timezone.utc).isoformat()

    logger.info(
        "pipeline_started run_id=%s stage=feature_store version=%s",
        run_id,
        version,
    )

    connection = duckdb.connect(str(database_path))
    view_registry: list[dict[str, Any]] = []

    try:
        connection.execute(
            f"""
            ATTACH '{sql_path(warehouse_path)}'
            AS warehouse (READ_ONLY)
            """
        )

        for view_name, specification in FEATURE_VIEWS.items():
            target_table = storage_table_name(view_name, version)
            source_table = str(specification["source_table"])

            connection.execute(
                f"""
                CREATE OR REPLACE TABLE {target_table} AS
                SELECT *
                FROM warehouse.{source_table}
                """
            )

            columns = table_columns(connection, target_table)
            key_columns = list(specification["key_columns"])

            view_registry.append(
                {
                    "name": view_name,
                    "entity": specification["entity"],
                    "version": version,
                    "source_table": source_table,
                    "storage_table": target_table,
                    "key_columns": key_columns,
                    "feature_columns": [
                        column
                        for column in columns
                        if column not in key_columns
                    ],
                    "description": specification["description"],
                    "row_count": int(
                        connection.execute(
                            f"SELECT COUNT(*) FROM {target_table}"
                        ).fetchone()[0]
                    ),
                }
            )

    finally:
        connection.close()

    registry: dict[str, Any] = {
        "project": "RecoMart",
        "feature_store": "custom_duckdb_registry",
        "version": version,
        "run_id": run_id,
        "generated_at": generated_at,
        "warehouse_source": str(warehouse_path),
        "feature_store_database": str(database_path),
        "feature_views": view_registry,
        "retrieval_policy": (
            "Training and inference must request the same named feature "
            "view and explicit version."
        ),
    }

    with registry_path.open("w", encoding="utf-8") as handle:
        json.dump(registry, handle, indent=2)
        handle.write("\n")

    summary = {
        "project": "RecoMart",
        "stage": "feature_store",
        "run_id": run_id,
        "version": version,
        "feature_store_database": str(database_path),
        "registry_path": str(registry_path),
        "views": {
            view["name"]: view["row_count"]
            for view in view_registry
        },
    }

    logger.info(
        "pipeline_finished run_id=%s stage=feature_store version=%s",
        run_id,
        version,
    )

    return summary


def load_registry(
    config: ProjectConfig,
    version: str = "v1",
) -> dict[str, Any]:
    _, _, registry_path = feature_store_paths(config, version)

    if not registry_path.exists():
        raise FileNotFoundError(
            f"Feature-store registry does not exist: {registry_path}. "
            "Run materialize-feature-store first."
        )

    with registry_path.open("r", encoding="utf-8") as handle:
        return dict(json.load(handle))


def retrieve_features(
    config: ProjectConfig,
    feature_view: str,
    key_values: dict[str, int],
    consumer: str,
    version: str = "v1",
) -> dict[str, Any]:
    """Retrieve one versioned feature-view row for training or inference."""
    if consumer not in {"training", "inference"}:
        raise ValueError("consumer must be 'training' or 'inference'")

    registry = load_registry(config, version)
    views = {
        str(view["name"]): view
        for view in registry["feature_views"]
    }

    if feature_view not in views:
        raise ValueError(f"Feature view is not registered: {feature_view}")

    view = views[feature_view]
    key_columns = list(view["key_columns"])

    if set(key_values) != set(key_columns):
        raise ValueError(
            f"{feature_view} requires exactly these keys: {key_columns}"
        )

    database_path = Path(str(registry["feature_store_database"]))

    if not database_path.exists():
        raise FileNotFoundError(
            f"Feature-store database does not exist: {database_path}"
        )

    filters = " AND ".join(
        f"{column} = ?"
        for column in key_columns
    )
    values = [key_values[column] for column in key_columns]

    connection = duckdb.connect(str(database_path), read_only=True)

    try:
        cursor = connection.execute(
            f"""
            SELECT *
            FROM {view["storage_table"]}
            WHERE {filters}
            """,
            values,
        )
        columns = [
            description[0]
            for description in cursor.description
        ]
        records = [
            dict(zip(columns, row))
            for row in cursor.fetchall()
        ]
    finally:
        connection.close()

    return {
        "consumer": consumer,
        "feature_view": feature_view,
        "version": version,
        "keys": key_values,
        "records": records,
    }