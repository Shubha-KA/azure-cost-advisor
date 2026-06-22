"""Concurrent cost and chat API benchmark with deterministic local dependencies."""

from __future__ import annotations

import concurrent.futures
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from src.api.app import create_app
from src.config import Settings
from src.domain.context import OperationContext
from src.domain.models import AzureSubscription, CostFact, Tenant
from src.storage.factory import create_storage_provider


class Advisor:
    def __init__(self, settings, tenant_id, subscription_ids):
        self.tenant_id = tenant_id

    def ask(self, question, history=""):
        return f"Scoped answer for {self.tenant_id}"


def run() -> dict:
    with tempfile.TemporaryDirectory() as directory:
        settings = Settings(
            _env_file=None,
            STORAGE_PROVIDER="file",
            STORAGE_DATA_DIR=directory,
            DEFAULT_TENANT_ID="tenant-load",
            DEFAULT_SUBSCRIPTION_ID="subscription-load",
            DATA_RAW_DIR=str(Path(directory) / "raw"),
            DATA_PROCESSED_DIR=str(Path(directory) / "processed"),
            DATA_EMBEDDINGS_DIR=str(Path(directory) / "embeddings"),
        )
        storage = create_storage_provider(settings)
        storage.tenants.upsert(
            "tenant-load",
            Tenant(tenantId="tenant-load", correlationId="correlation-load"),
        )
        storage.subscriptions.upsert(
            "tenant-load",
            AzureSubscription(
                tenantId="tenant-load",
                subscriptionId="subscription-load",
                selected=True,
                correlationId="correlation-load",
            ),
        )
        context = OperationContext.create("tenant-load", "subscription-load")
        storage.cost_facts.upsert_many(
            "tenant-load",
            [
                CostFact(
                    **context.document_fields(),
                    date=f"2026-06-{index % 28 + 1:02d}",
                    serviceName="Compute",
                    costAmount=1,
                    currency="INR",
                    sourceSystem="load-test",
                    sourceTimestamp="2026-06-12T00:00:00Z",
                )
                for index in range(1000)
            ],
        )
        client = TestClient(
            create_app(settings, storage=storage, advisor_factory=Advisor)
        )
        headers = {
            "X-Tenant-ID": "tenant-load",
            "X-Subscription-ID": "subscription-load",
        }

        def call(index: int):
            started = time.perf_counter()
            response = (
                client.get("/api/costs/summary", headers=headers)
                if index % 2 == 0
                else client.post(
                    "/api/chat",
                    headers=headers,
                    json={"message": "Summarize costs"},
                )
            )
            return response.status_code, (time.perf_counter() - started) * 1000

        started = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=25) as executor:
            results = list(executor.map(call, range(500)))
        elapsed = time.perf_counter() - started
        latencies = [latency for _, latency in results]
        return {
            "requests": len(results),
            "concurrency": 25,
            "successes": sum(status == 200 for status, _ in results),
            "requestsPerSecond": round(len(results) / elapsed, 2),
            "p50LatencyMs": round(statistics.median(latencies), 2),
            "p95LatencyMs": round(statistics.quantiles(latencies, n=20)[18], 2),
            "p99LatencyMs": round(statistics.quantiles(latencies, n=100)[98], 2),
        }


if __name__ == "__main__":
    print(run())
