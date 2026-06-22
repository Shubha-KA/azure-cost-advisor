"""Run collection and processing for all eligible tenant subscriptions."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from src.auth.customer_credentials import CustomerTenantCredentialFactory
from src.collector.run import OrchestrationReport, run_all
from src.config import Settings, get_settings
from src.domain.context import OperationContext
from src.processor.run import ProcessingReport, run_processing
from src.storage.factory import create_storage_provider

logger = logging.getLogger(__name__)


@dataclass
class SubscriptionRunResult:
    tenant_id: str
    subscription_id: str
    collection_run_id: str
    processing_run_id: str
    collection: OrchestrationReport | None = None
    processing: ProcessingReport | None = None
    status: str = "pending"
    errors: list[str] = field(default_factory=list)


@dataclass
class MultiTenantRunSummary:
    started_at: str
    completed_at: str = ""
    tenants_processed: int = 0
    subscriptions_processed: int = 0
    collection_runs_created: int = 0
    processing_runs_created: int = 0
    cost_facts_generated: int = 0
    resource_facts_generated: int = 0
    recommendation_count: int = 0
    search_documents_indexed: int = 0
    reconciliation_results: dict[str, str] = field(default_factory=dict)
    results: list[SubscriptionRunResult] = field(default_factory=list)


class MultiTenantPipelineService:
    def __init__(
        self,
        settings: Settings | None = None,
        storage=None,
        credential_factory: Callable[[str, str], Any] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.storage = storage or create_storage_provider(self.settings)
        self.credential_factory = credential_factory or (
            CustomerTenantCredentialFactory(
                self.settings,
                self.storage,
            ).for_subscription
        )

    def run_once(
        self,
        *,
        tenant_id: str | None = None,
        subscription_id: str | None = None,
        continue_on_error: bool = True,
    ) -> MultiTenantRunSummary:
        summary = MultiTenantRunSummary(
            started_at=datetime.now(timezone.utc).isoformat()
        )
        targets = self._targets(tenant_id, subscription_id)
        summary.tenants_processed = len({target[0] for target in targets})
        summary.subscriptions_processed = len(targets)

        for target_tenant, target_subscription in targets:
            context = OperationContext.create(
                target_tenant, target_subscription
            )
            result = SubscriptionRunResult(
                tenant_id=target_tenant,
                subscription_id=target_subscription,
                collection_run_id=context.collection_run_id,
                processing_run_id=context.processing_run_id,
            )
            summary.results.append(result)
            credential = self._credential_for(
                target_tenant, target_subscription
            )
            try:
                result.collection = run_all(
                    export_csv=True,
                    continue_on_error=continue_on_error,
                    settings=self.settings,
                    context=context,
                    storage=self.storage,
                    credential=credential,
                )
                summary.collection_runs_created += 1
                if result.collection.errors and not continue_on_error:
                    raise RuntimeError("; ".join(result.collection.errors))

                _, result.processing = run_processing(
                    settings=self.settings,
                    context=context,
                    storage=self.storage,
                )
                summary.processing_runs_created += 1
                summary.cost_facts_generated += result.processing.cost_fact_count
                summary.resource_facts_generated += (
                    result.processing.resource_fact_count
                )
                recommendations = self.storage.recommendations.list_latest(
                    target_tenant, target_subscription
                )
                summary.recommendation_count += len(recommendations)
                key = f"{target_tenant}/{target_subscription}"
                summary.reconciliation_results[key] = (
                    result.processing.reconciliation_status
                )
                result.status = (
                    "partial"
                    if result.collection.errors
                    else "completed"
                )
                if (
                    self.settings.openai_configured
                    and (
                        self.settings.search_provider == "faiss"
                        or self.settings.azure_search_configured
                    )
                ):
                    from src.ai.service import AIService

                    summary.search_documents_indexed += (
                        AIService(
                            self.settings, storage=self.storage
                        ).index_subscription(
                            target_tenant, target_subscription
                        )
                    )
            except Exception as exc:
                result.status = "failed"
                result.errors.append(str(exc))
                logger.exception(
                    "tenant_run_failed tenant_id=%s subscription_id=%s "
                    "collection_run_id=%s processing_run_id=%s",
                    target_tenant,
                    target_subscription,
                    context.collection_run_id,
                    context.processing_run_id,
                )
                if not continue_on_error:
                    break

        summary.completed_at = datetime.now(timezone.utc).isoformat()
        logger.info(
            "multi_tenant_run_summary tenants=%d subscriptions=%d "
            "collection_runs=%d processing_runs=%d cost_facts=%d "
            "resource_facts=%d recommendations=%d",
            summary.tenants_processed,
            summary.subscriptions_processed,
            summary.collection_runs_created,
            summary.processing_runs_created,
            summary.cost_facts_generated,
            summary.resource_facts_generated,
            summary.recommendation_count,
        )
        return summary

    def _targets(
        self,
        tenant_id: str | None,
        subscription_id: str | None,
    ) -> list[tuple[str, str]]:
        targets: list[tuple[str, str]] = []
        for tenant in self.storage.tenants.list():
            if tenant_id and tenant.tenant_id != tenant_id:
                continue
            for subscription in self.storage.subscriptions.list(tenant.tenant_id):
                if subscription_id and subscription.subscription_id != subscription_id:
                    continue
                eligible = (
                    subscription.selected
                    and subscription.onboarding_status == "validated"
                    and subscription.status.lower() not in {"disabled", "deleted"}
                )
                if eligible:
                    targets.append(
                        (tenant.tenant_id, subscription.subscription_id)
                    )

        if targets:
            return targets
        if tenant_id or subscription_id:
            return []
        if self.settings.auth_mode.lower() == "legacy":
            return [
                (
                    self.settings.effective_tenant_id,
                    self.settings.effective_subscription_id,
                )
            ]
        return []

    def _credential_for(self, tenant_id: str, subscription_id: str):
        return self.credential_factory(tenant_id, subscription_id)
