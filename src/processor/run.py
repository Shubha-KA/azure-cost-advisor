"""Orchestrate the full processing pipeline."""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd

from src.config import get_settings
from src.domain.context import OperationContext
from src.domain.models import CostFact, ProcessingRun, Recommendation, ResourceFact
from src.processor.anomaly_detector import AnomalyDetector
from src.processor.normalizer import DataNormalizer, ProcessorError
from src.processor.report_generator import ReportGenerator
from src.processor.savings_estimator import SavingsEstimator
from src.processor.waste_detector import WasteDetector
from src.storage.factory import create_storage_provider

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class ProcessingReport:
    started_at: str
    tenant_id: str = ""
    subscription_id: str = ""
    collection_run_id: str = ""
    processing_run_id: str = ""
    completed_at: str = ""
    resource_count: int = 0
    resource_fact_count: int = 0
    waste_count: int = 0
    anomaly_count: int = 0
    total_estimated_savings: dict[str, float] = field(default_factory=dict)
    raw_cost_record_count: int = 0
    cost_fact_count: int = 0
    raw_totals: dict[str, float] = field(default_factory=dict)
    processed_totals: dict[str, float] = field(default_factory=dict)
    summary_totals: dict[str, float] = field(default_factory=dict)
    reconciliation_status: str = "not_run"
    output_files: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def run_processing(
    *,
    settings=None,
    context: OperationContext | None = None,
    storage=None,
) -> tuple[pd.DataFrame, ProcessingReport]:
    """Execute normalize → waste → savings → anomalies → report."""
    settings = settings or get_settings()
    settings.ensure_data_dirs()
    storage = storage or create_storage_provider(settings)
    if context is None:
        collection_context = _load_collection_context(settings)
        context = OperationContext.create(
            collection_context["tenantId"],
            collection_context["subscriptionId"],
        ).model_copy(
            update={
                "collection_run_id": collection_context["collectionRunId"],
                "correlation_id": collection_context["correlationId"],
            }
        )

    report = ProcessingReport(
        started_at=datetime.now(timezone.utc).isoformat(),
        tenant_id=context.tenant_id,
        subscription_id=context.subscription_id,
        collection_run_id=context.collection_run_id,
        processing_run_id=context.processing_run_id,
    )
    storage.processing_metadata.upsert(
        context.tenant_id,
        {
            **ProcessingRun(
                **context.document_fields(),
                status="running",
                startedAt=report.started_at,
            ).model_dump(by_alias=True, mode="json"),
            "metadataType": "processingRun",
            "startTime": report.started_at,
            "endTime": None,
        },
    )

    try:
        logger.info("Step 1/5: Normalizing resource data and cost facts")
        normalizer = DataNormalizer(settings, context, storage)
        payloads = normalizer.loader.load_all_available()
        df = normalizer.normalize(payloads)
        cost_payload = payloads.get("costs", {})
        cost_facts = normalizer.normalize_cost_facts(cost_payload)
        reconciliation = _reconcile_costs(cost_payload, cost_facts)

        logger.info("Step 2/5: Applying waste detection rules")
        df = WasteDetector(settings).detect(df)

        logger.info("Step 3/5: Estimating savings")
        df = SavingsEstimator(settings).estimate(df)
        savings_summary = SavingsEstimator.summary(df)

        logger.info("Step 4/5: Detecting cost anomalies")
        df, anomalies_payload = AnomalyDetector(
            settings, context, storage
        ).detect(df)

        logger.info("Step 5/5: Generating reports")
        generator = ReportGenerator(settings)
        outputs = generator.generate(
            df,
            cost_facts,
            anomalies_payload,
            savings_summary,
            reconciliation,
        )
        summary = generator.load_latest_summary()
        summary_totals = {
            str(currency): round(float(amount), 2)
            for currency, amount in summary.get("total_cost", {}).items()
        }
        if summary_totals != reconciliation["processed_totals"]:
            raise ProcessorError(
                "Cost reconciliation failed: summary totals "
                f"{summary_totals} != processed totals "
                f"{reconciliation['processed_totals']}"
            )

        report.resource_count = len(df)
        report.waste_count = int((df["waste_level"] != "NONE").sum())
        report.anomaly_count = anomalies_payload.get("anomaly_count", 0)
        report.total_estimated_savings = savings_summary["total_estimated_savings"]
        report.raw_cost_record_count = reconciliation["raw_cost_record_count"]
        report.cost_fact_count = reconciliation["cost_fact_count"]
        report.raw_totals = reconciliation["raw_totals"]
        report.processed_totals = reconciliation["processed_totals"]
        report.summary_totals = summary_totals
        report.reconciliation_status = "passed"
        report.output_files = [str(p) for p in outputs.values()]
        storage.cost_facts.upsert_many(
            context.tenant_id,
            [
                CostFact.model_validate(_cost_fact_document(row, context))
                for row in cost_facts.to_dict(orient="records")
            ],
        )
        resource_models = [
            ResourceFact.model_validate(_resource_fact_document(row, context))
            for row in df.to_dict(orient="records")
            if str(row.get("resource_id", "")).strip()
        ]
        storage.resources.upsert_many(context.tenant_id, resource_models)
        report.resource_fact_count = len(resource_models)
        recommendations = [
            Recommendation(
                **context.document_fields(),
                resourceId=str(row.get("resource_id", "")),
                category=str(row.get("rule_id", "waste")),
                title=f"{row.get('resource_name', 'Resource')} optimization",
                content=str(row.get("recommendation", "")),
                estimatedSavings=float(row.get("estimated_savings", 0)),
                currency=str(row.get("savings_currency", "")),
                sourceSystem="Rule-based processing",
                sourceTimestamp=datetime.now(timezone.utc),
                evidence={
                    "wasteLevel": row.get("waste_level", "NONE"),
                    "costBasis": row.get("cost_basis", "unknown"),
                    "monthlyCost": row.get("monthly_cost", 0),
                },
            )
            for row in df.to_dict(orient="records")
            if row.get("waste_level") != "NONE" and row.get("recommendation")
        ]
        storage.recommendations.upsert_many(
            context.tenant_id, recommendations
        )
        processing_run = ProcessingRun(
            **context.document_fields(),
            status="completed",
            completedAt=datetime.now(timezone.utc),
            counts={
                "resources": len(df),
                "costFacts": len(cost_facts),
                "waste": report.waste_count,
                "anomalies": report.anomaly_count,
            },
            recordCounts={
                "rawCostRecords": report.raw_cost_record_count,
                "costFacts": report.cost_fact_count,
                "resourceFacts": report.resource_fact_count,
                "recommendations": len(recommendations),
            },
            reconciliation=reconciliation,
            reconciliationStatus=report.reconciliation_status,
        )
        storage.processing_metadata.upsert(
            context.tenant_id,
            {
                **processing_run.model_dump(by_alias=True, mode="json"),
                "metadataType": "processingRun",
                "summary": summary,
                "startTime": report.started_at,
                "endTime": datetime.now(timezone.utc).isoformat(),
            },
        )

    except ProcessorError as exc:
        logger.error("Processing failed: %s", exc)
        report.errors.append(str(exc))
        _persist_failed_run(storage, context, report)
        raise
    except Exception as exc:
        logger.exception("Unexpected processing error")
        report.errors.append(str(exc))
        _persist_failed_run(storage, context, report)
        raise

    report.completed_at = datetime.now(timezone.utc).isoformat()
    logger.info(
        "processing_summary tenant_id=%s subscription_id=%s collection_run_id=%s "
        "processing_run_id=%s cost_facts=%d resource_facts=%d "
        "reconciliation_status=%s",
        context.tenant_id,
        context.subscription_id,
        context.collection_run_id,
        context.processing_run_id,
        report.cost_fact_count,
        report.resource_fact_count,
        report.reconciliation_status,
    )
    return df, report


