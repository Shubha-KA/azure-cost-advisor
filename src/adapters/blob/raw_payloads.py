"""Gzip-compressed raw payload storage in Azure Blob Storage."""

from __future__ import annotations

import gzip
import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from src.repositories.errors import RepositoryError, TenantScopeError


class BlobRawPayloadRepository:
    def __init__(self, settings) -> None:
        try:
            from azure.storage.blob import BlobServiceClient
        except ImportError as exc:
            raise RepositoryError(
                "azure-storage-blob is required for STORAGE_PROVIDER=cosmos"
            ) from exc
        if settings.azure_storage_connection_string:
            service = BlobServiceClient.from_connection_string(
                settings.azure_storage_connection_string
            )
        else:
            from azure.identity import DefaultAzureCredential

            service = BlobServiceClient(
                settings.azure_storage_account_url,
                credential=DefaultAzureCredential(),
            )
        self.container = service.get_container_client(
            settings.azure_storage_container
        )
        try:
            self.container.create_container()
        except Exception as exc:
            if "ContainerAlreadyExists" not in str(exc):
                raise RepositoryError(f"Blob container initialization failed: {exc}") from exc

    @staticmethod
    def _prefix(
        tenant_id: str, subscription_id: str, collection_run_id: str
    ) -> str:
        if not tenant_id:
            raise TenantScopeError("tenantId is required")
        return (
            f"raw/tenants/{tenant_id}/subscriptions/{subscription_id}/"
            f"collection-runs/{collection_run_id}"
        )

    def save(
        self,
        tenant_id: str,
        subscription_id: str,
        collection_run_id: str,
        collector: str,
        payload: dict[str, Any],
    ) -> str:
        context = payload.get("context", {})
        if context and context.get("tenantId") != tenant_id:
            raise TenantScopeError("Raw payload tenantId does not match repository scope")
        serialized = json.dumps(payload, default=str).encode("utf-8")
        compressed = gzip.compress(serialized)
        checksum = hashlib.sha256(compressed).hexdigest()
        prefix = self._prefix(tenant_id, subscription_id, collection_run_id)
        name = f"{prefix}/{collector}/payload.json.gz"
        metadata = {
            "tenantid": tenant_id,
            "subscriptionid": subscription_id,
            "collectionrunid": collection_run_id,
            "correlationid": str(context.get("correlationId", "")),
            "schemaversion": str(context.get("schemaVersion", 1)),
            "collector": collector,
            "sha256": checksum,
        }
        self.container.upload_blob(
            name,
            compressed,
            overwrite=True,
            metadata=metadata,
            content_settings=self._content_settings(),
        )
        manifest = {
            **metadata,
            "blobName": name,
            "savedAt": datetime.now(timezone.utc).isoformat(),
            "compressedBytes": len(compressed),
        }
        self.container.upload_blob(
            f"{prefix}/{collector}/manifest.json",
            json.dumps(manifest).encode("utf-8"),
            overwrite=True,
        )
        self.container.upload_blob(
            f"raw/tenants/{tenant_id}/subscriptions/{subscription_id}/"
            f"latest/{collector}.json",
            serialized,
            overwrite=True,
        )
        return name

    @staticmethod
    def _content_settings():
        from azure.storage.blob import ContentSettings

        return ContentSettings(
            content_type="application/json", content_encoding="gzip"
        )

    def load_latest(
        self, tenant_id: str, subscription_id: str, collector: str
    ) -> dict[str, Any] | None:
        if not tenant_id:
            raise TenantScopeError("tenantId is required")
        name = (
            f"raw/tenants/{tenant_id}/subscriptions/{subscription_id}/"
            f"latest/{collector}.json"
        )
        try:
            data = self.container.download_blob(name).readall()
        except Exception as exc:
            if "BlobNotFound" in str(exc):
                return None
            raise RepositoryError(f"Blob download failed: {exc}") from exc
        return json.loads(data)

    def delete_tenant(self, tenant_id: str) -> int:
        if not tenant_id:
            raise TenantScopeError("tenantId is required")
        prefix = f"raw/tenants/{tenant_id}/"
        blobs = [item.name for item in self.container.list_blobs(name_starts_with=prefix)]
        if blobs:
            self.container.delete_blobs(*blobs)
        return len(blobs)
