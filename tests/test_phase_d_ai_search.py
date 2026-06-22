from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from src.ai.inventory import ResourceGraphInventoryService
from src.ai.inventory import InventoryQueryError
from src.ai.advisor import FinOpsAdvisor
from src.ai.rag import RAGPipeline
from src.ai.router import classify_intent, route_query
from src.domain.context import OperationContext
from src.domain.models import CostFact, ProcessingRun, Recommendation, ResourceFact
from src.repositories.errors import TenantScopeError
from src.search.azure_ai_search import AzureAISearchProvider
from src.search.knowledge import KnowledgeService
from src.search.models import KnowledgeDocument, SearchResult
from src.storage.factory import create_storage_provider


class _Embeddings:
    def embed_documents(self, texts):
        return [[0.1, 0.2, 0.3] for _ in texts]

    def embed_query(self, text):
        return [0.1, 0.2, 0.3]


class _IndexClient:
    def __init__(self):
        self.index = None

    def create_or_update_index(self, index):
        self.index = index
        return index


class _UploadResult:
    succeeded = True


class _SearchClient:
    def __init__(self):
        self.uploads = []
        self.search_kwargs = None

    def upload_documents(self, documents):
        self.uploads.extend(documents)
        return [_UploadResult() for _ in documents]

    def search(self, **kwargs):
        self.search_kwargs = kwargs
        return [
            {
                "id": "doc-a",
                "tenantId": "tenant-a",
                "subscriptionId": "subscription-a",
                "collectionRunId": "collection-a",
                "processingRunId": "processing-a",
                "sourceSystem": "test",
                "schemaVersion": 1,
                "documentType": "cost_fact",
                "title": "Cost",
                "content": "Tenant A cost context",
                "metadataJson": "{}",
                "@search.score": 1.5,
            }
        ]


def _search_settings(test_settings):
    test_settings.search_provider = "azure_ai_search"
    test_settings.azure_search_endpoint = "https://search.example"
    test_settings.azure_search_api_key = "search-key"
    test_settings.azure_search_vector_dimensions = 3
    return test_settings


def _document(tenant_id="tenant-a"):
    return KnowledgeDocument(
        id="doc-a",
        tenantId=tenant_id,
        subscriptionId="subscription-a",
        collectionRunId="collection-a",
        processingRunId="processing-a",
        sourceSystem="test",
        schemaVersion=1,
        documentType="cost_fact",
        title="Cost",
        content="Cost context",
    )


def test_azure_search_index_creation_and_hybrid_tenant_filter(test_settings):
    index_client = _IndexClient()
    search_client = _SearchClient()
    provider = AzureAISearchProvider(
        _search_settings(test_settings),
        index_client=index_client,
        search_client=search_client,
        embeddings=_Embeddings(),
    )
    provider.ensure_index()
    count = provider.index_documents("tenant-a", [_document()])
    results = provider.search(
        "tenant-a", "subscription-a", "cost trend", top=5
    )

    assert index_client.index.name == "finops-knowledge"
    assert count == 1
    assert search_client.uploads[0]["tenantId"] == "tenant-a"
    assert search_client.uploads[0]["contentVector"] == [0.1, 0.2, 0.3]
    assert (
        search_client.search_kwargs["filter"]
        == "tenantId eq 'tenant-a' and subscriptionId eq 'subscription-a'"
    )
    assert search_client.search_kwargs["query_type"] == "semantic"
    assert search_client.search_kwargs["vector_queries"]
    assert results[0].metadata["tenantId"] == "tenant-a"


def test_search_rejects_cross_tenant_indexing(test_settings):
    provider = AzureAISearchProvider(
        _search_settings(test_settings),
        index_client=_IndexClient(),
        search_client=_SearchClient(),
        embeddings=_Embeddings(),
    )
    with pytest.raises(TenantScopeError):
        provider.index_documents("tenant-b", [_document("tenant-a")])


class _MemorySearch:
    def __init__(self):
        self.documents = []
        self.last_query = None
        self.last_search_latency_ms = 1.2

    def ensure_index(self):
        self.created = True

    def index_documents(self, tenant_id, documents):
        assert all(item.tenant_id == tenant_id for item in documents)
        self.documents.extend(documents)
        return len(documents)

    def search(self, tenant_id, subscription_id, query, top=6):
        self.last_query = (tenant_id, subscription_id, query)
        return [
            SearchResult(
                content=item.content,
                metadata=item.model_dump(by_alias=True),
            )
            for item in self.documents
            if item.tenant_id == tenant_id
            and item.subscription_id == subscription_id
        ][:top]


