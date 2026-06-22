"""Auditable GDPR-friendly tenant export and offboarding workflow."""

from __future__ import annotations

import shutil
import hashlib
from datetime import datetime, timezone

from src.repositories.errors import TenantScopeError


class TenantLifecycleService:
    def __init__(self, settings, storage, search_provider=None) -> None:
        self.settings = settings
        self.storage = storage
        self.search_provider = search_provider

    def request_deletion(self, tenant_id: str, requested_by: str) -> dict:
        if not tenant_id:
            raise TenantScopeError("tenantId is required")
        record = {
            "tenantId": tenant_id,
            "subscriptionId": "tenant-lifecycle",
            "metadataType": "tenantDeletionRequest",
            "metadataId": f"delete-{tenant_id}",
            "requestedBy": requested_by,
            "requestedAt": datetime.now(timezone.utc).isoformat(),
            "status": "pending",
            "schemaVersion": 1,
        }
        self.storage.processing_metadata.upsert(tenant_id, record)
        return record

    def execute_deletion(self, tenant_id: str) -> dict:
        deleted_blobs = 0
        deleted_search_documents = 0
        raw_payloads = self.storage.raw_payloads
        if hasattr(raw_payloads, "delete_tenant"):
            deleted_blobs = raw_payloads.delete_tenant(tenant_id)
        search_provider = self.search_provider
        if search_provider is None and (
            self.settings.search_provider == "faiss"
            or self.settings.azure_search_configured
        ):
            from src.search.factory import create_search_provider

            search_provider = create_search_provider(self.settings)
        if search_provider is not None and hasattr(search_provider, "delete_tenant"):
            deleted_search_documents = search_provider.delete_tenant(tenant_id)
        if self.settings.storage_provider == "file":
            root = self.settings.storage_path / "tenants" / tenant_id
            resolved = root.resolve()
            allowed = (self.settings.storage_path / "tenants").resolve()
            if allowed not in resolved.parents:
                raise TenantScopeError("Deletion path escaped tenant storage")
            if root.exists():
                shutil.rmtree(root)
        else:
            for repository in (
                self.storage.tenants,
                self.storage.subscriptions,
                self.storage.tenant_users,
                self.storage.tenant_health,
                self.storage.cost_facts,
                self.storage.resources,
                self.storage.recommendations,
                self.storage.processing_metadata,
            ):
                if not hasattr(repository, "delete_tenant"):
                    raise RuntimeError(
                        "Configured repository does not support tenant deletion"
                    )
                repository.delete_tenant(tenant_id)
        deleted_at = datetime.now(timezone.utc).isoformat()
        tombstone = {
            "tenantId": "platform-audit",
            "subscriptionId": "tenant-lifecycle",
            "metadataType": "tenantDeletionCompleted",
            "metadataId": f"deleted-{hashlib.sha256(tenant_id.encode()).hexdigest()[:24]}",
            "tenantHash": hashlib.sha256(tenant_id.encode()).hexdigest(),
            "deletedAt": deleted_at,
            "deletedBlobs": deleted_blobs,
            "deletedSearchDocuments": deleted_search_documents,
            "backupRetentionDays": 30,
            "schemaVersion": 1,
        }
        self.storage.processing_metadata.upsert("platform-audit", tombstone)
        return {
            "tenantId": tenant_id,
            "status": "deleted",
            "deletedAt": deleted_at,
            "deletedBlobs": deleted_blobs,
            "deletedSearchDocuments": deleted_search_documents,
            "backupRetentionDays": 30,
        }
