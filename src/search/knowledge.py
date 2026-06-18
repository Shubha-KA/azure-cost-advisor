"""Build tenant-scoped AI knowledge documents from authoritative repositories."""

from __future__ import annotations

import json

from src.domain.ids import deterministic_id
from src.search.models import KnowledgeDocument


class KnowledgeService:
    def __init__(self, storage, search_provider) -> None:
        self.storage = storage
        self.search_provider = search_provider

    def build_documents(
        self, tenant_id: str, subscription_id: str
    ) -> list[KnowledgeDocument]:
        documents: list[KnowledgeDocument] = []
        costs = self.storage.cost_facts.list_latest(
            tenant_id, subscription_id
        )
        resources = self.storage.resources.list_latest(
            tenant_id, subscription_id
        )
        recommendations = self.storage.recommendations.list_latest(
            tenant_id, subscription_id
        )
        metadata = self.storage.processing_metadata.list_latest(
            tenant_id, subscription_id
        )

        for fact in costs:
            documents.append(
                self._document(
                    fact,
                    "cost_fact",
                    f"{fact.service_name} cost on {fact.date}",
                    (
                        f"Cost {fact.currency} {fact.cost_amount:.2f} for "
                        f"{fact.service_name} in {fact.resource_group}, "
                        f"location {fact.location}, resource {fact.resource_id or 'unallocated'}."
                    ),
                    {
                        "currency": fact.currency,
                        "costAmount": fact.cost_amount,
                        "date": str(fact.date),
                        "resourceId": fact.resource_id,
                    },
                )
            )
        for fact in resources:
            documents.append(
                self._document(
                    fact,
                    "resource_fact",
                    f"{fact.resource_name} resource analysis",
                    (
                        f"Resource {fact.resource_name} is a {fact.resource_type} "
                        f"in {fact.resource_group}. Cost basis {fact.cost_basis}; "
                        f"estimated monthly cost {fact.estimated_cost_currency} "
                        f"{fact.estimated_monthly_cost:.2f}; waste level "
                        f"{fact.waste_level}; recommendation {fact.recommendation or 'none'}."
                    ),
                    {
                        "resourceId": fact.resource_id,
                        "resourceType": fact.resource_type,
                        "wasteLevel": fact.waste_level,
                    },
                )
            )
            documents.append(
                self._document(
                    fact,
                    "resource_inventory_summary",
                    f"{fact.resource_type}: {fact.resource_name}",
                    (
                        f"Historical resource inventory record for "
                        f"{fact.resource_name}, type {fact.resource_type}, "
                        f"resource group {fact.resource_group}, location {fact.location}."
                    ),
                    {"resourceId": fact.resource_id},
                )
            )
        for recommendation in recommendations:
            documents.append(
                self._document(
                    recommendation,
                    "recommendation",
                    recommendation.title or "FinOps recommendation",
                    recommendation.content,
                    recommendation.evidence,
                )
            )
        for item in metadata:
            if item.get("metadataType") != "processingRun":
                continue
            documents.append(
                KnowledgeDocument(
                    id=deterministic_id(
                        tenant_id,
                        subscription_id,
                        item.get("processingRunId"),
                        "processing_summary",
                    ),
                    tenantId=tenant_id,
                    subscriptionId=subscription_id,
                    collectionRunId=str(item.get("collectionRunId", "")),
                    processingRunId=str(item.get("processingRunId", "")),
                    sourceSystem="Processing Service",
                    schemaVersion=int(item.get("schemaVersion", 1)),
                    documentType="processing_summary",
                    title="Processing and reconciliation summary",
                    content=json.dumps(
                        {
                            "recordCounts": item.get("recordCounts", {}),
                            "reconciliation": item.get("reconciliation", {}),
                            "summary": item.get("summary", {}),
                        },
                        default=str,
                    ),
                    metadataJson=json.dumps(
                        {"status": item.get("status", "")}
                    ),
                )
            )
            summary = item.get("summary", {})
            if summary.get("daily_trend"):
                documents.append(
                    KnowledgeDocument(
                        id=deterministic_id(
                            tenant_id,
                            subscription_id,
                            item.get("processingRunId"),
                            "cost_trend",
                        ),
                        tenantId=tenant_id,
                        subscriptionId=subscription_id,
                        collectionRunId=str(item.get("collectionRunId", "")),
                        processingRunId=str(item.get("processingRunId", "")),
                        sourceSystem="Azure Cost Management",
                        schemaVersion=1,
                        documentType="cost_trend",
                        title="Daily Azure cost trend",
                        content=json.dumps(summary["daily_trend"], default=str),
                        metadataJson=json.dumps(
                            {"totalCost": summary.get("total_cost", {})}
                        ),
                    )
                )
        advisor = self.storage.raw_payloads.load_latest(
            tenant_id, subscription_id, "advisor"
        )
        if advisor:
            context = advisor.get("context", {})
            for finding in advisor.get("recommendations", []):
                documents.append(
                    KnowledgeDocument(
                        id=deterministic_id(
                            tenant_id,
                            subscription_id,
                            finding.get("recommendationId"),
                            "advisor",
                        ),
                        tenantId=tenant_id,
                        subscriptionId=subscription_id,
                        collectionRunId=str(
                            context.get("collectionRunId", "legacy")
                        ),
                        processingRunId=str(
                            context.get("processingRunId", "not_processed")
                        ),
                        sourceSystem="Azure Advisor",
                        schemaVersion=1,
                        documentType="advisor_finding",
                        title=str(finding.get("problem", "Advisor finding")),
                        content=(
                            f"{finding.get('problem', '')}. "
                            f"{finding.get('solution', '')}. "
                            f"Resource {finding.get('resourceName', '')}."
                        ),
                        metadataJson=json.dumps(finding, default=str),
                    )
                )
        return documents

    def index_subscription(
        self, tenant_id: str, subscription_id: str
    ) -> int:
        documents = self.build_documents(tenant_id, subscription_id)
        self.search_provider.ensure_index()
        return self.search_provider.index_documents(tenant_id, documents)

    @staticmethod
    def _document(entity, document_type, title, content, metadata):
        payload = entity.model_dump(by_alias=True, mode="json")
        entity_id = (
            payload.get("factId")
            or payload.get("resourceFactId")
            or payload.get("recommendationId")
        )
        return KnowledgeDocument(
            id=deterministic_id(entity_id, document_type),
            tenantId=entity.tenant_id,
            subscriptionId=entity.subscription_id,
            collectionRunId=entity.collection_run_id,
            processingRunId=entity.processing_run_id,
            sourceSystem=entity.source_system,
            schemaVersion=entity.schema_version,
            documentType=document_type,
            title=title,
            content=content,
            metadataJson=json.dumps(metadata, default=str),
        )
