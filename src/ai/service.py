"""Tenant-aware AI knowledge, chat, and insight service."""

from src.ai.advisor import FinOpsAdvisor
from src.ai.rag import RAGPipeline
from src.search.factory import create_search_provider
from src.search.knowledge import KnowledgeService
from src.storage.factory import create_storage_provider


class AIService:
    def __init__(self, settings, *, storage=None, search_provider=None, llm=None):
        self.settings = settings
        self.storage = storage or create_storage_provider(settings)
        self.search_provider = search_provider or create_search_provider(settings)
        self.rag = RAGPipeline(
            settings,
            storage=self.storage,
            search_provider=self.search_provider,
            llm=llm,
        )

    def index_subscription(self, tenant_id: str, subscription_id: str) -> int:
        return KnowledgeService(
            self.storage, self.search_provider
        ).index_subscription(tenant_id, subscription_id)

    def executive_summary(self, tenant_id: str, subscription_id: str):
        return self.rag.generate_executive_summary(
            tenant_id, subscription_id
        )

    def cost_optimization_insights(
        self, tenant_id: str, subscription_id: str
    ):
        return self.rag.invoke(
            "Identify the highest-confidence cost optimization insights using "
            "cost facts, resource facts, Advisor findings, and recommendations.",
            tenant_id=tenant_id,
            subscription_id=subscription_id,
            operation="cost_optimization_insights",
            k=15,
        )
