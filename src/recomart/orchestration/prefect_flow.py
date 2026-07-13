"""Prefect orchestration for the complete RecoMart pipeline."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from prefect import flow, get_run_logger, task

from recomart.config import ProjectConfig, load_config
from recomart.logging_config import configure_logging
from recomart.pipeline import (
    run_feature_store,
    run_features,
    run_ingestion,
    run_model_training,
    run_preparation_eda,
    run_validation,
)


def pipeline_context() -> tuple[ProjectConfig, logging.Logger]:
    config = load_config()
    logger = configure_logging(config.log_file)
    return config, logger


def write_orchestration_summary(
    config: ProjectConfig,
    run_id: str,
    status: str,
    stages: dict[str, Any],
    error: str | None = None,
) -> Path:
    output_directory = (
        config.project_root
        / "reports"
        / "orchestration"
        / f"run_id={run_id}"
    )
    output_directory.mkdir(parents=True, exist_ok=True)

    summary_path = output_directory / "orchestration_summary.json"

    payload = {
        "project": "RecoMart",
        "orchestrator": "Prefect",
        "run_id": run_id,
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stages": stages,
        "error": error,
    }

    with summary_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, default=str)
        handle.write("\n")

    return summary_path


@task(
    name="ingest_data",
    retries=2,
    retry_delay_seconds=10,
)
def ingest_data() -> dict[str, Any]:
    config, logger = pipeline_context()
    return run_ingestion(config, logger)


@task(
    name="validate_data",
    retries=1,
    retry_delay_seconds=5,
)
def validate_data() -> dict[str, Any]:
    config, logger = pipeline_context()
    return run_validation(config, logger)


@task(
    name="prepare_eda",
    retries=1,
    retry_delay_seconds=5,
)
def prepare_eda() -> dict[str, Any]:
    config, logger = pipeline_context()
    return run_preparation_eda(config, logger)


@task(
    name="build_features",
    retries=1,
    retry_delay_seconds=5,
)
def build_features() -> dict[str, Any]:
    config, logger = pipeline_context()
    return run_features(config, logger)


@task(
    name="materialize_feature_store",
    retries=1,
    retry_delay_seconds=5,
)
def materialize_feature_store() -> dict[str, Any]:
    config, logger = pipeline_context()
    return run_feature_store(config, logger)


@task(
    name="train_recommender",
    retries=1,
    retry_delay_seconds=5,
)
def train_recommender(
    rank: int,
    top_k: int,
    seed: int,
) -> dict[str, Any]:
    config, logger = pipeline_context()
    return run_model_training(
        config=config,
        logger=logger,
        rank=rank,
        top_k=top_k,
        seed=seed,
    )


@flow(
    name="recomart_end_to_end_pipeline",
    log_prints=True,
)
def run_recomart_flow(
    skip_ingestion: bool = False,
    rank: int = 12,
    top_k: int = 10,
    seed: int = 42,
) -> dict[str, Any]:
    """Run ordered ingestion-to-model-training workflow with Prefect."""
    config = load_config()
    flow_logger = get_run_logger()
    run_id = str(uuid.uuid4())
    stages: dict[str, Any] = {}

    flow_logger.info(
        "orchestration_started run_id=%s skip_ingestion=%s",
        run_id,
        skip_ingestion,
    )

    try:
        if skip_ingestion:
            stages["ingestion"] = {
                "status": "skipped",
                "reason": (
                    "Existing raw snapshots were intentionally reused."
                ),
            }
        else:
            stages["ingestion"] = ingest_data()

        stages["validation"] = validate_data()
        stages["preparation_eda"] = prepare_eda()
        stages["feature_engineering"] = build_features()
        stages["feature_store"] = materialize_feature_store()
        stages["model_training"] = train_recommender(
            rank=rank,
            top_k=top_k,
            seed=seed,
        )

    except Exception as exc:
        report_path = write_orchestration_summary(
            config=config,
            run_id=run_id,
            status="failed",
            stages=stages,
            error=repr(exc),
        )
        flow_logger.exception(
            "orchestration_failed run_id=%s report=%s",
            run_id,
            report_path,
        )
        raise

    report_path = write_orchestration_summary(
        config=config,
        run_id=run_id,
        status="success",
        stages=stages,
    )

    flow_logger.info(
        "orchestration_finished run_id=%s report=%s",
        run_id,
        report_path,
    )

    return {
        "project": "RecoMart",
        "stage": "pipeline_orchestration",
        "orchestrator": "Prefect",
        "run_id": run_id,
        "status": "success",
        "orchestration_report": str(report_path),
        "stages": list(stages),
    }