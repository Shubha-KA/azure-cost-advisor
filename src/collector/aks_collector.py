"""Azure Kubernetes Service metrics collector (mock-simulated)."""

from __future__ import annotations

from src.collector.base import BaseCollector
from src.collector.schemas import AksMetricsPayload


class AksCollector(BaseCollector[AksMetricsPayload]):
    """Ingests AKS cluster utilization and cost metrics from mock Monitor data."""

    collector_name = "aks"
    mock_filename = "aks_metrics.json"
    schema_model = AksMetricsPayload
    output_prefix = "aks_metrics"

    def _count_records(self, validated: AksMetricsPayload) -> int:
        return len(validated.clusters)

    def _apply_ingestion_transforms(self, body: dict) -> None:
        clusters = body.get("clusters", [])
        body["summary"] = {
            "clusterCount": len(clusters),
            "totalNodeCount": sum(
                sum(np.get("nodeCount", 0) for np in c.get("nodePools", []))
                for c in clusters
            ),
            "totalMonthlyCostEstimateUsd": round(
                sum(c.get("monthlyCostEstimateUsd", 0) for c in clusters), 2
            ),
            "underutilizedClusters": sum(
                1
                for c in clusters
                if c.get("metrics", {}).get("cpuUtilizationPercent", 100) < 40
            ),
        }
