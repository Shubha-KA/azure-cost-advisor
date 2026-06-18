"""Azure Kubernetes Service metrics collector (mock-simulated)."""

from __future__ import annotations

from uuid import uuid4

from src.collector.metrics_collector import MetricsCollector
from src.collector.base import BaseCollector
from src.collector.schemas import AksMetricsPayload


class AksCollector(BaseCollector[AksMetricsPayload]):
    """Ingests AKS cluster utilization and cost metrics from mock Monitor data."""

    collector_name = "aks"
    mock_filename = "aks_metrics.json"
    schema_model = AksMetricsPayload
    output_prefix = "aks_metrics"
    allow_mock_fallback = False

    def _fetch_live_data(self) -> dict:
        from src.collector.auth import get_azure_credential
        from azure.mgmt.containerservice import ContainerServiceClient
        from azure.mgmt.monitor import MonitorManagementClient
        from datetime import datetime, timezone, timedelta
        
        credential = self.credential or get_azure_credential()
        sub_id = self.context.subscription_id
        aks_client = ContainerServiceClient(credential, sub_id)
        monitor_client = MonitorManagementClient(credential, sub_id)
        
        clusters_data = []
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=7)
        run_id = f"aks-metrics-{uuid4()}"
        try:
            clusters = list(aks_client.managed_clusters.list())
            for cluster in clusters:
                definitions = {
                    definition.name.value
                    for definition in monitor_client.metric_definitions.list(cluster.id)
                }
                requested = [
                    name
                    for name in (
                        "node_cpu_usage_percentage",
                        "node_memory_working_set_percentage",
                        "node_disk_usage_percentage",
                        "node_network_in_bytes",
                        "node_network_out_bytes",
                        "kube_node_status_condition",
                        "kube_pod_status_phase",
                        "cluster_autoscaler_unneeded_nodes_count",
                        "cluster_autoscaler_unschedulable_pods_count",
                    )
                    if name in definitions
                ]
                raw_metrics = MetricsCollector._query_metrics(
                    monitor_client,
                    cluster.id,
                    requested,
                    start,
                    now,
                )
                cpu = raw_metrics.get(
                    "node_cpu_usage_percentage", {}
                ).get("average", 0.0)
                memory = raw_metrics.get(
                    "node_memory_working_set_percentage", {}
                ).get("average", 0.0)
                node_pools = []
                for pool in cluster.agent_pool_profiles or []:
                    node_pools.append(
                        {
                            "name": pool.name,
                            "vmSize": pool.vm_size or "Unknown",
                            "nodeCount": pool.count or 0,
                            "avgCpuPercent": cpu,
                            "avgMemoryPercent": memory,
                        }
                    )
                clusters_data.append(
                    {
                        "resourceId": cluster.id,
                        "clusterName": cluster.name,
                        "resourceGroup": MetricsCollector._resource_group_from_id(
                            cluster.id
                        ),
                        "location": cluster.location,
                        "kubernetesVersion": cluster.kubernetes_version or "Unknown",
                        "nodePools": node_pools,
                        "metrics": {
                            "cpuUtilizationPercent": cpu,
                            "memoryUtilizationPercent": memory,
                            **{
                                name: values["average"]
                                for name, values in raw_metrics.items()
                            },
                        },
                        "monthlyCostEstimateUsd": 0.0,
                        "sourceSystem": "Azure Monitor",
                        "sourceTimestamp": now.isoformat(),
                        "collectionRunId": run_id,
                    }
                )
        except Exception as e:
            raise RuntimeError(f"Failed to collect AKS metrics: {e}") from e

            
        return {
            "metadata": {
                "subscriptionId": sub_id,
                "apiVersion": "2023-01-01",
                "generatedAt": now.isoformat(),
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
