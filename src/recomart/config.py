"""Project configuration loaded from the repository JSON file."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ProjectConfig:
    project_root: Path
    api_base_url: str
    api_timeout_seconds: int
    api_max_attempts: int
    api_backoff_seconds: float
    resources: dict[str, str]
    clickstream_input: Path

    @property
    def raw_dir(self) -> Path:
        return self.project_root / "data" / "raw"

    @property
    def log_file(self) -> Path:
        return self.project_root / "logs" / "pipeline.log"

    @property
    def prepared_dir(self) -> Path:
        return self.project_root / "data" / "prepared"

    @property
    def quarantine_dir(self) -> Path:
        return self.project_root / "data" / "quarantine"

    @property
    def reports_dir(self) -> Path:
        return self.project_root / "reports" / "data_quality"


def load_config(config_path: Path | None = None) -> ProjectConfig:
    project_root = Path(__file__).resolve().parents[2]
    source_path = config_path or project_root / "config" / "project.json"

    with source_path.open("r", encoding="utf-8") as handle:
        values: dict[str, Any] = json.load(handle)

    return ProjectConfig(
        project_root=project_root,
        api_base_url=str(values["api_base_url"]).rstrip("/"),
        api_timeout_seconds=int(values["api_timeout_seconds"]),
        api_max_attempts=int(values["api_max_attempts"]),
        api_backoff_seconds=float(values["api_backoff_seconds"]),
        resources=dict(values["resources"]),
        clickstream_input=project_root / str(values["clickstream_input"]),
    )