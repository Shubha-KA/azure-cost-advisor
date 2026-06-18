"""Idempotently migrate legacy latest files into configured repositories."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from uuid import uuid4

import pandas as pd

from src.config import Settings, get_settings
from src.domain.context import OperationContext
from src.domain.models import (
    AzureSubscription,
    CostFact,
    Recommendation,
    ResourceFact,
    Tenant,
)
from src.storage.factory import create_storage_provider


def migrate_legacy_files(
    settings: Settings | None = None, dry_run: bool = True
) -> dict[str, object]:
    settings = settings or get_settings()
    storage = create_storage_provider(settings)
    context = _legacy_context(settings)
    resources = _read_csv(settings.processed_path / "resources_latest.csv")
    costs = _read_csv(settings.processed_path / "cost_facts_latest.csv")
    recommendation_payload = _read_json(
        settings.processed_path / "recommendations_latest.json"
    )

    cost_models = [
        CostFact(
            **context.document_fields(),
            date=row["date"],
            resourceId=str(row.get("resource_id", "")),
            resourceGroup=str(row.get("resource_group", "")),
            serviceName=str(row.get("service_name", "")),
            location=str(row.get("location", "")),
            costAmount=float(row.get("cost_amount", row.get("cost_usd", 0))),
            usageQuantity=float(row.get("usage_quantity", 0)),
            currency=str(row.get("currency", "UNKNOWN")),
            sourceSystem=str(row.get("source_system", "legacy migration")),
            sourceTimestamp=str(row.get("source_timestamp", "")),
        )
        for row in costs.to_dict(orient="records")
    ]
    resource_models = [
        ResourceFact(
            **context.document_fields(),
            resourceId=str(row.get("resource_id", "")),
            resourceName=str(row.get("resource_name", "")),
            resourceType=str(row.get("resource_type", "")),
            resourceGroup=str(row.get("resource_group", "")),
            location=str(row.get("location", "")),
            actualCostCollectedPeriod=float(
                row.get("actual_cost_collected_period", 0)
            ),
            actualCostCurrency=str(row.get("actual_cost_currency", "")),
            estimatedMonthlyCost=float(row.get("estimated_monthly_cost", 0)),
            estimatedCostCurrency=str(row.get("estimated_cost_currency", "")),
            costBasis=str(row.get("cost_basis", "unknown")),
            wasteLevel=str(row.get("waste_level", "NONE")),
            recommendation=str(row.get("recommendation", "")),
            estimatedSavings=float(row.get("estimated_savings", 0)),
            savingsCurrency=str(row.get("savings_currency", "")),
            sourceSystem=str(row.get("source_system", "legacy migration")),
            sourceTimestamp=str(row.get("source_timestamp", "")),
            attributes={"migrationSource": "legacy-files"},
        )
        for row in resources.to_dict(orient="records")
        if str(row.get("resource_id", "")).strip()
    ]
    recommendations = []
    if recommendation_payload.get("recommendations"):
        recommendations.append(
            Recommendation(
                **context.document_fields(),
                title="Migrated FinOps recommendations",
                content=str(recommendation_payload["recommendations"]),
                sourceSystem=str(
                    recommendation_payload.get("source_system", "legacy migration")
                ),
                sourceTimestamp=str(
                    recommendation_payload.get("source_timestamp", "")
                ),
                evidence={"migrationSource": "recommendations_latest.json"},
            )
        )

    result = {
        "dryRun": dry_run,
        "tenantId": context.tenant_id,
        "subscriptionId": context.subscription_id,
        "costFacts": len(cost_models),
        "resources": len(resource_models),
        "recommendations": len(recommendations),
        "totalsByCurrency": (
            costs.groupby("currency")["cost_amount"].sum().round(2).to_dict()
            if not costs.empty
            else {}
        ),
    }
    if dry_run:
        return result

    storage.tenants.upsert(
        context.tenant_id,
        Tenant(
            tenantId=context.tenant_id,
            displayName="Migrated tenant",
            correlationId=context.correlation_id,
        ),
    )
    storage.subscriptions.upsert(
        context.tenant_id,
        AzureSubscription(
            tenantId=context.tenant_id,
            subscriptionId=context.subscription_id,
            displayName="Migrated subscription",
            correlationId=context.correlation_id,
        ),
    )
    storage.cost_facts.upsert_many(context.tenant_id, cost_models)
    storage.resources.upsert_many(context.tenant_id, resource_models)
    storage.recommendations.upsert_many(context.tenant_id, recommendations)
    storage.processing_metadata.upsert(
        context.tenant_id,
        {
            **context.document_fields(),
            "metadataType": "legacyMigration",
            "status": "completed",
            "metadataId": f"legacy-migration-{context.processing_run_id}",
            "counts": result,
        },
    )
    return result


def _legacy_context(settings: Settings) -> OperationContext:
    resources = _read_csv(settings.processed_path / "resources_latest.csv")
    if not resources.empty:
        row = resources.iloc[0]
        required = (
            "tenant_id",
            "subscription_id",
            "collection_run_id",
            "processing_run_id",
            "correlation_id",
        )
        if all(key in resources.columns and pd.notna(row[key]) for key in required):
            return OperationContext(
                tenantId=str(row["tenant_id"]),
                subscriptionId=str(row["subscription_id"]),
                collectionRunId=str(row["collection_run_id"]),
                processingRunId=str(row["processing_run_id"]),
                correlationId=str(row["correlation_id"]),
            )
    return OperationContext(
        tenantId=settings.effective_tenant_id,
        subscriptionId=settings.effective_subscription_id,
        collectionRunId=f"legacy-{uuid4()}",
        processingRunId=f"legacy-{uuid4()}",
        correlationId=str(uuid4()),
    )


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            migrate_legacy_files(dry_run=not args.execute),
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