def test_knowledge_index_contains_required_tenant_documents(test_settings):
    storage = create_storage_provider(test_settings)
    context = OperationContext.create("tenant-a", "subscription-a")
    storage.cost_facts.upsert_many(
        "tenant-a",
        [
            CostFact(
                **context.document_fields(),
                date="2026-06-01",
                costAmount=10,
                currency="INR",
                sourceSystem="Azure Cost Management",
                sourceTimestamp="2026-06-01T00:00:00Z",
            )
        ],
    )
    storage.resources.upsert_many(
        "tenant-a",
        [
            ResourceFact(
                **context.document_fields(),
                resourceId="/subscriptions/a/r1",
                resourceName="r1",
                resourceType="test/resource",
                sourceSystem="Azure Resource Graph",
                sourceTimestamp="2026-06-01T00:00:00Z",
            )
        ],
    )
    storage.processing_metadata.upsert(
        "tenant-a",
        {
            **ProcessingRun(
                **context.document_fields(),
                status="completed",
                reconciliationStatus="passed",
            ).model_dump(by_alias=True, mode="json"),
            "metadataType": "processingRun",
            "summary": {
                "daily_trend": [
                    {"date": "2026-06-01", "currency": "INR", "cost_amount": 10}
                ],
                "total_cost": {"INR": 10},
            },
        },
    )
    search = _MemorySearch()
    service = KnowledgeService(storage, search)
    count = service.index_subscription("tenant-a", "subscription-a")

    types = {item.document_type for item in search.documents}
    assert count == len(search.documents)
    assert {
        "cost_fact",
        "resource_fact",
        "resource_inventory_summary",
        "processing_summary",
        "cost_trend",
    }.issubset(types)
    assert all(item.tenant_id == "tenant-a" for item in search.documents)
    assert all(item.schema_version == 1 for item in search.documents)


class _LLMResponse:
    content = "Tenant-scoped optimization response"
    usage_metadata = {
        "input_tokens": 20,
        "output_tokens": 8,
        "total_tokens": 28,
    }
    response_metadata = {}


class _LLM:
    def invoke(self, messages):
        return _LLMResponse()


def test_rag_tracks_tokens_and_never_crosses_tenants(test_settings):
    test_settings.azure_openai_endpoint = "https://openai.example"
    test_settings.azure_openai_api_key = "key"
    storage = create_storage_provider(test_settings)
    context = OperationContext.create("tenant-a", "subscription-a")
    storage.processing_metadata.upsert(
        "tenant-a",
        {
            **ProcessingRun(
                **context.document_fields(), status="completed"
            ).model_dump(by_alias=True, mode="json"),
            "metadataType": "processingRun",
        },
    )
    search = _MemorySearch()
    search.documents = [_document("tenant-a"), _document("tenant-b")]
    rag = RAGPipeline(
        test_settings,
        storage=storage,
        search_provider=search,
        llm=_LLM(),
    )
    result = rag.invoke(
        "How can I reduce cost?",
        tenant_id="tenant-a",
        subscription_id="subscription-a",
    )

    assert result["answer"] == "Tenant-scoped optimization response"
    assert result["usage"]["total_tokens"] == 28
    assert search.last_query[:2] == ("tenant-a", "subscription-a")
    assert len(result["context"]) == 1
    executions = [
        item
        for item in storage.processing_metadata.list_latest(
            "tenant-a", "subscription-a"
        )
        if item.get("metadataType") == "aiExecution"
    ]
    assert executions[0]["promptTokens"] == 20
    assert executions[0]["completionTokens"] == 8
    assert executions[0]["retrievedDocuments"] == 1
    assert executions[0]["searchLatencyMs"] >= 0


class _ResourceGraphClient:
    def resources(self, request):
        self.request = request
        return SimpleNamespace(
            data=[
                {
                    "name": "vm-a",
                    "type": "microsoft.compute/virtualmachines",
                    "resourceGroup": "rg-a",
                    "location": "eastus",
                }
            ]
        )


