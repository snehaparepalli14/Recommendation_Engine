"""Immutable local raw-data storage and audit metadata utilities."""

from __future__ import annotations

import csv
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class StoredArtifact:
    path: Path
    record_count: int
    sha256: str


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def partition_directory(root: Path, source: str, entity: str, captured_at: datetime) -> Path:
    return root / source / entity / f"ingestion_date={captured_at.date().isoformat()}"


def _file_stamp(captured_at: datetime) -> str:
    return captured_at.strftime("%Y%m%dT%H%M%S%fZ")


def _checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_then_publish(destination: Path, write_file: Any) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    try:
        write_file(temporary)
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def store_json_snapshot(root: Path, source: str, entity: str, payload: Any, record_count: int, captured_at: datetime | None = None) -> StoredArtifact:
    instant = captured_at or utc_now()
    destination = partition_directory(root, source, entity, instant) / f"{entity}_{_file_stamp(instant)}.json"

    def write_file(path: Path) -> None:
        with path.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")

    _write_then_publish(destination, write_file)
    return StoredArtifact(destination, record_count, _checksum(destination))


def store_csv_snapshot(root: Path, source: str, entity: str, fieldnames: list[str], rows: Iterable[dict[str, str]], captured_at: datetime | None = None) -> StoredArtifact:
    instant = captured_at or utc_now()
    destination = partition_directory(root, source, entity, instant) / f"{entity}_{_file_stamp(instant)}.csv"
    materialized_rows = list(rows)

    def write_file(path: Path) -> None:
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(materialized_rows)

    _write_then_publish(destination, write_file)
    return StoredArtifact(destination, len(materialized_rows), _checksum(destination))


def store_run_manifest(root: Path, run_id: str, manifest: dict[str, Any], captured_at: datetime | None = None) -> StoredArtifact:
    return store_json_snapshot(root, "manifests", "pipeline_runs", manifest, len(manifest.get("sources", [])), captured_at)

