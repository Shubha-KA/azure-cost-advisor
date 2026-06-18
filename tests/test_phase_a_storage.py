from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from src.domain.context import OperationContext
from src.domain.models import (
    AzureSubscription,
    CostFact,
    ResourceFact,
    Tenant,
    TenantUser,
)
from src.adapters.blob.raw_payloads import BlobRawPayloadRepository
from src.adapters.cosmos.repositories import (
    CosmosEntityRepository,
    CosmosRepositories,
)
from src.migration.file_to_repositories import migrate_legacy_files
from src.repositories.errors import StorageConfigurationError, TenantScopeError
from src.storage.factory import create_storage_provider


def test_domain_models_require_tenant_identifiers() -> None:
    with pytest.raises(ValidationError):
        Tenant(tenantId="", correlationId="correlation")

    context = OperationContext.create("tenant-a", "subscription-a")
    assert context.schema_version == 1
    assert context.collection_run_id
    assert context.processing_run_id


def test_file_provider_is_default_and_persists_master_data(test_settings) -> None:
    provider = create_storage_provider(test_settings)
    tenant = Tenant(
        tenantId="tenant-a",
        displayName="Tenant A",
        correlationId="correlation-a",
    )
    subscription = AzureSubscription(
        tenantId="tenant-a",
        subscriptionId="subscription-a",
        correlationId="correlation-a",
    )
    user = TenantUser(
        tenantId="tenant-a",
        userId="user-a",
        correlationId="correlation-a",
    )

    provider.tenants.upsert("tenant-a", tenant)
    provider.subscriptions.upsert("tenant-a", subscription)
    provider.tenant_users.upsert("tenant-a", user)

    assert provider.tenants.get("tenant-a") == tenant
    assert provider.subscriptions.list("tenant-a") == [subscription]
    assert provider.tenant_users.list("tenant-a") == [user]


def test_repository_rejects_cross_tenant_writes(test_settings) -> None:
    provider = create_storage_provider(test_settings)
    context = OperationContext.create("tenant-a", "subscription-a")
    fact = CostFact(
        **context.document_fields(),
        date="2026-01-01",
        costAmount=1,
        currency="USD",
        sourceSystem="test",
        sourceTimestamp="2026-01-01T00:00:00Z",
    )
    with pytest.raises(TenantScopeError):
        provider.cost_facts.upsert_many("tenant-b", [fact])


def test_file_fact_repositories_are_tenant_and_run_scoped(test_settings) -> None:
    provider = create_storage_provider(test_settings)
    context = OperationContext.create("tenant-a", "subscription-a")
    cost = CostFact(
        **context.document_fields(),
        date="2026-01-01",
        resourceId="/subscriptions/a/resourceGroups/rg/providers/test/r1",
        costAmount=12.5,
        currency="inr",
        sourceSystem="test",
        sourceTimestamp="2026-01-01T00:00:00Z",
    )
    resource = ResourceFact(
        **context.document_fields(),
        resourceId="/subscriptions/a/resourceGroups/rg/providers/test/r1",
        resourceName="r1",
        resourceType="test/resource",
        sourceSystem="test",
        sourceTimestamp="2026-01-01T00:00:00Z",
    )
    provider.cost_facts.upsert_many("tenant-a", [cost])
    provider.resources.upsert_many("tenant-a", [resource])

    costs = provider.cost_facts.list_for_run(
        "tenant-a", "subscription-a", context.processing_run_id
    )
    resources = provider.resources.list_latest("tenant-a", "subscription-a")
    assert costs[0].currency == "INR"
    assert resources[0].resource_id.endswith("/r1")
    assert provider.cost_facts.list_latest("tenant-b", "subscription-a") == []


def test_cosmos_provider_requires_cloud_configuration(test_settings) -> None:
    test_settings.storage_provider = "cosmos"
    with pytest.raises(StorageConfigurationError):
        create_storage_provider(test_settings)


