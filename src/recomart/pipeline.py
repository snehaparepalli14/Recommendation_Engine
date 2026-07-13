from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from recomart.config import ProjectConfig
from recomart.ingestion.api_client import ApiClient
from recomart.ingestion.clickstream import ingest_clickstream
from recomart.ingestion.dummyjson import ingest_resource
from recomart.storage import store_run_manifest
from recomart.validation.quality_gate import validate_latest_raw_snapshots
from recomart.preparation.prepare_eda import run_preparation_and_eda
from recomart.features.warehouse import run_feature_engineering
from recomart.feature_store.store import (
    materialize_feature_store,
    retrieve_features,
)
from recomart.models.recommender import (
    recommend_products,
    train_recommender,
)


def run_ingestion(
    config: ProjectConfig,
    logger: logging.Logger,
) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc)
    run_id = str(uuid.uuid4())

    logger.info("pipeline_started run_id=%s stage=ingestion", run_id)

    client = ApiClient(
        timeout_seconds=config.api_timeout_seconds,
        max_attempts=config.api_max_attempts,
        backoff_seconds=config.api_backoff_seconds,
        logger=logger,
    )

    sources: list[dict[str, object]] = []
    failures: list[Exception] = []

    for resource in ("products", "users", "carts"):
        try:
            _, metadata = ingest_resource(
                resource,
                config,
                client,
                logger,
            )
            sources.append(metadata)

        except Exception as exc:
            logger.exception(
                "resource_ingestion_failed source=dummyjson entity=%s",
                resource,
            )
            sources.append(
                {
                    "source": "dummyjson",
                    "entity": resource,
                    "source_location": (
                        f"{config.api_base_url}"
                        f"{config.resources[resource]}"
                    ),
                    "status": "failed",
                    "error": repr(exc),
                }
            )
            failures.append(exc)

    try:
        _, metadata = ingest_clickstream(config, logger)
        sources.append(metadata)

    except Exception as exc:
        logger.exception(
            "resource_ingestion_failed source=clickstream entity=events"
        )
        sources.append(
            {
                "source": "clickstream",
                "entity": "events",
                "source_location": str(config.clickstream_input),
                "status": "failed",
                "error": repr(exc),
            }
        )
        failures.append(exc)

    finished_at = datetime.now(timezone.utc)

    manifest: dict[str, Any] = {
        "run_id": run_id,
        "stage": "ingestion",
        "status": "failed" if failures else "success",
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "sources": sources,
    }

    manifest_artifact = store_run_manifest(
        config.raw_dir,
        run_id,
        manifest,
        finished_at,
    )

    manifest["manifest_path"] = str(manifest_artifact.path)

    logger.info(
        "pipeline_finished run_id=%s stage=ingestion status=%s manifest=%s",
        run_id,
        manifest["status"],
        manifest_artifact.path,
    )

    if failures:
        raise RuntimeError(
            f"Ingestion completed with {len(failures)} failed source(s); "
            f"see {manifest_artifact.path}"
        )

    return manifest


def run_validation(
    config: ProjectConfig,
    logger: logging.Logger,
) -> dict[str, Any]:
    """Run Stage 2 against the latest immutable raw snapshots."""
    return validate_latest_raw_snapshots(config, logger)

def run_preparation_eda(
    config: ProjectConfig,
    logger: logging.Logger,
) -> dict[str, Any]:
    """Run Stage 3 data preparation and exploratory data analysis."""
    return run_preparation_and_eda(config, logger)

def run_features(
    config: ProjectConfig,
    logger: logging.Logger,
) -> dict[str, Any]:
    """Run Stage 4 warehouse loading and feature engineering."""
    return run_feature_engineering(config, logger)

def run_feature_store(
    config: ProjectConfig,
    logger: logging.Logger,
) -> dict[str, Any]:
    """Materialise version v1 of the custom feature store."""
    return materialize_feature_store(config, logger, version="v1")


def get_user_features(
    config: ProjectConfig,
    user_id: int,
    consumer: str,
) -> dict[str, Any]:
    """Retrieve versioned user features for training or inference."""
    return retrieve_features(
        config=config,
        feature_view="user_activity",
        key_values={"user_id": user_id},
        consumer=consumer,
        version="v1",
    )

def run_model_training(
    config: ProjectConfig,
    logger: logging.Logger,
    rank: int,
    top_k: int,
    seed: int,
) -> dict[str, Any]:
    """Run Task 9 collaborative-model training and evaluation."""
    return train_recommender(
        config=config,
        logger=logger,
        rank=rank,
        top_k=top_k,
        seed=seed,
    )


def get_recommendations(
    config: ProjectConfig,
    user_id: int,
    limit: int,
) -> dict[str, Any]:
    """Return a Top-K recommendation inference response."""
    return recommend_products(
        config=config,
        user_id=user_id,
        limit=limit,
    )

def run_orchestration(
    skip_ingestion: bool,
    rank: int,
    top_k: int,
    seed: int,
) -> dict[str, Any]:
    """Run the Prefect-managed end-to-end workflow."""
    from recomart.orchestration.prefect_flow import run_recomart_flow

    return run_recomart_flow(
        skip_ingestion=skip_ingestion,
        rank=rank,
        top_k=top_k,
        seed=seed,
    )