def _persist_failed_run(storage, context, report: ProcessingReport) -> None:
    storage.processing_metadata.upsert(
        context.tenant_id,
        {
            **ProcessingRun(
                **context.document_fields(),
                status="failed",
                startedAt=report.started_at,
                completedAt=datetime.now(timezone.utc),
                recordCounts={
                    "costFacts": report.cost_fact_count,
                    "resourceFacts": report.resource_fact_count,
                },
                reconciliationStatus=report.reconciliation_status,
                errors=report.errors,
            ).model_dump(by_alias=True, mode="json"),
            "metadataType": "processingRun",
            "startTime": report.started_at,
            "endTime": datetime.now(timezone.utc).isoformat(),
        },
    )


def _load_collection_context(settings) -> dict[str, str]:
    import json

    path = settings.raw_path / "costs_latest.json"
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        context = payload.get("context", {})
        if all(
            context.get(key)
            for key in (
                "tenantId",
                "subscriptionId",
                "collectionRunId",
                "correlationId",
            )
        ):
            return context
    fallback = OperationContext.create(
        settings.effective_tenant_id,
        settings.effective_subscription_id,
    )
    return fallback.document_fields()


def _cost_fact_document(row: dict, context: OperationContext) -> dict:
    return {
        **context.document_fields(),
        "date": row["date"],
        "resourceId": row.get("resource_id", ""),
        "resourceGroup": row.get("resource_group", ""),
        "serviceName": row.get("service_name", ""),
        "location": row.get("location", ""),
        "costAmount": row.get("cost_amount", 0),
        "usageQuantity": row.get("usage_quantity", 0),
        "currency": row.get("currency", "UNKNOWN"),
        "sourceSystem": row.get("source_system", "unknown"),
        "sourceTimestamp": row.get("source_timestamp", ""),
    }


