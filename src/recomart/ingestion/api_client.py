"""Small retrying HTTP client used for REST ingestion."""

from __future__ import annotations

import json
import logging
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ApiIngestionError(RuntimeError):
    """Raised when an API endpoint cannot provide a usable response."""


class ApiClient:
    def __init__(self, timeout_seconds: int, max_attempts: int, backoff_seconds: float, logger: logging.Logger) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts
        self.backoff_seconds = backoff_seconds
        self.logger = logger

    def get_json(self, url: str) -> Any:
        failure: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                self.logger.info("api_request_started url=%s attempt=%s", url, attempt)
                request = Request(url, headers={"Accept": "application/json", "User-Agent": "RecoMartPipeline/1.0"})
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    if not 200 <= getattr(response, "status", 200) < 300:
                        raise ApiIngestionError(f"Unexpected HTTP status: {response.status}")
                    payload = json.loads(response.read().decode("utf-8"))
                self.logger.info("api_request_succeeded url=%s attempt=%s", url, attempt)
                return payload
            except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, ApiIngestionError) as exc:
                failure = exc
                self.logger.warning("api_request_failed url=%s attempt=%s error=%r", url, attempt, exc)
                if attempt < self.max_attempts:
                    time.sleep(self.backoff_seconds * (2 ** (attempt - 1)))
        raise ApiIngestionError(f"Request failed after {self.max_attempts} attempt(s): {url}") from failure

