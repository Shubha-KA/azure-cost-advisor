"""Storage-independent repository protocols."""

from __future__ import annotations

from typing import Any, Protocol, Sequence

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
from src.repositories.results import WriteResult


class TenantRepository(Protocol):
    def upsert(self, tenant_id: str, entity: Tenant) -> WriteResult: ...
    def get(self, tenant_id: str) -> Tenant | None: ...
    def list(self) -> list[Tenant]: ...


class SubscriptionRepository(Protocol):
    def upsert(
        self, tenant_id: str, entity: AzureSubscription
    ) -> WriteResult: ...
    def list(self, tenant_id: str) -> list[AzureSubscription]: ...


class TenantUserRepository(Protocol):
    def upsert(self, tenant_id: str, entity: TenantUser) -> WriteResult: ...
    def list(self, tenant_id: str) -> list[TenantUser]: ...


class TenantHealthRepository(Protocol):
    def upsert(self, tenant_id: str, entity: TenantHealth) -> WriteResult: ...
    def get(
        self, tenant_id: str, subscription_id: str
    ) -> TenantHealth | None: ...
    def list(self, tenant_id: str) -> list[TenantHealth]: ...


class RawPayloadRepository(Protocol):
    def save(
        self,
        tenant_id: str,
        subscription_id: str,
        collection_run_id: str,
        collector: str,
        payload: dict[str, Any],
    ) -> str: ...

    def load_latest(
        self, tenant_id: str, subscription_id: str, collector: str
    ) -> dict[str, Any] | None: ...


class CostFactRepository(Protocol):
    def upsert_many(
        self, tenant_id: str, facts: Sequence[CostFact]
    ) -> WriteResult: ...
    def list_for_run(
        self, tenant_id: str, subscription_id: str, processing_run_id: str
    ) -> list[CostFact]: ...
    def list_latest(
        self, tenant_id: str, subscription_id: str
    ) -> list[CostFact]: ...


class ResourceRepository(Protocol):
    def upsert_many(
        self, tenant_id: str, facts: Sequence[ResourceFact]
    ) -> WriteResult: ...
    def list_for_run(
        self, tenant_id: str, subscription_id: str, processing_run_id: str
    ) -> list[ResourceFact]: ...
    def list_latest(
        self, tenant_id: str, subscription_id: str
    ) -> list[ResourceFact]: ...


class RecommendationRepository(Protocol):
    def upsert_many(
        self, tenant_id: str, recommendations: Sequence[Recommendation]
    ) -> WriteResult: ...
    def list_latest(
        self, tenant_id: str, subscription_id: str
    ) -> list[Recommendation]: ...


class ProcessingMetadataRepository(Protocol):
    def upsert(
        self, tenant_id: str, document: dict[str, Any]
    ) -> WriteResult: ...
    def get(
        self, tenant_id: str, subscription_id: str, metadata_id: str
    ) -> dict[str, Any] | None: ...
    def list_latest(
        self, tenant_id: str, subscription_id: str
    ) -> list[dict[str, Any]]: ...


class SessionRepository(Protocol):
    def upsert(self, entity: ServerSession) -> WriteResult: ...
    def get(self, session_id: str) -> ServerSession | None: ...
    def delete(self, session_id: str) -> None: ...
