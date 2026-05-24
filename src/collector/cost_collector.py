"""Azure Cost Management API collector (mock-simulated)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.collector.base import BaseCollector
from src.collector.schemas import CostDataPayload


class CostCollector(BaseCollector[CostDataPayload]):
    """Ingests cost/usage records from mock Cost Management API responses."""

    collector_name = "cost"
    mock_filename = "cost_data.json"
    schema_model = CostDataPayload
    output_prefix = "costs"

    def _count_records(self, validated: CostDataPayload) -> int:
        return len(validated.records)

    def export_csv(self, envelope: dict | None = None) -> Path:
        """Flatten cost records to CSV for downstream pandas processors."""
        data = envelope or self.load_latest_envelope()
        records = data.get("records", [])
        rows = [
            {
                "date": r["date"],
                "resource_group": r["resourceGroup"],
                "service_name": r["serviceName"],
                "location": r["location"],
                "cost_usd": r["costUSD"],
                "usage_quantity": r["usageQuantity"],
                "currency": r.get("currency", "USD"),
            }
            for r in records
        ]
        df = pd.DataFrame(rows)
        csv_path = self.settings.raw_path / "costs_latest.csv"
        df.to_csv(csv_path, index=False)
        self.logger.info("Exported %d cost rows to %s", len(df), csv_path)
        return csv_path

    def load_latest_dataframe(self) -> pd.DataFrame:
        csv_path = self.settings.raw_path / "costs_latest.csv"
        if not csv_path.exists():
            self.collect()
            self.export_csv()
        return pd.read_csv(csv_path, parse_dates=["date"])
