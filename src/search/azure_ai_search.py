"""Azure AI Search hybrid and semantic tenant-scoped provider."""

from __future__ import annotations

import json
import time
from typing import Sequence

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SearchableField,
    SemanticConfiguration,
    SemanticField,
    SemanticPrioritizedFields,
    SemanticSearch,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)
from azure.search.documents.models import VectorizedQuery

from src.ai.embeddings import build_embeddings
from src.repositories.errors import TenantScopeError
from src.search.models import KnowledgeDocument, SearchResult


class AzureAISearchProvider:
    def __init__(
        self,
        settings,
        *,
        index_client=None,
        search_client=None,
        embeddings=None,
    ) -> None:
        self.settings = settings
        if not settings.azure_search_api_key:
            from azure.identity import DefaultAzureCredential

            credential = DefaultAzureCredential()
        else:
            credential = AzureKeyCredential(settings.azure_search_api_key or "test")
        self.index_client = index_client or SearchIndexClient(
            settings.azure_search_endpoint, credential
        )
        self.search_client = search_client or SearchClient(
            settings.azure_search_endpoint,
            settings.azure_search_index_name,
            credential,
        )
        self.embeddings = embeddings or build_embeddings(settings)
        self.last_search_latency_ms = 0.0

    def ensure_index(self) -> None:
        fields = [
            SimpleField(name="id", type=SearchFieldDataType.String, key=True),
            SimpleField(
                name="tenantId",
                type=SearchFieldDataType.String,
                filterable=True,
                facetable=True,
            ),
            SimpleField(
                name="subscriptionId",
                type=SearchFieldDataType.String,
                filterable=True,
                facetable=True,
            ),
            SimpleField(
                name="collectionRunId",
                type=SearchFieldDataType.String,
                filterable=True,
            ),
            SimpleField(
                name="processingRunId",
                type=SearchFieldDataType.String,
                filterable=True,
            ),
            SimpleField(
                name="sourceSystem",
                type=SearchFieldDataType.String,
                filterable=True,
                facetable=True,
            ),
            SimpleField(
                name="schemaVersion",
                type=SearchFieldDataType.Int32,
                filterable=True,
            ),
            SimpleField(
                name="documentType",
                type=SearchFieldDataType.String,
                filterable=True,
                facetable=True,
            ),
            SearchableField(name="title", type=SearchFieldDataType.String),
            SearchableField(name="content", type=SearchFieldDataType.String),
            SimpleField(name="metadataJson", type=SearchFieldDataType.String),
            SearchField(
                name="contentVector",
                type=SearchFieldDataType.Collection(
                    SearchFieldDataType.Single
                ),
                searchable=True,
                vector_search_dimensions=(
                    self.settings.azure_search_vector_dimensions
                ),
                vector_search_profile_name="finops-vector-profile",
            ),
        ]
        index = SearchIndex(
            name=self.settings.azure_search_index_name,
            fields=fields,
            vector_search=VectorSearch(
                algorithms=[
                    HnswAlgorithmConfiguration(name="finops-hnsw")
                ],
                profiles=[
                    VectorSearchProfile(
                        name="finops-vector-profile",
                        algorithm_configuration_name="finops-hnsw",
                    )
                ],
            ),
            semantic_search=SemanticSearch(
                configurations=[
                    SemanticConfiguration(
                        name=self.settings.azure_search_semantic_config,
                        prioritized_fields=SemanticPrioritizedFields(
                            title_field=SemanticField(field_name="title"),
                            content_fields=[
                                SemanticField(field_name="content")
                            ],
                        ),
                    )
                ]
            ),
        )
        self.index_client.create_or_update_index(index)

    def index_documents(
        self, tenant_id: str, documents: Sequence[KnowledgeDocument]
    ) -> int:
        if any(document.tenant_id != tenant_id for document in documents):
            raise TenantScopeError(
                "All search documents must match the indexing tenantId"
            )
        if not documents:
            return 0
        texts = [document.content for document in documents]
        vectors = self.embeddings.embed_documents(texts)
        payload = []
        for document, vector in zip(documents, vectors):
            row = document.model_dump(by_alias=True)
            row["contentVector"] = vector
            payload.append(row)
        results = self.search_client.upload_documents(payload)
        failures = [
            result for result in results
            if not getattr(result, "succeeded", False)
        ]
        if failures:
            raise RuntimeError(
                f"Azure AI Search rejected {len(failures)} documents"
            )
        return len(payload)

    def search(
        self,
        tenant_id: str,
        subscription_id: str,
        query: str,
        *,
        top: int = 6,
    ) -> list[SearchResult]:
        if not tenant_id or not subscription_id:
            raise TenantScopeError(
                "tenantId and subscriptionId are required for search"
            )
        vector = self.embeddings.embed_query(query)
        vector_query = VectorizedQuery(
            vector=vector,
            k_nearest_neighbors=max(top, 10),
            fields="contentVector",
        )
        escaped_tenant = tenant_id.replace("'", "''")
        escaped_subscription = subscription_id.replace("'", "''")
        started = time.perf_counter()
        results = self.search_client.search(
            search_text=query,
            vector_queries=[vector_query],
            filter=(
                f"tenantId eq '{escaped_tenant}' and "
                f"subscriptionId eq '{escaped_subscription}'"
            ),
            query_type="semantic",
            semantic_configuration_name=(
                self.settings.azure_search_semantic_config
            ),
            select=[
                "id",
                "tenantId",
                "subscriptionId",
                "collectionRunId",
                "processingRunId",
                "sourceSystem",
                "schemaVersion",
                "documentType",
                "title",
                "content",
                "metadataJson",
            ],
            top=top,
        )
        rows = list(results)
        self.last_search_latency_ms = (
            time.perf_counter() - started
        ) * 1000
        return [
            SearchResult(
                content=row["content"],
                score=float(row.get("@search.score", 0) or 0),
                metadata={
                    "id": row["id"],
                    "tenantId": row["tenantId"],
                    "subscriptionId": row["subscriptionId"],
                    "collectionRunId": row["collectionRunId"],
                    "processingRunId": row["processingRunId"],
                    "sourceSystem": row["sourceSystem"],
                    "schemaVersion": row["schemaVersion"],
                    "documentType": row["documentType"],
                    "title": row["title"],
                    **json.loads(row.get("metadataJson") or "{}"),
                },
            )
            for row in rows
        ]

    def delete_tenant(self, tenant_id: str) -> int:
        if not tenant_id:
            raise TenantScopeError("tenantId is required")
        escaped = tenant_id.replace("'", "''")
        rows = list(
            self.search_client.search(
                search_text="*",
                filter=f"tenantId eq '{escaped}'",
                select=["id"],
                top=1000,
            )
        )
        if rows:
            self.search_client.delete_documents(
                [{"id": row["id"]} for row in rows]
            )
        return len(rows)
