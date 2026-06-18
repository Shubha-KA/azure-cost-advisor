"""Azure Monitor VM metrics collector (mock-simulated)."""

from __future__ import annotations

from pathlib import Path
import re
from uuid import uuid4

import pandas as pd

from src.collector.base import BaseCollector
from src.collector.schemas import VmMetricsPayload


class MetricsCollector(BaseCollector[VmMetricsPayload]):
    """Ingests virtual machine performance metrics from mock Monitor API data."""

    collector_name = "metrics"
    mock_filename = "vm_metrics.json"
    schema_model = VmMetricsPayload
    output_prefix = "vm_metrics"
    allow_mock_fallback = False

    def _fetch_live_data(self) -> dict:
        from src.collector.auth import get_azure_credential
        from azure.mgmt.compute import ComputeManagementClient
        from azure.mgmt.monitor import MonitorManagementClient
        from datetime import datetime, timezone, timedelta
        
        credential = self.credential or get_azure_credential()
        sub_id = self.context.subscription_id
        compute_client = ComputeManagementClient(credential, sub_id)
        monitor_client = MonitorManagementClient(credential, sub_id)
        
        resources_data = []
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=7)
        run_id = f"vm-metrics-{uuid4()}"
        try:
            vms = list(compute_client.virtual_machines.list_all())
            for vm in vms:
                definitions = {
                    definition.name.value
                    for definition in monitor_client.metric_definitions.list(vm.id)
                }
                requested = [
                    name
                    for name in (
                        "Percentage CPU",
                        "Available Memory Percentage",
                        "Available Memory Bytes",
                        "Network In Total",
                        "Network Out Total",
                        "Disk Read Bytes",
                        "Disk Write Bytes",
                        "Disk Read Operations/Sec",
                        "Disk Write Operations/Sec",
                        "VmAvailabilityMetric",
                        "CPU Credits Remaining",
                        "CPU Credits Consumed",
                    )
                    if name in definitions
                ]
                metrics = self._query_metrics(
                    monitor_client,
                    vm.id,
                    requested,
                    start,
                    now,
                )
                resources_data.append(
                    {
                        "resourceId": vm.id,
                        "resourceGroup": self._resource_group_from_id(vm.id),
                        "resourceName": vm.name,
                        "location": vm.location,
                        "vmSize": getattr(vm.hardware_profile, "vm_size", "Unknown"),
                        "timeRange": {
                            "start": start.isoformat(),
                            "end": now.isoformat(),
                        },
                        "metrics": metrics,
                        "sourceSystem": "Azure Monitor",
                        "sourceTimestamp": now.isoformat(),
                        "collectionRunId": run_id,
                    }
                )
        except Exception as e:
            raise RuntimeError(f"Failed to collect VM metrics: {e}") from e
            
            
        return {
            "metadata": {
                "subscriptionId": sub_id,
                "apiVersion": "2023-01-01",
                "generatedAt": now.isoformat(),
                "source": "live"
            },
            "resources": resources_data
        }

    @staticmethod
    def _query_metrics(client, resource_id, names, start, end) -> dict:
        if not names:
            return {}
        result = {}
        timespan = (
            f"{start.strftime('%Y-%m-%dT%H:%M:%SZ')}/"
            f"{end.strftime('%Y-%m-%dT%H:%M:%SZ')}"
        )
        for name in names:
            try:
                response = client.metrics.list(
                    resource_id,
                    timespan=timespan,
                    interval="PT1H",
                    metricnames=name,
                    aggregation="Average",
                    auto_adjust_timegrain=True,
                )
            except Exception:
                continue
            for metric in response.value or []:
                points = [
                    point
                    for series in metric.timeseries or []
                    for point in series.data or []
                ]
                averages = [
                    point.average for point in points if point.average is not None
                ]
                if not averages:
                    continue
                result[metric.name.value] = {
                    "average": sum(averages) / len(averages),
                    "maximum": max(averages),
                    "minimum": min(averages),
                    "unit": str(metric.unit),
                }
        return result

    @staticmethod
    def _resource_group_from_id(resource_id: str) -> str:
        match = re.search(
            r"/resourcegroups/([^/]+)", resource_id or "", re.IGNORECASE
        )
        return match.group(1) if match else "Unknown"

    def _count_records(self, validated: VmMetricsPayload) -> int:
        return len(validated.resources)

    def export_usage_csv(self, envelope: dict | None = None) -> Path:
        """Map VM metrics to usage schema expected by waste detector."""
        data = envelope or self.load_latest_envelope()
        rows = []
        for resource in data.get("resources", []):
            metrics = resource.get("metrics", {})
            cpu = metrics.get("Percentage CPU", {}).get("average", 0.0)
            mem_metric = metrics.get("Available Memory Bytes", {})
            mem_avg = mem_metric.get("average", 0.0)
            mem_pct = max(0.0, min(100.0, 100.0 - (mem_avg / 1e9))) if mem_avg else 0.0
            net_in = metrics.get("Network In Total", {}).get("average", 0.0)
            net_mbps = round(net_in / 1_000_000, 2) if net_in else 0.0

            rows.append(
                {
                    "resource_group": resource["resourceGroup"],
                    "resource_name": resource["resourceName"],
                    "service_name": "Virtual Machines",
                    "avg_cpu_percent": round(cpu, 2),
                    "avg_memory_percent": round(mem_pct, 2),
                    "avg_network_mbps": net_mbps,
                    "hours_observed": 168,
                    "sku": resource.get("vmSize", "Unknown"),
                }
            )

        df = pd.DataFrame(rows)
        csv_path = self.settings.raw_path / "usage_latest.csv"
        df.to_csv(csv_path, index=False)
        self.logger.info("Exported %d VM metric rows to %s", len(df), csv_path)
        return csv_path

    def load_latest_dataframe(self) -> pd.DataFrame:
        csv_path = self.settings.raw_path / "usage_latest.csv"
        if not csv_path.exists():
            self.collect()
            self.export_usage_csv()
        return pd.read_csv(csv_path)