def test_live_inventory_response_has_required_provenance(test_settings):
    client = _ResourceGraphClient()
    result = ResourceGraphInventoryService(
        test_settings,
        tenant_id="tenant-a",
        subscription_ids=["subscription-a", "subscription-b"],
        client=client,
    ).query("What VMs exist?")

    assert result["source"] == "Azure Resource Graph"
    assert result["timestamp"]
    assert result["subscription_scope"] == [
        "subscription-a",
        "subscription-b",
    ]
    assert result["result_count"] == 1
    assert route_query("Show storage accounts") == "live_inventory"
    assert route_query("Show last month's cost trend") == "cost_analysis"


def test_entra_inventory_requires_tenant_scoped_credential(test_settings):
    test_settings.auth_mode = "entra"
    with pytest.raises(InventoryQueryError, match="tenant-scoped credential"):
        ResourceGraphInventoryService(
            test_settings,
            tenant_id="tenant-a",
            subscription_ids=["subscription-a"],
        )


def test_inventory_chat_never_uses_historical_search(
    test_settings, monkeypatch
):
    class _Inventory:
        def __init__(self, *args, **kwargs):
            pass

        def query(self, question):
            return {
                "source": "Azure Resource Graph",
                "source_system": "Azure Resource Graph",
                "timestamp": "2026-06-12T00:00:00Z",
                "subscription_scope": ["subscription-a"],
                "result_count": 1,
                "collection_run_id": "inventory-a",
                "records": [
                    {
                        "name": "vault-a",
                        "type": "microsoft.keyvault/vaults",
                        "resourceGroup": "rg-a",
                        "location": "eastus",
                    }
                ],
            }

    monkeypatch.setattr(
        "src.ai.advisor.ResourceGraphInventoryService", _Inventory
    )
    advisor = FinOpsAdvisor(
        test_settings,
        tenant_id="tenant-a",
        subscription_ids=["subscription-a"],
    )
    advisor.rag.invoke = lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("Inventory chat must not use search")
    )
    answer = advisor.ask("Show Key Vaults")

    assert "Azure Resource Graph (LIVE)" not in answer
    assert "Subscription scope: subscription-a" not in answer
    assert "Result count: 1" not in answer
    assert "Collection run" not in answer
    assert "vault-a" in answer


@pytest.mark.parametrize(
    ("question", "route"),
    [
        ("which resource is costing me more", "cost_analysis"),
        ("highest cost resource", "cost_analysis"),
        ("top spend resources", "cost_analysis"),
        ("list all resources", "live_inventory"),
        ("what resources exist in eastus", "live_inventory"),
        ("how can I save money", "recommendation"),
        ("How can I reduce my spend?", "recommendation"),
        ("show recommendations", "recommendation"),
        ("which AKS node pool costs most", "cost_analysis"),
    ],
)
def test_finops_intent_precedence_scores_all_intents(question, route):
    classification = classify_intent(question)

    assert classification.route == route
    assert route_query(question) == route


def test_cost_question_uses_cost_facts_not_inventory_or_rag(test_settings, monkeypatch):
    storage = create_storage_provider(test_settings)
    context = OperationContext.create("tenant-a", "subscription-a")
    storage.cost_facts.upsert_many(
        "tenant-a",
        [
            CostFact(
                **context.document_fields(),
                date="2026-06-01",
                resourceId="/subscriptions/a/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-a",
                resourceGroup="rg",
                serviceName="Virtual Machines",
                costAmount=25,
                currency="INR",
                sourceSystem="Azure Cost Management",
                sourceTimestamp="2026-06-01T00:00:00Z",
            ),
            CostFact(
                **context.document_fields(),
                date="2026-06-01",
                resourceId="/subscriptions/a/resourceGroups/rg/providers/Microsoft.Network/publicIPAddresses/pip-a",
                resourceGroup="rg",
                serviceName="IP Addresses",
                costAmount=5,
                currency="INR",
                sourceSystem="Azure Cost Management",
                sourceTimestamp="2026-06-01T00:00:00Z",
            ),
        ],
    )
    storage.resources.upsert_many(
        "tenant-a",
        [
            ResourceFact(
                **context.document_fields(),
                resourceId="/subscriptions/a/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-a",
                resourceName="vm-a",
                resourceType="microsoft.compute/virtualmachines",
                resourceGroup="rg",
                sourceSystem="Azure Resource Graph",
                sourceTimestamp="2026-06-01T00:00:00Z",
            )
        ],
    )
    storage.recommendations.upsert_many(
        "tenant-a",
        [
            Recommendation(
                **context.document_fields(),
                resourceId="/subscriptions/a/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-a",
                title="Rightsize VM",
                content="Review VM size.",
                estimatedSavings=10,
                currency="INR",
                sourceSystem="rules",
                sourceTimestamp="2026-06-01T00:00:00Z",
            )
        ],
    )

    monkeypatch.setattr(
        "src.ai.advisor.ResourceGraphInventoryService",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("Cost questions must not use live inventory")
        ),
    )
    advisor = FinOpsAdvisor(
        test_settings,
        tenant_id="tenant-a",
        subscription_ids=["subscription-a"],
    )
    advisor.rag.invoke = lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("Cost questions must not use generic RAG first")
    )

    answer = advisor.ask("which resource is costing me more")

    assert "Route selected" not in answer
    assert "Retrieval source" not in answer
    assert "Cost records analyzed" not in answer
    assert "vm-a" in answer
    assert "INR 25.00" in answer


