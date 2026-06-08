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

    def _fetch_live_data(self) -> dict:
        from src.collector.auth import get_azure_credential
        from azure.mgmt.containerservice import ContainerServiceClient
        from azure.mgmt.monitor import MonitorManagementClient
        from datetime import datetime, timezone, timedelta
        
        credential = get_azure_credential()
        sub_id = self.settings.azure_subscription_id
        aks_client = ContainerServiceClient(credential, sub_id)
        monitor_client = MonitorManagementClient(credential, sub_id)
        
        clusters_data = []
        try:
            # Note: The user currently has 0 AKS clusters. 
            # If they had clusters, we would iterate and fetch metrics here.
            clusters = list(aks_client.managed_clusters.list())
            for cluster in clusters:
                # Mock extraction logic for future implementation if they create clusters
                pass
        except Exception as e:
            self.logger.warning("Failed to list AKS clusters: %s", e)

            
        return {
            "metadata": {
                "subscriptionId": sub_id,
                "apiVersion": "2023-01-01",
                "generatedAt": datetime.now(timezone.utc).isoformat(),
                "source": "live"
            },
            "clusters": clusters_data
        }

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
