"""Construct the configured storage provider."""

from __future__ import annotations

from src.adapters.filesystem import (
    FileCostFactRepository,
    FileProcessingMetadataRepository,
    FileRawPayloadRepository,
    FileRecommendationRepository,
    FileResourceRepository,
    FileSubscriptionRepository,
    FileTenantRepository,
    FileTenantHealthRepository,
    FileTenantUserRepository,
    FileSessionRepository,
)
from src.config import Settings, get_settings
from src.repositories.errors import StorageConfigurationError
from src.storage.provider import StorageProvider


def create_storage_provider(settings: Settings | None = None) -> StorageProvider:
    settings = settings or get_settings()
    provider = settings.storage_provider.lower()
    if provider == "file":
        root = settings.storage_path
        return StorageProvider(
            tenants=FileTenantRepository(root),
            subscriptions=FileSubscriptionRepository(root),
            tenant_users=FileTenantUserRepository(root),
            tenant_health=FileTenantHealthRepository(root),
            raw_payloads=FileRawPayloadRepository(root, settings.raw_path),
            cost_facts=FileCostFactRepository(root),
            resources=FileResourceRepository(root),
            recommendations=FileRecommendationRepository(root),
            processing_metadata=FileProcessingMetadataRepository(root),
            sessions=FileSessionRepository(root),
        )
    if provider == "cosmos":
        from src.adapters.blob.raw_payloads import BlobRawPayloadRepository
        from src.adapters.cosmos.repositories import CosmosRepositories

        if not settings.cosmos_endpoint:
            raise StorageConfigurationError(
                "COSMOS_ENDPOINT is required for STORAGE_PROVIDER=cosmos"
            )
        if not (
            settings.azure_storage_connection_string
            or settings.azure_storage_account_url
        ):
            raise StorageConfigurationError(
                "Azure Blob configuration is required for STORAGE_PROVIDER=cosmos"
            )
        cosmos = CosmosRepositories(settings)
        return StorageProvider(
            tenants=cosmos.tenants,
            subscriptions=cosmos.subscriptions,
            tenant_users=cosmos.tenant_users,
            tenant_health=cosmos.tenant_health,
            raw_payloads=BlobRawPayloadRepository(settings),
            cost_facts=cosmos.cost_facts,
            resources=cosmos.resources,
            recommendations=cosmos.recommendations,
            processing_metadata=cosmos.processing_metadata,
            sessions=cosmos.sessions,
        )
    raise StorageConfigurationError(
        f"Unsupported STORAGE_PROVIDER={settings.storage_provider!r}"
    )