def test_ai_debug_mode_exposes_diagnostics_when_enabled(test_settings):
    test_settings.ai_debug_mode = True
    advisor = FinOpsAdvisor(
        test_settings,
        tenant_id="tenant-a",
        subscription_ids=["subscription-a"],
    )

    answer = advisor.ask("highest cost resource")

    assert "Debug Details" in answer
    assert "Detected intent: Cost Analysis" in answer
    assert "Route selected: cost_analysis" in answer
    assert "Retrieval source:" in answer


def test_optimization_question_correlates_recommendations_costs_and_resources(
    test_settings,
):
    storage = create_storage_provider(test_settings)
    context = OperationContext.create("tenant-a", "subscription-a")
    resource_id = "/subscriptions/a/resourceGroups/rg/providers/Microsoft.Network/publicIPAddresses/pip-a"
    storage.cost_facts.upsert_many(
        "tenant-a",
        [
            CostFact(
                **context.document_fields(),
                date="2026-06-01",
                resourceId=resource_id,
                resourceGroup="rg",
                serviceName="IP Addresses",
                costAmount=12,
                currency="INR",
                sourceSystem="Azure Cost Management",
                sourceTimestamp="2026-06-01T00:00:00Z",
            )
        ],
    )
    storage.resources.upsert_many(
        "tenant-a",
        [
            ResourceFact(
                **context.document_fields(),
                resourceId=resource_id,
                resourceName="pip-a",
                resourceType="Public IP Address",
                resourceGroup="rg",
                wasteLevel="MEDIUM",
                recommendation="Delete Public IP",
                estimatedSavings=12,
                savingsCurrency="INR",
                sourceSystem="Azure Resource Graph",
                sourceTimestamp="2026-06-01T00:00:00Z",
            )
        ],
    )
    storage.recommendations.upsert_many(
        "tenant-a",
        [
            Recommendation(
                **context.document_fields(),
                resourceId=resource_id,
                title="pip-a optimization",
                content="Delete Public IP",
                estimatedSavings=12,
                currency="INR",
                sourceSystem="Rule-based processing",
                sourceTimestamp="2026-06-01T00:00:00Z",
                evidence={"wasteLevel": "MEDIUM", "costBasis": "actual"},
            )
        ],
    )
    advisor = FinOpsAdvisor(
        test_settings,
        tenant_id="tenant-a",
        subscription_ids=["subscription-a"],
    )

    answer = advisor.ask("How can I reduce my spend?")

    assert "Route selected" not in answer
    assert "Retrieval source" not in answer
    assert "pip-a (Public IP Address)" in answer
    assert "Delete Public IP" in answer
    assert "observed spend INR 12.00" in answer
    assert "waste level MEDIUM" in answer


