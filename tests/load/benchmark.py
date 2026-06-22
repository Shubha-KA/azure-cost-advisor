"""Deterministic repository throughput benchmark: 100 tenants / 1,000 subscriptions."""

from __future__ import annotations

import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import Settings
from src.domain.context import OperationContext
from src.domain.models import AzureSubscription, CostFact, Tenant
from src.storage.factory import create_storage_provider


def run() -> dict:
    with tempfile.TemporaryDirectory() as directory:
        settings = Settings(
            _env_file=None,
            STORAGE_PROVIDER="file",
            STORAGE_DATA_DIR=directory,
            DATA_RAW_DIR=str(Path(directory) / "raw"),
            DATA_PROCESSED_DIR=str(Path(directory) / "processed"),
            DATA_EMBEDDINGS_DIR=str(Path(directory) / "embeddings"),
        )
        storage = create_storage_provider(settings)
        started = time.perf_counter()
        latencies = []
        records = 0
        for tenant_number in range(100):
            tenant_id = f"tenant-{tenant_number}"
            storage.tenants.upsert(
                tenant_id,
                Tenant(
                    tenantId=tenant_id,
                    correlationId=f"tenant-correlation-{tenant_number}",
                ),
            )
            for subscription_number in range(10):
                subscription_id = (
                    f"subscription-{tenant_number}-{subscription_number}"
                )
                storage.subscriptions.upsert(
                    tenant_id,
                    AzureSubscription(
                        tenantId=tenant_id,
                        subscriptionId=subscription_id,
                        selected=True,
                        correlationId=f"subscription-correlation-{records}",
                    ),
                )
                context = OperationContext.create(tenant_id, subscription_id)
                facts = [
                    CostFact(
                        **context.document_fields(),
                        date=f"2026-06-{(index % 28) + 1:02d}",
                        serviceName=f"service-{index % 20}",
                        resourceGroup=f"rg-{index % 10}",
                        costAmount=float(index + 1),
                        currency="INR",
                        sourceSystem="load-test",
                        sourceTimestamp="2026-06-12T00:00:00Z",
                    )
                    for index in range(100)
                ]
                write_started = time.perf_counter()
                storage.cost_facts.upsert_many(tenant_id, facts)
                latencies.append((time.perf_counter() - write_started) * 1000)
                records += len(facts)
        elapsed = time.perf_counter() - started
        return {
            "tenants": 100,
            "subscriptions": 1000,
            "costRecords": records,
            "elapsedSeconds": round(elapsed, 3),
            "recordsPerSecond": round(records / elapsed, 2),
            "p95SubscriptionWriteMs": round(
                statistics.quantiles(latencies, n=20)[18], 2
            ),
        }


if __name__ == "__main__":
    print(run())