def test_migration_dry_run_and_execute(test_settings) -> None:
    test_settings.processed_path.mkdir(parents=True, exist_ok=True)
    (test_settings.processed_path / "cost_facts_latest.csv").write_text(
        "date,resource_id,resource_group,service_name,location,cost_amount,"
        "usage_quantity,currency,source_system,source_timestamp\n"
        "2026-01-01,/subscriptions/a/r1,rg,Compute,eastus,10,1,USD,test,"
        "2026-01-01T00:00:00Z\n",
        encoding="utf-8",
    )
    (test_settings.processed_path / "resources_latest.csv").write_text(
        "resource_id,resource_name,resource_type,resource_group,location,"
        "source_system,source_timestamp\n"
        "/subscriptions/a/r1,r1,test/resource,rg,eastus,test,"
        "2026-01-01T00:00:00Z\n",
        encoding="utf-8",
    )
    (test_settings.processed_path / "recommendations_latest.json").write_text(
        json.dumps({"recommendations": "Review r1"}),
        encoding="utf-8",
    )

    dry_run = migrate_legacy_files(test_settings, dry_run=True)
    executed = migrate_legacy_files(test_settings, dry_run=False)
    assert dry_run["costFacts"] == executed["costFacts"] == 1
    provider = create_storage_provider(test_settings)
    assert len(
        provider.cost_facts.list_latest(
            test_settings.effective_tenant_id,
            test_settings.effective_subscription_id,
        )
    ) == 1


class _FakeCollection:
    def __init__(self) -> None:
        self.documents: list[dict] = []
        self.partition_keys: list[str] = []

    def upsert_item(self, document):
        self.documents = [row for row in self.documents if row["id"] != document["id"]]
        self.documents.append(document)

    def query_items(self, query, parameters=None, partition_key=None, **kwargs):
        self.partition_keys.append(partition_key)
        values = {
            item["name"]: item["value"]
            for item in (parameters or [])
        }
        rows = [
            row for row in self.documents
            if all(
                row.get(field) == values[name]
                for name, field in (
                    ("@tenantId", "tenantId"),
                    ("@subscriptionId", "subscriptionId"),
                    ("@processingRunId", "processingRunId"),
                )
                if name in values
            )
        ]
        return rows


def test_cosmos_repository_filters_every_operation_by_tenant() -> None:
    collection = _FakeCollection()
    repository = CosmosEntityRepository(collection, CostFact, "factId")
    context = OperationContext.create("tenant-a", "subscription-a")
    fact = CostFact(
        **context.document_fields(),
        date="2026-01-01",
        costAmount=4,
        currency="USD",
        sourceSystem="test",
        sourceTimestamp="2026-01-01T00:00:00Z",
    )
    repository.upsert_many("tenant-a", [fact])
    assert len(
        repository.list_for_run(
            "tenant-a", "subscription-a", context.processing_run_id
        )
    ) == 1
    assert (
        repository.list_for_run(
            "tenant-b", "subscription-a", context.processing_run_id
        )
        == []
    )
    assert collection.partition_keys == ["tenant-a", "tenant-b"]


def test_cosmos_nosql_adapter_maps_expected_containers(
    test_settings, monkeypatch
) -> None:
    import azure.cosmos

    requested = []

    class _Database:
        def get_container_client(self, name):
            requested.append(name)
            return _FakeCollection()

    class _Client:
        def __init__(self, endpoint, credential):
            assert endpoint == "https://test.documents.azure.com:443/"
            assert credential == "test-key"

        def get_database_client(self, name):
            assert name == "finops-test"
            return _Database()

    monkeypatch.setattr(azure.cosmos, "CosmosClient", _Client)
    test_settings.cosmos_endpoint = "https://test.documents.azure.com:443/"
    test_settings.cosmos_database = "finops-test"
    test_settings.cosmos_key = "test-key"

    repositories = CosmosRepositories(test_settings)

    assert repositories.cost_facts.container is not None
    assert requested == [
        "tenants",
        "subscriptions",
        "tenantUsers",
        "tenantHealth",
        "costFacts",
        "resources",
        "recommendations",
        "processingMetadata",
    ]


class _BlobResult:
    def __init__(self, value: bytes) -> None:
        self.value = value

    def readall(self) -> bytes:
        return self.value


class _FakeContainer:
    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}

    def upload_blob(self, name, data, **kwargs):
        self.values[name] = data

    def download_blob(self, name):
        if name not in self.values:
            raise RuntimeError("BlobNotFound")
        return _BlobResult(self.values[name])


def test_blob_adapter_uses_tenant_scoped_layout() -> None:
    repository = BlobRawPayloadRepository.__new__(BlobRawPayloadRepository)
    repository.container = _FakeContainer()
    payload = {
        "context": {
            "tenantId": "tenant-a",
            "subscriptionId": "subscription-a",
            "collectionRunId": "run-a",
            "correlationId": "correlation-a",
            "schemaVersion": 1,
        },
        "records": [{"value": 1}],
    }
    path = repository.save(
        "tenant-a", "subscription-a", "run-a", "costs", payload
    )
    assert path.startswith(
        "raw/tenants/tenant-a/subscriptions/subscription-a/"
    )
    assert (
        repository.load_latest("tenant-a", "subscription-a", "costs")
        == payload
    )