def test_utilization_question_only_returns_compute_resources(test_settings):
    storage = create_storage_provider(test_settings)
    context = OperationContext.create("tenant-a", "subscription-a")
    storage.resources.upsert_many(
        "tenant-a",
        [
            ResourceFact(
                **context.document_fields(),
                resourceId="/subscriptions/a/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-a",
                resourceName="vm-a",
                resourceType="Virtual Machine",
                resourceGroup="rg",
                wasteLevel="HIGH",
                recommendation="Rightsize VM",
                estimatedSavings=20,
                savingsCurrency="INR",
                sourceSystem="Azure Monitor",
                sourceTimestamp="2026-06-01T00:00:00Z",
                attributes={
                    "cpu_avg_percent": 2.0,
                    "memory_avg_percent": 12.0,
                    "rule_id": "oversized_vm",
                },
            ),
            ResourceFact(
                **context.document_fields(),
                resourceId="/subscriptions/a/resourceGroups/rg/providers/Microsoft.Network/publicIPAddresses/pip-a",
                resourceName="pip-a",
                resourceType="Public IP Address",
                resourceGroup="rg",
                wasteLevel="MEDIUM",
                recommendation="Delete Public IP",
                estimatedSavings=5,
                savingsCurrency="INR",
                sourceSystem="Azure Resource Graph",
                sourceTimestamp="2026-06-01T00:00:00Z",
                attributes={"cpu_avg_percent": 0.0, "memory_avg_percent": 0.0},
            ),
        ],
    )
    advisor = FinOpsAdvisor(
        test_settings,
        tenant_id="tenant-a",
        subscription_ids=["subscription-a"],
    )

    answer = advisor.ask("which VM is underutilized?")

    assert "Route selected" not in answer
    assert "Retrieval source" not in answer
    assert "vm-a" in answer
    assert "pip-a" not in answer


class _NarrativeLLMResponse:
    content = (
        "Executive diagnosis\n"
        "Application Gateway is a major cost driver and AKS has quantified savings.\n\n"
        "Top spend categories\n"
        "- Application Gateway\n\n"
        "Root causes\n"
        "- Underutilized AKS capacity\n\n"
        "Prioritized actions\n"
        "- Priority High: Enable autoscaler on aks-a\n\n"
        "Estimated savings\n"
        "- INR 100/month"
    )
    usage_metadata = {}
    response_metadata = {}


class _NarrativeLLM:
    def __init__(self):
        self.messages = None

    def invoke(self, messages):
        self.messages = messages
        return _NarrativeLLMResponse()


def test_optimization_uses_llm_narrative_when_available(test_settings):
    storage = create_storage_provider(test_settings)
    context = OperationContext.create("tenant-a", "subscription-a")
    resource_id = "/subscriptions/a/resourceGroups/rg/providers/Microsoft.ContainerService/managedClusters/aks-a"
    storage.cost_facts.upsert_many(
        "tenant-a",
        [
            CostFact(
                **context.document_fields(),
                date="2026-06-01",
                resourceId=resource_id,
                resourceGroup="rg",
                serviceName="Azure Kubernetes Service",
                costAmount=200,
                currency="INR",
                sourceSystem="Azure Cost Management",
                sourceTimestamp="2026-06-01T00:00:00Z",
            )
        ],
    )
    storage.resources.upsert_many(
        "tenant-a",
        [
            ResourceFact(
                **context.document_fields(),
                resourceId=resource_id,
                resourceName="aks-a",
                resourceType="AKS Cluster",
                resourceGroup="rg",
                wasteLevel="HIGH",
                recommendation="Enable Autoscaler",
                estimatedSavings=100,
                savingsCurrency="INR",
                sourceSystem="Azure Monitor",
                sourceTimestamp="2026-06-01T00:00:00Z",
                attributes={"cpu_avg_percent": 8.0, "memory_avg_percent": 40.0},
            )
        ],
    )
    storage.recommendations.upsert_many(
        "tenant-a",
        [
            Recommendation(
                **context.document_fields(),
                resourceId=resource_id,
                title="aks-a optimization",
                content="Enable Autoscaler",
                estimatedSavings=100,
                currency="INR",
                sourceSystem="Rule-based processing",
                sourceTimestamp="2026-06-01T00:00:00Z",
                evidence={"wasteLevel": "HIGH", "costBasis": "actual"},
            )
        ],
    )
    llm = _NarrativeLLM()
    advisor = FinOpsAdvisor(
        test_settings,
        tenant_id="tenant-a",
        subscription_ids=["subscription-a"],
        llm=llm,
    )

    answer = advisor.ask("How can I reduce my spend?")

    assert "Executive diagnosis" in answer
    assert "Route selected" not in answer
    assert "Retrieval source" not in answer
    assert llm.messages is not None
    prompt_text = "\n".join(str(message.content) for message in llm.messages)
    assert "FinOps analysis JSON" in prompt_text
    assert "top_spend_categories" in prompt_text
    assert "opportunities" in prompt_text
