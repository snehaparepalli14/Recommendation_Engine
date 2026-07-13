"""DummyJSON collection ingestion."""

from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import datetime

from recomart.config import ProjectConfig
from recomart.ingestion.api_client import ApiClient
from recomart.storage import StoredArtifact, store_json_snapshot, utc_now


def ingest_resource(resource: str, config: ProjectConfig, client: ApiClient, logger: logging.Logger, captured_at: datetime | None = None) -> tuple[StoredArtifact, dict[str, object]]:
    if resource not in config.resources:
        raise ValueError(f"Unsupported DummyJSON resource: {resource}")
    instant = captured_at or utc_now()
    url = f"{config.api_base_url}{config.resources[resource]}"
    payload = client.get_json(url)
    if not isinstance(payload, dict) or not isinstance(payload.get(resource), list):
        raise ValueError(f"Expected a JSON object with a '{resource}' list")
    artifact = store_json_snapshot(config.raw_dir, "dummyjson", resource, payload, len(payload[resource]), instant)
    logger.info("resource_ingested source=dummyjson entity=%s records=%s path=%s", resource, artifact.record_count, artifact.path)
    metadata: dict[str, object] = {"source": "dummyjson", "entity": resource, "source_location": url, "status": "success", **asdict(artifact)}
    metadata["path"] = str(artifact.path)
    return artifact, metadata

