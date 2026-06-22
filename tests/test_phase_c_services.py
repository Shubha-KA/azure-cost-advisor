from __future__ import annotations

import pytest

from src.domain.models import AzureSubscription, Tenant
from src.scheduler.run import run_scheduled
from src.services.multi_tenant_pipeline import MultiTenantPipelineService
from src.storage.factory import create_storage_provider
from src.domain.context import OperationContext
from src.processor.normalizer import ProcessorError, RawDataLoader


def _seed_target(storage, tenant_id: str, subscription_id: str) -> None:
    storage.tenants.upsert(
        tenant_id,
        Tenant(
            tenantId=tenant_id,
            displayName=tenant_id,
            onboardingStatus="completed",
            correlationId=f"correlation-{tenant_id}",
        ),
    )
    storage.subscriptions.upsert(
        tenant_id,
        AzureSubscription(
            tenantId=tenant_id,
            subscriptionId=subscription_id,
            displayName=subscription_id,
            selected=True,
            onboardingStatus="validated",
            correlationId=f"correlation-{subscription_id}",
        ),
    )


def test_multi_tenant_collection_processing_and_isolation(test_settings) -> None:
    storage = create_storage_provider(test_settings)
    _seed_target(storage, "tenant-a", "subscription-a1")
    _seed_target(storage, "tenant-a", "subscription-a2")
    _seed_target(storage, "tenant-b", "subscription-b1")

    summary = MultiTenantPipelineService(
        test_settings, storage=storage
    ).run_once()

    assert summary.tenants_processed == 2
    assert summary.subscriptions_processed == 3
    assert summary.collection_runs_created == 3
    assert summary.processing_runs_created == 3
    assert summary.cost_facts_generated > 0
    assert summary.resource_facts_generated > 0
    assert set(summary.reconciliation_results.values()) == {"passed"}
    assert all(result.status == "completed" for result in summary.results)

    for result in summary.results:
        cost_facts = storage.cost_facts.list_for_run(
            result.tenant_id,
            result.subscription_id,
            result.processing_run_id,
        )
        resources = storage.resources.list_for_run(
            result.tenant_id,
            result.subscription_id,
            result.processing_run_id,
        )
        metadata = storage.processing_metadata.list_latest(
            result.tenant_id, result.subscription_id
        )
        collection_runs = [
            item for item in metadata
            if item.get("metadataType") == "collectionRun"
        ]
        processing_runs = [
            item for item in metadata
            if item.get("metadataType") == "processingRun"
        ]

        assert cost_facts
        assert resources
        assert {fact.tenant_id for fact in cost_facts} == {result.tenant_id}
        assert {fact.subscription_id for fact in cost_facts} == {
            result.subscription_id
        }
        assert {fact.currency for fact in cost_facts} == {"USD"}
        assert all(
            fact.resource_id == fact.resource_id.lower()
            for fact in cost_facts
        )
        assert collection_runs[0]["recordsCollected"] > 0
        assert processing_runs[0]["reconciliationStatus"] == "passed"
        assert processing_runs[0]["recordCounts"]["costFacts"] == len(cost_facts)
        assert processing_runs[0]["recordCounts"]["resourceFacts"] == len(resources)
        assert processing_runs[0]["summary"]["cost_reconciliation"]["status"] == "passed"

    assert storage.cost_facts.list_latest("tenant-c", "subscription-a1") == []
    assert storage.cost_facts.list_latest("tenant-a", "subscription-b1") == []


def test_manual_target_filter_runs_one_subscription(test_settings) -> None:
    storage = create_storage_provider(test_settings)
    _seed_target(storage, "tenant-a", "subscription-a1")
    _seed_target(storage, "tenant-a", "subscription-a2")
    service = MultiTenantPipelineService(test_settings, storage=storage)

    summary = service.run_once(
        tenant_id="tenant-a", subscription_id="subscription-a2"
    )

    assert summary.tenants_processed == 1
    assert summary.subscriptions_processed == 1
    assert summary.results[0].subscription_id == "subscription-a2"


def test_scheduler_runs_configured_cycles_without_waiting(test_settings) -> None:
    storage = create_storage_provider(test_settings)
    _seed_target(storage, "tenant-a", "subscription-a1")
    service = MultiTenantPipelineService(test_settings, storage=storage)
    sleeps = []

    summaries = run_scheduled(
        service,
        interval_seconds=60,
        max_cycles=2,
        sleep=sleeps.append,
    )

    assert len(summaries) == 2
    assert sleeps == [60]
    assert all(item.collection_runs_created == 1 for item in summaries)
    assert all(item.processing_runs_created == 1 for item in summaries)


def test_legacy_mode_remains_single_subscription(test_settings) -> None:
    service = MultiTenantPipelineService(test_settings)
    summary = service.run_once()

    assert summary.tenants_processed == 1
    assert summary.subscriptions_processed == 1
    assert summary.collection_runs_created == 1
    assert summary.processing_runs_created == 1


def test_scoped_processing_never_falls_back_to_another_latest_file(
    test_settings,
) -> None:
    test_settings.raw_path.mkdir(parents=True, exist_ok=True)
    (test_settings.raw_path / "costs_latest.json").write_text(
        '{"records": [{"costAmount": 999, "currency": "USD"}]}',
        encoding="utf-8",
    )
    context = OperationContext.create("tenant-a", "subscription-a")
    loader = RawDataLoader(
        test_settings,
        context,
        create_storage_provider(test_settings),
    )

    with pytest.raises(ProcessorError, match="Tenant-scoped raw payload"):
        loader.load("costs")
