"""Local clickstream CSV ingestion."""

from __future__ import annotations

import csv
import logging
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from recomart.config import ProjectConfig
from recomart.storage import StoredArtifact, store_csv_snapshot, utc_now


REQUIRED_COLUMNS = {"event_id", "user_id", "product_id", "event_type", "event_timestamp", "session_id"}


def ingest_clickstream(config: ProjectConfig, logger: logging.Logger, input_path: Path | None = None, captured_at: datetime | None = None) -> tuple[StoredArtifact, dict[str, object]]:
    source_path = input_path or config.clickstream_input
    with source_path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames or []
        missing = sorted(REQUIRED_COLUMNS.difference(fields))
        if missing:
            raise ValueError(f"Clickstream CSV is missing required columns: {missing}")
        rows = list(reader)
    instant = captured_at or utc_now()
    artifact = store_csv_snapshot(config.raw_dir, "clickstream", "events", fields, rows, instant)
    logger.info("resource_ingested source=clickstream entity=events records=%s path=%s", artifact.record_count, artifact.path)
    metadata: dict[str, object] = {"source": "clickstream", "entity": "events", "source_location": str(source_path), "status": "success", **asdict(artifact)}
    metadata["path"] = str(artifact.path)
    return artifact, metadata

