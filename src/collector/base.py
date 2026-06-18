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
from src.domain.context import OperationContext
from src.storage.factory import create_storage_provider
from src.storage.provider import StorageProvider

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
    allow_mock_fallback: bool = True

    def __init__(
        self,
        settings: Settings | None = None,
        context: OperationContext | None = None,
        storage: StorageProvider | None = None,
        credential: Any | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.settings.ensure_data_dirs()
        self.context = context or OperationContext.create(
            self.settings.effective_tenant_id,
            self.settings.effective_subscription_id,
        )
        self.storage = storage or create_storage_provider(self.settings)
        self.credential = credential
        self.mock_data_dir = self.settings.project_root / "tests" / "mock_data"
        self.logger = logging.getLogger(f"{__name__}.{self.collector_name}")

    @property
    def mock_file_path(self) -> Path:
        return self.mock_data_dir / self.mock_filename

    def collect(self) -> IngestionResult:
        """Execute full collect → validate → ingest → save pipeline."""
        self.logger.info("Starting collection for %s", self.collector_name)
        start = time.perf_counter()

        is_live = False
        try:
            collection_mode = self.settings.collection_mode.strip().lower()
            if collection_mode not in {"auto", "live", "mock"}:
                raise CollectorError(
                    f"Unsupported COLLECTION_MODE={self.settings.collection_mode!r}"
                )
            use_live = collection_mode == "live" or (
                collection_mode == "auto"
                and (
                    self.credential is not None
                    or self.settings.azure_credentials_configured
                )
            )
            if use_live:
                if (
                    self.credential is None
                    and not self.settings.azure_credentials_configured
                ):
                    raise CollectorError(
                        f"{self.collector_name}: live collection requires an Azure credential"
                    )
                try:
                    self.logger.info("Fetching LIVE data from Azure API...")
                    raw_payload = self._fetch_live_data()
                    is_live = True
                except NotImplementedError:
                    if not self.allow_mock_fallback:
                        raise
                    self.logger.warning("Live fetch not implemented for %s. Falling back to mock.", self.collector_name)
                    raw_payload = self._load_mock_json()
                except Exception as exc:
                    if not self.allow_mock_fallback:
                        raise CollectorError(
                            f"{self.collector_name}: live collection failed: {exc}"
                        ) from exc
                    self.logger.error("Live fetch failed for %s: %s. Falling back to mock.", self.collector_name, exc)
                    raw_payload = self._load_mock_json()
            else:
                raw_payload = self._load_mock_json()

            validated = self._validate_schema(raw_payload)
            enriched = self._simulate_api_ingestion(validated, is_live=is_live)
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

    def _fetch_live_data(self) -> dict[str, Any]:
        """Fetch live data using Azure SDK and format into the expected raw dictionary payload."""
        raise NotImplementedError(f"{self.collector_name} live fetch not implemented.")

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

    def _simulate_api_ingestion(self, validated: T, is_live: bool = False) -> dict[str, Any]:
        """Wrap validated data with Azure API–style ingestion envelope."""
        now = datetime.now(timezone.utc)
        ingestion_id = f"{self.collector_name}-{now.strftime('%Y%m%d%H%M%S%f')}"

        body = validated.model_dump(mode="json", by_alias=True)
        body["ingestion"] = {
            "ingestionId": ingestion_id,
            "ingestedAt": now.isoformat(),
            "collector": self.collector_name,
            "simulatedApi": not is_live,
            "mockSource": None if is_live else self.mock_filename,
            "subscriptionId": self._extract_subscription_id(validated),
        }
        body["context"] = self.context.document_fields()
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
            self.storage.raw_payloads.save(
                self.context.tenant_id,
                self.context.subscription_id,
                self.context.collection_run_id,
                self.output_prefix,
                enriched,
            )
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
