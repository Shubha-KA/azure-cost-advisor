"""Azure Cosmos DB for NoSQL implementations of application repositories."""

from __future__ import annotations

from dataclasses import dataclass
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


def _document(entity: BaseModel, item_id: str) -> dict[str, Any]:
    return {
        **entity.model_dump(by_alias=True, mode="json"),
        "id": str(item_id),
    }


def _model(model: type[T], row: dict[str, Any]) -> T:
    payload = {
        key: value
        for key, value in row.items()
        if key != "id" and not key.startswith("_")
    }
    return model.model_validate(payload)


def _query(
    container,
    tenant_id: str,
    query: str,
    parameters: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    _require_tenant(tenant_id)
    return list(
        container.query_items(
            query=query,
            parameters=[
                {"name": "@tenantId", "value": tenant_id},
                *(parameters or []),
            ],
            partition_key=tenant_id,
        )
    )


class _CosmosRepositoryBase:
    def __init__(self, container) -> None:
        self.container = container

    def delete_tenant(self, tenant_id: str) -> int:
        rows = _query(
            self.container,
            tenant_id,
            "SELECT c.id FROM c WHERE c.tenantId = @tenantId",
        )
        for row in rows:
            self.container.delete_item(
                item=row["id"],
                partition_key=tenant_id,
            )
        return len(rows)


class CosmosEntityRepository(_CosmosRepositoryBase):
    def __init__(self, container, model: type[T], id_field: str) -> None:
        super().__init__(container)
        self.model = model
        self.id_field = id_field

    def upsert_many(
        self, tenant_id: str, entities: Sequence[T]
    ) -> WriteResult:
        _validate_entities(tenant_id, entities)
        try:
            for entity in entities:
                payload = entity.model_dump(by_alias=True, mode="json")
                self.container.upsert_item(
                    _document(entity, str(payload[self.id_field]))
                )
        except Exception as exc:
            raise RepositoryError(f"Cosmos NoSQL write failed: {exc}") from exc
        return WriteResult(updated=len(entities))

    def list_for_run(
        self, tenant_id: str, subscription_id: str, processing_run_id: str
    ) -> list[T]:
        rows = _query(
            self.container,
            tenant_id,
            (
                "SELECT * FROM c WHERE c.tenantId = @tenantId "
                "AND c.subscriptionId = @subscriptionId "
                "AND c.processingRunId = @processingRunId"
            ),
            [
                {"name": "@subscriptionId", "value": subscription_id},
                {"name": "@processingRunId", "value": processing_run_id},
            ],
        )
        return [_model(self.model, row) for row in rows]

    def list_latest(self, tenant_id: str, subscription_id: str) -> list[T]:
        rows = _query(
            self.container,
            tenant_id,
            (
                "SELECT c.processingRunId, c.sourceTimestamp FROM c "
                "WHERE c.tenantId = @tenantId "
                "AND c.subscriptionId = @subscriptionId"
            ),
            [{"name": "@subscriptionId", "value": subscription_id}],
        )
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
            tenant_id, subscription_id, latest["processingRunId"]
        )


class CosmosTenantRepository(_CosmosRepositoryBase):
    def upsert(self, tenant_id: str, entity: Tenant) -> WriteResult:
        _validate_entities(tenant_id, [entity])
        self.container.upsert_item(_document(entity, tenant_id))
        return WriteResult(updated=1)

    def get(self, tenant_id: str) -> Tenant | None:
        _require_tenant(tenant_id)
        try:
            row = self.container.read_item(
                item=tenant_id,
                partition_key=tenant_id,
            )
        except Exception as exc:
            if getattr(exc, "status_code", None) == 404:
                return None
            raise RepositoryError(f"Cosmos NoSQL read failed: {exc}") from exc
        return _model(Tenant, row)

    def list(self) -> list[Tenant]:
        rows = self.container.query_items(
            query="SELECT * FROM c",
            enable_cross_partition_query=True,
        )
        return [_model(Tenant, row) for row in rows]


class CosmosSubscriptionRepository(_CosmosRepositoryBase):
    def upsert(
        self, tenant_id: str, entity: AzureSubscription
    ) -> WriteResult:
        _validate_entities(tenant_id, [entity])
        item_id = deterministic_id(tenant_id, entity.subscription_id)
        self.container.upsert_item(_document(entity, item_id))
        return WriteResult(updated=1)

    def list(self, tenant_id: str) -> list[AzureSubscription]:
        rows = _query(
            self.container,
            tenant_id,
            "SELECT * FROM c WHERE c.tenantId = @tenantId",
        )
        return [_model(AzureSubscription, row) for row in rows]


class CosmosTenantUserRepository(_CosmosRepositoryBase):
    def upsert(self, tenant_id: str, entity: TenantUser) -> WriteResult:
        _validate_entities(tenant_id, [entity])
        item_id = deterministic_id(tenant_id, entity.user_id)
        self.container.upsert_item(_document(entity, item_id))
        return WriteResult(updated=1)

    def list(self, tenant_id: str) -> list[TenantUser]:
        rows = _query(
            self.container,
            tenant_id,
            "SELECT * FROM c WHERE c.tenantId = @tenantId",
        )
        return [_model(TenantUser, row) for row in rows]