def _resource_fact_document(row: dict, context: OperationContext) -> dict:
    canonical = {
        **context.document_fields(),
        "resourceId": row.get("resource_id", ""),
        "resourceName": row.get("resource_name", ""),
        "resourceType": row.get("resource_type", ""),
        "resourceGroup": row.get("resource_group", ""),
        "location": row.get("location", ""),
        "actualCostCollectedPeriod": row.get("actual_cost_collected_period", 0),
        "actualCostCurrency": row.get("actual_cost_currency", ""),
        "estimatedMonthlyCost": row.get("estimated_monthly_cost", 0),
        "estimatedCostCurrency": row.get("estimated_cost_currency", ""),
        "costBasis": row.get("cost_basis", "unknown"),
        "wasteLevel": row.get("waste_level", "NONE"),
        "recommendation": row.get("recommendation", ""),
        "estimatedSavings": row.get("estimated_savings", 0),
        "savingsCurrency": row.get("savings_currency", ""),
        "sourceSystem": row.get("source_system", "unknown"),
        "sourceTimestamp": row.get("source_timestamp", ""),
    }
    known = {
        "tenant_id", "subscription_id", "collection_run_id",
        "processing_run_id", "correlation_id", "schema_version",
        "resource_id", "resource_name", "resource_type", "resource_group",
        "location", "actual_cost_collected_period", "actual_cost_currency",
        "estimated_monthly_cost", "estimated_cost_currency", "cost_basis",
        "waste_level", "recommendation", "estimated_savings",
        "savings_currency", "source_system", "source_timestamp",
    }
    utilization_keys = {"cpu_avg_percent", "memory_avg_percent", "node_utilization"}
    utilizable = _supports_utilization(row.get("resource_type", ""))
    canonical["attributes"] = {
        key: value
        for key, value in row.items()
        if key not in known and (utilizable or key not in utilization_keys)
    }
    return canonical


def _supports_utilization(resource_type: str) -> bool:
    value = str(resource_type or "").lower()
    return any(
        term in value
        for term in (
            "virtual machine",
            "microsoft.compute/virtualmachines",
            "microsoft.compute/virtualmachinescalesets",
            "aks cluster",
            "microsoft.containerservice/managedclusters",
        )
    )


def _reconcile_costs(
    cost_payload: dict, cost_facts: pd.DataFrame
) -> dict[str, object]:
    records = cost_payload.get("records", [])
    source = str(cost_payload.get("metadata", {}).get("source", "unknown"))
    raw_count = len(records)
    fact_count = len(cost_facts)
    raw_totals: dict[str, float] = {}
    for record in records:
        currency = str(record.get("currency", "UNKNOWN")).upper()
        amount = float(record.get("costAmount", record.get("costUSD", 0)) or 0)
        raw_totals[currency] = raw_totals.get(currency, 0.0) + amount
    raw_totals = {key: round(value, 2) for key, value in raw_totals.items()}
    processed_totals = (
        cost_facts.groupby("currency")["cost_amount"].sum().round(2).to_dict()
        if not cost_facts.empty
        else {}
    )

    if source == "live" and raw_count > 0 and cost_facts.empty:
        raise ProcessorError(
            "Live Cost Management records exist but processed cost facts are empty"
        )
    if raw_count != fact_count:
        raise ProcessorError(
            "Cost reconciliation failed: "
            f"{raw_count} raw records != {fact_count} processed cost facts"
        )
    if raw_totals != processed_totals:
        raise ProcessorError(
            "Cost reconciliation failed: "
            f"raw totals {raw_totals} != processed totals {processed_totals}"
        )

    return {
        "status": "passed",
        "source": source,
        "raw_cost_record_count": raw_count,
        "cost_fact_count": fact_count,
        "raw_totals": raw_totals,
        "processed_totals": processed_totals,
        "summary_totals": processed_totals,
        "currencies": sorted(processed_totals),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="FinsOpsIQ processor")
    args = parser.parse_args()
    _, report = run_processing()
    print(f"Resources processed: {report.resource_count}")
    print(f"Waste flagged: {report.waste_count}")
    print(f"Anomalies: {report.anomaly_count}")
    print(f"Est. savings: {report.total_estimated_savings}")
    print(
        "Cost reconciliation: "
        f"{report.raw_cost_record_count} raw == {report.cost_fact_count} facts, "
        f"{report.raw_totals} == "
        f"{report.summary_totals} "
        f"({report.reconciliation_status})"
    )
    for path in report.output_files:
        print(f"  -> {path}")


if __name__ == "__main__":
    main()
