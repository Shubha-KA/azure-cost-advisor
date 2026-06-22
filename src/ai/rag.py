"""Tenant-scoped Azure AI Search retrieval and Azure OpenAI reasoning."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import AzureChatOpenAI

from src.ai.prompts import HYBRID_COPILOT_PROMPT, RAG_PROMPT, RECOMMENDATIONS_PROMPT
from src.config import Settings, get_settings
from src.search.factory import create_search_provider
from src.search.knowledge import KnowledgeService
from src.storage.factory import create_storage_provider

logger = logging.getLogger(__name__)


class RAGError(Exception):
    pass


class RAGPipeline:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        storage=None,
        search_provider=None,
        llm=None,
    ) -> None:
        self.settings = settings or get_settings()
        self.storage = storage or create_storage_provider(self.settings)
        self._search_provider = search_provider
        self._llm = llm

    def _get_search_provider(self):
        if self._search_provider is None:
            self._search_provider = create_search_provider(self.settings)
        return self._search_provider

    def _get_llm(self):
        if self._llm is not None:
            return self._llm
        if not self.settings.openai_configured:
            raise RAGError("Azure OpenAI is not configured")
        kwargs = {}
        if (
            self.settings.use_managed_identity
            and not self.settings.azure_openai_api_key
        ):
            from azure.identity import (
                DefaultAzureCredential,
                get_bearer_token_provider,
            )

            kwargs["azure_ad_token_provider"] = get_bearer_token_provider(
                DefaultAzureCredential(),
                "https://cognitiveservices.azure.com/.default",
            )
        else:
            kwargs["api_key"] = self.settings.azure_openai_api_key
        self._llm = AzureChatOpenAI(
            azure_endpoint=self.settings.azure_openai_endpoint.rstrip("/"),
            api_version=self.settings.azure_openai_api_version,
            azure_deployment=self.settings.azure_openai_deployment_name,
            temperature=0.2,
            **kwargs,
        )
        return self._llm

    def build_index(
        self,
        rebuild: bool = False,
        *,
        tenant_id: str | None = None,
        subscription_id: str | None = None,
    ) -> int:
        tenant_id = tenant_id or self.settings.effective_tenant_id
        subscription_id = (
            subscription_id or self.settings.effective_subscription_id
        )
        provider = self._get_search_provider()
        count = KnowledgeService(
            self.storage, provider
        ).index_subscription(tenant_id, subscription_id)
        logger.info(
            "search_index_summary provider=%s tenant_id=%s "
            "subscription_id=%s documents=%d",
            self.settings.search_provider,
            tenant_id,
            subscription_id,
            count,
        )
        return count

    def retrieve(
        self,
        query: str,
        k: int = 6,
        *,
        tenant_id: str | None = None,
        subscription_id: str | None = None,
    ) -> list[dict[str, Any]]:
        tenant_id = tenant_id or self.settings.effective_tenant_id
        subscription_id = (
            subscription_id or self.settings.effective_subscription_id
        )
        results = self._get_search_provider().search(
            tenant_id, subscription_id, query, top=k
        )
        logger.warning(
            "azure_ai_search_retrieval provider=%s tenant_id=%s subscription_id=%s "
            "query=%r top=%d retrieved=%d documents=%s",
            self.settings.search_provider,
            tenant_id,
            subscription_id,
            query,
            k,
            len(results),
            [
                {
                    "id": result.metadata.get("id"),
                    "type": result.metadata.get("documentType"),
                    "title": result.metadata.get("title")
                    or result.metadata.get("resourceName")
                    or result.metadata.get("resourceId"),
                    "score": round(result.score, 4),
                }
                for result in results
            ],
        )
        return [
            {
                "content": result.content,
                "metadata": result.metadata,
                "score": result.score,
            }
            for result in results
        ]

    def invoke(
        self,
        query: str,
        chat_history: str = "",
        prompt: ChatPromptTemplate | None = None,
        k: int = 6,
        *,
        tenant_id: str | None = None,
        subscription_id: str | None = None,
        operation: str = "chat",
    ) -> dict[str, Any]:
        tenant_id = tenant_id or self.settings.effective_tenant_id
        subscription_id = (
            subscription_id or self.settings.effective_subscription_id
        )
        prompt = prompt or RAG_PROMPT
        started = time.perf_counter()
        search_started = time.perf_counter()
        documents = self.retrieve(
            query,
            k,
            tenant_id=tenant_id,
            subscription_id=subscription_id,
        )
        search_latency = (time.perf_counter() - search_started) * 1000
        context = "\n\n".join(item["content"] for item in documents)
        messages = prompt.format_messages(
            context=context or "No matching tenant-scoped documents.",
            chat_history=chat_history or "None",
            input=query,
        )
        response = self._get_llm().invoke(messages)
        latency = (time.perf_counter() - started) * 1000
        usage = _token_usage(response)
        answer = str(getattr(response, "content", response))
        self._persist_execution(
            tenant_id,
            subscription_id,
            operation,
            latency,
            search_latency,
            len(documents),
            usage,
        )
        return {
            "answer": answer,
            "context": documents,
            "source": "azure_openai_ai_search",
            "usage": usage,
            "latency_ms": latency,
            "search_latency_ms": search_latency,
            "model": self.settings.azure_openai_deployment_name,
        }

    def invoke_hybrid(
        self,
        query: str,
        *,
        structured_facts: str,
        chat_history: str = "",
        k: int = 8,
        tenant_id: str | None = None,
        subscription_id: str | None = None,
        operation: str = "knowledge_advisory",
    ) -> dict[str, Any]:
        tenant_id = tenant_id or self.settings.effective_tenant_id
        subscription_id = (
            subscription_id or self.settings.effective_subscription_id
        )
        started = time.perf_counter()
        search_started = time.perf_counter()
        documents = self.retrieve(
            query,
            k,
            tenant_id=tenant_id,
            subscription_id=subscription_id,
        )
        search_latency = (time.perf_counter() - search_started) * 1000
        search_context = "\n\n".join(item["content"] for item in documents)
        messages = HYBRID_COPILOT_PROMPT.format_messages(
            search_context=search_context or "No matching Azure AI Search documents.",
            structured_facts=structured_facts or "No structured subscription facts available.",
            chat_history=chat_history or "None",
            input=query,
        )
        response = self._get_llm().invoke(messages)
        latency = (time.perf_counter() - started) * 1000
        usage = _token_usage(response)
        answer = str(getattr(response, "content", response))
        self._persist_execution(
            tenant_id,
            subscription_id,
            operation,
            latency,
            search_latency,
            len(documents),
            usage,
        )
        return {
            "answer": answer,
            "context": documents,
            "source": "hybrid_cosmos_ai_search_openai",
            "usage": usage,
            "latency_ms": latency,
            "search_latency_ms": search_latency,
            "model": self.settings.azure_openai_deployment_name,
            "structured_facts": structured_facts,
        }

    def generate_recommendations(
        self,
        k: int = 25,
        *,
        tenant_id: str | None = None,
        subscription_id: str | None = None,
    ) -> dict[str, Any]:
        return self.invoke(
            "List every explicit waste finding and Azure Advisor recommendation, "
            "then summarize cost anomalies and quantified savings.",
            prompt=RECOMMENDATIONS_PROMPT,
            k=k,
            tenant_id=tenant_id,
            subscription_id=subscription_id,
            operation="recommendations",
        )

    def generate_executive_summary(
        self, tenant_id: str, subscription_id: str
    ) -> dict[str, Any]:
        return self.invoke(
            "Generate an executive FinOps summary of spend, trends, waste, "
            "savings, risks, and next actions.",
            tenant_id=tenant_id,
            subscription_id=subscription_id,
            operation="executive_summary",
            k=12,
        )

    def _persist_execution(
        self,
        tenant_id,
        subscription_id,
        operation,
        latency,
        search_latency,
        retrieved,
        usage,
    ) -> None:
        metadata = self.storage.processing_metadata.list_latest(
            tenant_id, subscription_id
        )
        processing = next(
            (
                item
                for item in metadata
                if item.get("metadataType") == "processingRun"
            ),
            {},
        )
        self.storage.processing_metadata.upsert(
            tenant_id,
            {
                "tenantId": tenant_id,
                "subscriptionId": subscription_id,
                "collectionRunId": processing.get(
                    "collectionRunId", "ai-unlinked"
                ),
                "processingRunId": processing.get(
                    "processingRunId", "ai-unlinked"
                ),
                "correlationId": str(uuid4()),
                "schemaVersion": 1,
                "metadataType": "aiExecution",
                "metadataId": f"ai-{uuid4()}",
                "operation": operation,
                "model": self.settings.azure_openai_deployment_name,
                "promptTokens": usage["prompt_tokens"],
                "completionTokens": usage["completion_tokens"],
                "totalTokens": usage["total_tokens"],
                "latencyMs": round(latency, 2),
                "searchLatencyMs": round(search_latency, 2),
                "retrievedDocuments": retrieved,
                "searchProvider": self.settings.search_provider,
                "createdAt": datetime.now(timezone.utc).isoformat(),
            },
        )


def _token_usage(response) -> dict[str, int]:
    usage = getattr(response, "usage_metadata", None) or {}
    if usage:
        prompt = int(usage.get("input_tokens", 0))
        completion = int(usage.get("output_tokens", 0))
        return {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": int(
                usage.get("total_tokens", prompt + completion)
            ),
        }
    token_usage = getattr(response, "response_metadata", {}).get(
        "token_usage", {}
    )
    return {
        "prompt_tokens": int(token_usage.get("prompt_tokens", 0)),
        "completion_tokens": int(token_usage.get("completion_tokens", 0)),
        "total_tokens": int(token_usage.get("total_tokens", 0)),
    }