class CosmosTenantHealthRepository(_CosmosRepositoryBase):
    def upsert(self, tenant_id: str, entity: TenantHealth) -> WriteResult:
        _validate_entities(tenant_id, [entity])
        item_id = deterministic_id(tenant_id, entity.subscription_id)
        self.container.upsert_item(_document(entity, item_id))
        return WriteResult(updated=1)

    def get(
        self, tenant_id: str, subscription_id: str
    ) -> TenantHealth | None:
        item_id = deterministic_id(tenant_id, subscription_id)
        try:
            row = self.container.read_item(
                item=item_id,
                partition_key=tenant_id,
            )
        except Exception as exc:
            if getattr(exc, "status_code", None) == 404:
                return None
            raise RepositoryError(f"Cosmos NoSQL read failed: {exc}") from exc
        return _model(TenantHealth, row)

    def list(self, tenant_id: str) -> list[TenantHealth]:
        rows = _query(
            self.container,
            tenant_id,
            "SELECT * FROM c WHERE c.tenantId = @tenantId",
        )
        return [_model(TenantHealth, row) for row in rows]


class CosmosProcessingMetadataRepository(_CosmosRepositoryBase):
    def upsert(
        self, tenant_id: str, document: dict[str, Any]
    ) -> WriteResult:
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
        self.container.upsert_item(
            {**document, "metadataId": metadata_id, "id": metadata_id}
        )
        return WriteResult(updated=1)

    def get(
        self, tenant_id: str, subscription_id: str, metadata_id: str
    ) -> dict[str, Any] | None:
        _require_tenant(tenant_id)
        try:
            row = self.container.read_item(
                item=metadata_id,
                partition_key=tenant_id,
            )
        except Exception as exc:
            if getattr(exc, "status_code", None) == 404:
                return None
            raise RepositoryError(f"Cosmos NoSQL read failed: {exc}") from exc
        if row.get("subscriptionId") != subscription_id:
            return None
        return {
            key: value
            for key, value in row.items()
            if key != "id" and not key.startswith("_")
        }

    def list_latest(
        self, tenant_id: str, subscription_id: str
    ) -> list[dict[str, Any]]:
        rows = _query(
            self.container,
            tenant_id,
            (
                "SELECT TOP 20 * FROM c WHERE c.tenantId = @tenantId "
                "AND c.subscriptionId = @subscriptionId "
                "ORDER BY c.startedAt DESC"
            ),
            [{"name": "@subscriptionId", "value": subscription_id}],
        )
        return [
            {
                key: value
                for key, value in row.items()
                if key != "id" and not key.startswith("_")
            }
            for row in rows
        ]


class CosmosSessionRepository:
    def __init__(self, container) -> None:
        self.container = container

    def upsert(self, entity: ServerSession) -> WriteResult:
        self.container.upsert_item(_document(entity, entity.session_id))
        return WriteResult(updated=1)

    def get(self, session_id: str) -> ServerSession | None:
        try:
            rows = list(
                self.container.query_items(
                    query="SELECT * FROM c WHERE c.id = @sessionId",
                    parameters=[{"name": "@sessionId", "value": session_id}],
                    enable_cross_partition_query=True,
                )
            )
            if not rows:
                return None
            return _model(ServerSession, rows[0])
        except Exception as exc:
            raise RepositoryError(f"Cosmos NoSQL read failed: {exc}") from exc

    def delete(self, session_id: str) -> None:
        session = self.get(session_id)
        if not session:
            return
        try:
            self.container.delete_item(
                item=session_id,
                partition_key=session.tenant_id,
            )
        except Exception as exc:
            if getattr(exc, "status_code", None) == 404:
                return
            raise RepositoryError(f"Cosmos NoSQL delete failed: {exc}") from exc


@dataclass
class CosmosRepositories:
    settings: Any

    def __post_init__(self) -> None:
        try:
            from azure.cosmos import CosmosClient
            from azure.identity import DefaultAzureCredential
        except ImportError as exc:
            raise RepositoryError(
                "azure-cosmos and azure-identity are required for "
                "STORAGE_PROVIDER=cosmos"
            ) from exc

        credential: Any = self.settings.cosmos_key or DefaultAzureCredential(
            managed_identity_client_id=self.settings.azure_client_id or None
        )
        self.client = CosmosClient(
            self.settings.cosmos_endpoint,
            credential=credential,
        )
        self.database = self.client.get_database_client(
            self.settings.cosmos_database
        )
        containers = {
            name: self.database.get_container_client(name)
            for name in (
                "tenants",
                "subscriptions",
                "tenantUsers",
                "tenantHealth",
                "costFacts",
                "resources",
                "recommendations",
                "processingMetadata",
                "authSessions",
            )
        }
        self.tenants = CosmosTenantRepository(containers["tenants"])
        self.subscriptions = CosmosSubscriptionRepository(
            containers["subscriptions"]
        )
        self.tenant_users = CosmosTenantUserRepository(containers["tenantUsers"])
        self.tenant_health = CosmosTenantHealthRepository(
            containers["tenantHealth"]
        )
        self.cost_facts = CosmosEntityRepository(
            containers["costFacts"], CostFact, "factId"
        )
        self.resources = CosmosEntityRepository(
            containers["resources"], ResourceFact, "resourceFactId"
        )
        self.recommendations = CosmosEntityRepository(
            containers["recommendations"], Recommendation, "recommendationId"
        )
        self.processing_metadata = CosmosProcessingMetadataRepository(
            containers["processingMetadata"]
        )
        self.sessions = CosmosSessionRepository(
            containers["authSessions"]
        )
