"""Orchestrate all Azure data collectors."""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.collector.advisor_collector import AdvisorCollector
from src.collector.aks_collector import AksCollector
from src.collector.base import CollectorError, IngestionResult
from src.collector.cost_collector import CostCollector
from src.collector.metrics_collector import MetricsCollector
from src.collector.resource_graph_collector import ResourceGraphCollector
from src.config import get_settings
from src.domain.context import OperationContext
from src.domain.models import AzureSubscription, CollectionRun, Tenant
from src.storage.factory import create_storage_provider

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class OrchestrationReport:
    started_at: str
    tenant_id: str = ""
    subscription_id: str = ""
    collection_run_id: str = ""
    completed_at: str = ""
    results: list[IngestionResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    export_csv: bool = True

    @property
    def success_count(self) -> int:
        return len(self.results)

    @property
    def failure_count(self) -> int:
        return len(self.errors)


def run_all(
    export_csv: bool = True,
    continue_on_error: bool = True,
    *,
    settings=None,
    context: OperationContext | None = None,
    storage=None,
    credential=None,
) -> OrchestrationReport:
    """Run every collector in sequence and optionally export pipeline CSVs."""
    from datetime import datetime, timezone

    settings = settings or get_settings()
    settings.ensure_data_dirs()
    context = context or OperationContext.create(
        settings.effective_tenant_id,
        settings.effective_subscription_id,
    )
    storage = storage or create_storage_provider(settings)
    if storage.tenants.get(context.tenant_id) is None:
        storage.tenants.upsert(
            context.tenant_id,
            Tenant(
                tenantId=context.tenant_id,
                displayName=context.tenant_id,
                correlationId=context.correlation_id,
            ),
        )
    subscriptions = {
        item.subscription_id: item
        for item in storage.subscriptions.list(context.tenant_id)
    }
    if context.subscription_id not in subscriptions:
        storage.subscriptions.upsert(
            context.tenant_id,
            AzureSubscription(
                tenantId=context.tenant_id,
                subscriptionId=context.subscription_id,
                displayName=context.subscription_id,
                correlationId=context.correlation_id,
            ),
        )

    report = OrchestrationReport(
        started_at=datetime.now(timezone.utc).isoformat(),
        tenant_id=context.tenant_id,
        subscription_id=context.subscription_id,
        collection_run_id=context.collection_run_id,
        export_csv=export_csv,
    )
    storage.processing_metadata.upsert(
        context.tenant_id,
        {
            **CollectionRun(
                tenantId=context.tenant_id,
                subscriptionId=context.subscription_id,
                collectionRunId=context.collection_run_id,
                processingRunId=context.processing_run_id,
                correlationId=context.correlation_id,
                status="running",
                startedAt=report.started_at,
            ).model_dump(by_alias=True, mode="json"),
            "metadataType": "collectionRun",
            "startTime": report.started_at,
            "endTime": None,
        },
    )

    collectors = [
        CostCollector(settings, context, storage, credential),
        MetricsCollector(settings, context, storage, credential),
        ResourceGraphCollector(settings, context, storage, credential),
        AdvisorCollector(settings, context, storage, credential),
        AksCollector(settings, context, storage, credential),
    ]

    cost_collector: CostCollector | None = None
    metrics_collector: MetricsCollector | None = None

    for collector in collectors:
        try:
            result = collector.collect()
            report.results.append(result)

            if isinstance(collector, CostCollector):
                cost_collector = collector
            elif isinstance(collector, MetricsCollector):
                metrics_collector = collector

        except CollectorError as exc:
            msg = f"{collector.collector_name}: {exc}"
            logger.error(msg)
            report.errors.append(msg)
            if not continue_on_error:
                break
        except Exception as exc:
            msg = f"{collector.collector_name}: unexpected error — {exc}"
            logger.exception(msg)
            report.errors.append(msg)
            if not continue_on_error:
                break

    if export_csv:
        try:
            if cost_collector:
                cost_collector.export_csv()
            if metrics_collector:
                metrics_collector.export_usage_csv()
        except Exception as exc:
            err = f"csv_export: {exc}"
            logger.error(err)
            report.errors.append(err)

    report.completed_at = datetime.now(timezone.utc).isoformat()
    run_status = (
        "completed"
        if not report.errors
        else "failed"
        if not report.results
        else "partial"
    )
    collection_run = CollectionRun(
        tenantId=context.tenant_id,
        subscriptionId=context.subscription_id,
        collectionRunId=context.collection_run_id,
        processingRunId=context.processing_run_id,
        correlationId=context.correlation_id,
        status=run_status,
        startedAt=report.started_at,
        completedAt=report.completed_at,
        collectors=[result.collector for result in report.results],
        counts={result.collector: result.record_count for result in report.results},
        recordsCollected=sum(result.record_count for result in report.results),
        errors=report.errors,
    )
    storage.processing_metadata.upsert(
        context.tenant_id,
        {
            **collection_run.model_dump(by_alias=True, mode="json"),
            "metadataType": "collectionRun",
            "startTime": report.started_at,
            "endTime": report.completed_at,
        },
    )
    logger.info(
        "collection_summary tenant_id=%s subscription_id=%s run_id=%s "
        "collectors_succeeded=%d collectors_failed=%d records_collected=%d",
        context.tenant_id,
        context.subscription_id,
        context.collection_run_id,
        report.success_count,
        report.failure_count,
        sum(result.record_count for result in report.results),
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run all FinsOpsIQ data collectors"
    )
    parser.add_argument(
        "--no-csv",
        action="store_true",
        help="Skip CSV export for downstream pandas pipeline",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop on first collector failure",
    )
    args = parser.parse_args()

    report = run_all(
        export_csv=not args.no_csv,
        continue_on_error=not args.fail_fast,
    )

    print(f"Collectors succeeded: {report.success_count}")
    for result in report.results:
        print(f"  - {result.collector}: {result.record_count} records -> {result.output_path}")

    if report.errors:
        print(f"Collectors failed: {report.failure_count}")
        for err in report.errors:
            print(f"  - {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
