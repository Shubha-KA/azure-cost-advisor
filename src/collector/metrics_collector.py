"""Azure Monitor VM metrics collector (mock-simulated)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.collector.base import BaseCollector
from src.collector.schemas import VmMetricsPayload


class MetricsCollector(BaseCollector[VmMetricsPayload]):
    """Ingests virtual machine performance metrics from mock Monitor API data."""

    collector_name = "metrics"
    mock_filename = "vm_metrics.json"
    schema_model = VmMetricsPayload
    output_prefix = "vm_metrics"

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
