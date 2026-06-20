"""Filesystem repository adapters for local and legacy-compatible runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence, TypeVar

from pydantic import BaseModel

from src.domain.ids import deterministic_id
from src.domain.models import (
    AzureSubscription,
    CostFact,
    Recommendation,
    ResourceFact,
    Tenant,
    TenantHealth,
    TenantUser,
    ServerSession,
)
from src.repositories.errors import RepositoryError, TenantScopeError
from src.repositories.results import WriteResult

T = TypeVar("T", bound=BaseModel)


def _require_tenant(tenant_id: str) -> None:
    if not tenant_id or not tenant_id.strip():
        raise TenantScopeError("tenantId is required")


def _validate_entities(tenant_id: str, entities: Sequence[BaseModel]) -> None:
    _require_tenant(tenant_id)
    if any(getattr(entity, "tenant_id", None) != tenant_id for entity in entities):
        raise TenantScopeError("All documents must match the repository tenantId")


def _safe_part(value: str) -> str:
    return value.replace("/", "_").replace("\\", "_").replace(":", "_")


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True), encoding="utf-8")


def _model(model: type[T], path: Path) -> T:
    document = _read_json(path)
    if document is None:
        raise RepositoryError(f"Document not found: {path}")
    return model.model_validate(document)


class _FileRepositoryBase:
    def __init__(self, root: Path, collection: str) -> None:
        self.root = Path(root)
        self.collection = collection

    def _tenant_dir(self, tenant_id: str) -> Path:
        _require_tenant(tenant_id)
        return (
            self.root
            / "tenants"
            / _safe_part(tenant_id)
            / self.collection
        )

    def _path(self, tenant_id: str, item_id: str) -> Path:
        return self._tenant_dir(tenant_id) / f"{_safe_part(item_id)}.json"

    def _rows(self, tenant_id: str) -> list[dict[str, Any]]:
        tenant_dir = self._tenant_dir(tenant_id)
        if not tenant_dir.exists():
            return []
        return [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(tenant_dir.glob("*.json"))
        ]

    def delete_tenant(self, tenant_id: str) -> int:
        tenant_dir = self.root / "tenants" / _safe_part(tenant_id)
        if not tenant_dir.exists():
            return 0
        count = sum(1 for path in tenant_dir.rglob("*.json") if path.is_file())
        import shutil

        shutil.rmtree(tenant_dir)
        return count


class FileTenantRepository(_FileRepositoryBase):
    def __init__(self, root: Path) -> None:
        super().__init__(root, "tenants")

    def upsert(self, tenant_id: str, entity: Tenant) -> WriteResult:
        _validate_entities(tenant_id, [entity])
        path = self._path(tenant_id, tenant_id)
        existed = path.exists()
        _write_json(path, entity.model_dump(by_alias=True, mode="json"))
        return WriteResult(inserted=0 if existed else 1, updated=1 if existed else 0, path=str(path))

    def get(self, tenant_id: str) -> Tenant | None:
        path = self._path(tenant_id, tenant_id)
        return _model(Tenant, path) if path.exists() else None

    def list(self) -> list[Tenant]:
        tenants_root = self.root / "tenants"
        if not tenants_root.exists():
            return []
        return [
            _model(Tenant, path)
            for path in sorted(tenants_root.glob("*/tenants/*.json"))
        ]


class FileSubscriptionRepository(_FileRepositoryBase):
    def __init__(self, root: Path) -> None:
        super().__init__(root, "subscriptions")

    def upsert(self, tenant_id: str, entity: AzureSubscription) -> WriteResult:
        _validate_entities(tenant_id, [entity])
        item_id = deterministic_id(tenant_id, entity.subscription_id)
        path = self._path(tenant_id, item_id)
        existed = path.exists()
        _write_json(path, entity.model_dump(by_alias=True, mode="json"))
        return WriteResult(inserted=0 if existed else 1, updated=1 if existed else 0, path=str(path))

    def list(self, tenant_id: str) -> list[AzureSubscription]:
        return [
            AzureSubscription.model_validate(row)
            for row in self._rows(tenant_id)
        ]


class FileTenantUserRepository(_FileRepositoryBase):
    def __init__(self, root: Path) -> None:
        super().__init__(root, "tenantUsers")

    def upsert(self, tenant_id: str, entity: TenantUser) -> WriteResult:
        _validate_entities(tenant_id, [entity])
        item_id = deterministic_id(tenant_id, entity.user_id)
        path = self._path(tenant_id, item_id)
        existed = path.exists()
        _write_json(path, entity.model_dump(by_alias=True, mode="json"))
        return WriteResult(inserted=0 if existed else 1, updated=1 if existed else 0, path=str(path))

    def list(self, tenant_id: str) -> list[TenantUser]:
        return [TenantUser.model_validate(row) for row in self._rows(tenant_id)]


class FileTenantHealthRepository(_FileRepositoryBase):
    def __init__(self, root: Path) -> None:
        super().__init__(root, "tenantHealth")

    def upsert(self, tenant_id: str, entity: TenantHealth) -> WriteResult:
        _validate_entities(tenant_id, [entity])
        item_id = deterministic_id(tenant_id, entity.subscription_id)
        path = self._path(tenant_id, item_id)
        existed = path.exists()
        _write_json(path, entity.model_dump(by_alias=True, mode="json"))
        return WriteResult(inserted=0 if existed else 1, updated=1 if existed else 0, path=str(path))

    def get(self, tenant_id: str, subscription_id: str) -> TenantHealth | None:
        path = self._path(tenant_id, deterministic_id(tenant_id, subscription_id))
        return _model(TenantHealth, path) if path.exists() else None

    def list(self, tenant_id: str) -> list[TenantHealth]:
        return [TenantHealth.model_validate(row) for row in self._rows(tenant_id)]


class FileRawPayloadRepository:
    def __init__(self, root: Path, raw_path: Path) -> None:
        self.root = Path(root) / "raw-payloads"
        self.legacy_raw_path = Path(raw_path)

    def _path(
        self,
        tenant_id: str,
        subscription_id: str,
        collection_run_id: str,
        collector: str,
    ) -> Path:
        return (
            self.root
            / "tenants"
            / _safe_part(tenant_id)
            / "subscriptions"
            / _safe_part(subscription_id)
            / "collection-runs"
            / _safe_part(collection_run_id)
            / f"{_safe_part(collector)}.json"
        )

    def _latest_path(self, tenant_id: str, subscription_id: str, collector: str) -> Path:
        return (
            self.root
            / "tenants"
            / _safe_part(tenant_id)
            / "subscriptions"
            / _safe_part(subscription_id)
            / "latest"
            / f"{_safe_part(collector)}.json"
        )

    def save(
        self,
        tenant_id: str,
        subscription_id: str,
        collection_run_id: str,
        collector: str,
        payload: dict[str, Any],
    ) -> str:
        _require_tenant(tenant_id)
        context = payload.get("context", {})
        if context and context.get("tenantId") != tenant_id:
            raise TenantScopeError("Raw payload tenantId does not match repository scope")
        path = self._path(tenant_id, subscription_id, collection_run_id, collector)
        _write_json(path, payload)
        _write_json(self._latest_path(tenant_id, subscription_id, collector), payload)
        return str(path)

    def load_latest(
        self, tenant_id: str, subscription_id: str, collector: str
    ) -> dict[str, Any] | None:
        _require_tenant(tenant_id)
        return _read_json(self._latest_path(tenant_id, subscription_id, collector))

    def delete_tenant(self, tenant_id: str) -> int:
        import shutil

        tenant_dir = self.root / "tenants" / _safe_part(tenant_id)
        if not tenant_dir.exists():
            return 0
        count = sum(1 for path in tenant_dir.rglob("*.json") if path.is_file())
        shutil.rmtree(tenant_dir)
        return count


class FileEntityRepository(_FileRepositoryBase):
    def __init__(self, root: Path, collection: str, model: type[T], id_field: str) -> None:
        super().__init__(root, collection)
        self.model = model
        self.id_field = id_field

    def upsert_many(self, tenant_id: str, entities: Sequence[T]) -> WriteResult:
        _validate_entities(tenant_id, entities)
        inserted = 0
        updated = 0
        for entity in entities:
            payload = entity.model_dump(by_alias=True, mode="json")
            path = self._path(tenant_id, str(payload[self.id_field]))
            if path.exists():
                updated += 1
            else:
                inserted += 1
            _write_json(path, payload)
        return WriteResult(inserted=inserted, updated=updated)

    def list_for_run(
        self, tenant_id: str, subscription_id: str, processing_run_id: str
    ) -> list[T]:
        return [
            self.model.model_validate(row)
            for row in self._rows(tenant_id)
            if row.get("subscriptionId") == subscription_id
            and row.get("processingRunId") == processing_run_id
        ]

    def list_latest(self, tenant_id: str, subscription_id: str) -> list[T]:
        rows = [
            row for row in self._rows(tenant_id)
            if row.get("subscriptionId") == subscription_id
        ]
        if not rows:
            return []
        latest = max(
            rows,
            key=lambda row: (
                str(row.get("sourceTimestamp", "")),
                str(row.get("processingRunId", "")),
            ),
        )
        return self.list_for_run(
            tenant_id,
            subscription_id,
            str(latest.get("processingRunId", "")),
        )


class FileCostFactRepository(FileEntityRepository):
    def __init__(self, root: Path) -> None:
        super().__init__(root, "costFacts", CostFact, "factId")


class FileResourceRepository(FileEntityRepository):
    def __init__(self, root: Path) -> None:
        super().__init__(root, "resources", ResourceFact, "resourceFactId")


class FileRecommendationRepository(FileEntityRepository):
    def __init__(self, root: Path) -> None:
        super().__init__(root, "recommendations", Recommendation, "recommendationId")


class FileProcessingMetadataRepository(_FileRepositoryBase):
    def __init__(self, root: Path) -> None:
        super().__init__(root, "processingMetadata")

    def upsert(self, tenant_id: str, document: dict[str, Any]) -> WriteResult:
        _require_tenant(tenant_id)
        if document.get("tenantId") != tenant_id:
            raise TenantScopeError("Metadata tenantId does not match repository scope")
        metadata_id = str(
            document.get("metadataId")
            or deterministic_id(
                tenant_id,
                document.get("subscriptionId"),
                document.get("collectionRunId"),
                document.get("processingRunId"),
                document.get("metadataType"),
            )
        )
        path = self._path(tenant_id, metadata_id)
        existed = path.exists()
        _write_json(path, {**document, "metadataId": metadata_id})
        return WriteResult(inserted=0 if existed else 1, updated=1 if existed else 0, path=str(path))

    def get(
        self, tenant_id: str, subscription_id: str, metadata_id: str
    ) -> dict[str, Any] | None:
        document = _read_json(self._path(tenant_id, metadata_id))
        if not document or document.get("subscriptionId") != subscription_id:
            return None
        return document

    def list_latest(
        self, tenant_id: str, subscription_id: str
    ) -> list[dict[str, Any]]:
        rows = [
            row for row in self._rows(tenant_id)
            if row.get("subscriptionId") == subscription_id
        ]
        return sorted(
            rows,
            key=lambda row: str(row.get("startedAt") or row.get("sourceTimestamp") or ""),
            reverse=True,
        )[:20]


class FileSessionRepository:
    def __init__(self, root: Path) -> None:
        self.root = Path(root) / "sessions"

    def _path(self, session_id: str) -> Path:
        return self.root / f"{_safe_part(session_id)}.json"

    def upsert(self, entity: ServerSession) -> WriteResult:
        path = self._path(entity.session_id)
        existed = path.exists()
        _write_json(path, entity.model_dump(by_alias=True, mode="json"))
        return WriteResult(inserted=0 if existed else 1, updated=1 if existed else 0, path=str(path))

    def get(self, session_id: str) -> ServerSession | None:
        path = self._path(session_id)
        if not path.exists():
            return None
        return ServerSession.model_validate(_read_json(path))

    def delete(self, session_id: str) -> None:
        path = self._path(session_id)
        if path.exists():
            path.unlink()
