"""Base collector: mock ingestion, schema validation, timestamped persistence."""

from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError

from src.config import Settings, get_settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class CollectorError(Exception):
    """Base exception for collector failures."""


class MockDataNotFoundError(CollectorError):
    """Raised when a required mock JSON file is missing."""


class SchemaValidationError(CollectorError):
    """Raised when payload fails Pydantic schema validation."""

    def __init__(self, collector: str, errors: list[dict[str, Any]]) -> None:
        self.collector = collector
        self.errors = errors
        super().__init__(f"{collector}: schema validation failed ({len(errors)} errors)")


class IngestionResult(BaseModel):
    collector: str
    source_file: str
    ingestion_id: str
    ingested_at: str
    record_count: int
    output_path: str
    latest_path: str
    status: str = "success"


class BaseCollector(ABC, Generic[T]):
    """Loads mock Azure API payloads, validates, enriches, and persists to data/raw/."""

    collector_name: str
    mock_filename: str
    schema_model: type[T]
    output_prefix: str

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.settings.ensure_data_dirs()
        self.mock_data_dir = self.settings.project_root / "tests" / "mock_data"
        self.logger = logging.getLogger(f"{__name__}.{self.collector_name}")

    @property
    def mock_file_path(self) -> Path:
        return self.mock_data_dir / self.mock_filename

    def collect(self) -> IngestionResult:
        """Execute full collect → validate → ingest → save pipeline."""
        self.logger.info("Starting collection for %s", self.collector_name)
        start = time.perf_counter()

        try:
            raw_payload = self._load_mock_json()
            validated = self._validate_schema(raw_payload)
            enriched = self._simulate_api_ingestion(validated)
            output_path, latest_path = self._save_outputs(enriched, validated)

            elapsed = time.perf_counter() - start
            record_count = self._count_records(validated)
            result = IngestionResult(
                collector=self.collector_name,
                source_file=str(self.mock_file_path),
                ingestion_id=enriched["ingestion"]["ingestionId"],
                ingested_at=enriched["ingestion"]["ingestedAt"],
                record_count=record_count,
                output_path=str(output_path),
                latest_path=str(latest_path),
            )
            self.logger.info(
                "%s completed in %.2fs — %d records → %s",
                self.collector_name,
                elapsed,
                record_count,
                output_path.name,
            )
            return result

        except CollectorError:
            self.logger.exception("%s failed with collector error", self.collector_name)
            raise
        except Exception as exc:
            self.logger.exception("%s failed unexpectedly", self.collector_name)
            raise CollectorError(f"{self.collector_name}: {exc}") from exc

    def _load_mock_json(self) -> dict[str, Any]:
        path = self.mock_file_path
        if not path.exists():
            raise MockDataNotFoundError(
                f"{self.collector_name}: mock file not found at {path}"
            )
        try:
            text = path.read_text(encoding="utf-8")
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise CollectorError(
                f"{self.collector_name}: invalid JSON in {path.name}: {exc}"
            ) from exc

        if not isinstance(payload, dict):
            raise CollectorError(
                f"{self.collector_name}: root JSON must be an object, got {type(payload).__name__}"
            )

        self.logger.debug("Loaded mock payload from %s (%d bytes)", path, len(text))
        return payload

    def _validate_schema(self, payload: dict[str, Any]) -> T:
        try:
            validated = self.schema_model.model_validate(payload)
            self.logger.debug("%s schema validation passed", self.collector_name)
            return validated
        except ValidationError as exc:
            error_list = exc.errors()
            self.logger.error(
                "%s schema validation failed: %s",
                self.collector_name,
                error_list[:3],
            )
            raise SchemaValidationError(self.collector_name, error_list) from exc

    def _simulate_api_ingestion(self, validated: T) -> dict[str, Any]:
        """Wrap validated data with Azure API–style ingestion envelope."""
        now = datetime.now(timezone.utc)
        ingestion_id = f"{self.collector_name}-{now.strftime('%Y%m%d%H%M%S%f')}"

        body = validated.model_dump(mode="json", by_alias=True)
        body["ingestion"] = {
            "ingestionId": ingestion_id,
            "ingestedAt": now.isoformat(),
            "collector": self.collector_name,
            "simulatedApi": True,
            "mockSource": self.mock_filename,
            "subscriptionId": self._extract_subscription_id(validated),
        }
        self._apply_ingestion_transforms(body)
        return body

    def _save_outputs(
        self, enriched: dict[str, Any], validated: T
    ) -> tuple[Path, Path]:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        output_path = self.settings.raw_path / f"{self.output_prefix}_{timestamp}.json"
        latest_path = self.settings.raw_path / f"{self.output_prefix}_latest.json"
        meta_path = self.settings.raw_path / f"{self.output_prefix}_{timestamp}.meta.json"

        try:
            serialized = json.dumps(enriched, indent=2, default=str)
            output_path.write_text(serialized, encoding="utf-8")
            latest_path.write_text(serialized, encoding="utf-8")

            meta = {
                "collector": self.collector_name,
                "saved_at": datetime.now(timezone.utc).isoformat(),
                "record_count": self._count_records(validated),
                "source_mock": self.mock_filename,
                "output_file": output_path.name,
            }
            meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        except OSError as exc:
            raise CollectorError(
                f"{self.collector_name}: failed to write output: {exc}"
            ) from exc

        return output_path, latest_path

    @abstractmethod
    def _count_records(self, validated: T) -> int:
        """Return number of primary records in the validated payload."""

    def _apply_ingestion_transforms(self, body: dict[str, Any]) -> None:
        """Optional hook for collector-specific enrichment after validation."""

    @staticmethod
    def _extract_subscription_id(validated: T | dict[str, Any]) -> str:
        if isinstance(validated, dict):
            return str(validated.get("metadata", {}).get("subscriptionId", "unknown"))
        meta = getattr(validated, "metadata", None)
        if meta is None:
            return "unknown"
        return str(getattr(meta, "subscription_id", "unknown"))

    def load_latest_envelope(self) -> dict[str, Any]:
        latest = self.settings.raw_path / f"{self.output_prefix}_latest.json"
        if not latest.exists():
            raise FileNotFoundError(
                f"No latest output for {self.collector_name}. Run collect() first."
            )
        return json.loads(latest.read_text(encoding="utf-8"))
