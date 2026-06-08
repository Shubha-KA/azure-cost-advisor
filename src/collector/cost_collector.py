"""Azure Cost Management API collector (mock-simulated)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

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

    def _fetch_live_data(self) -> dict[str, Any]:
        from src.collector.auth import get_azure_credential
        from azure.mgmt.costmanagement import CostManagementClient
        from azure.mgmt.costmanagement.models import QueryDefinition, QueryDataset, QueryAggregation, QueryGrouping, QueryTimePeriod
        from datetime import datetime, timezone, timedelta
        from typing import Any

        credential = get_azure_credential()
        client = CostManagementClient(credential)
        sub_id = self.settings.azure_subscription_id
        scope = f"/subscriptions/{sub_id}"

        now = datetime.now(timezone.utc)
        start = now - timedelta(days=self.settings.cost_lookback_days)
        
        query = QueryDefinition(
            type="Usage",
            timeframe="Custom",
            time_period=QueryTimePeriod(
                from_property=start,
                to=now
            ),
            dataset=QueryDataset(
                granularity="Daily",
                aggregation={
                    "totalCost": QueryAggregation(name="PreTaxCost", function="Sum"),
                    "totalUsage": QueryAggregation(name="UsageQuantity", function="Sum"),
                },
                grouping=[
                    QueryGrouping(type="Dimension", name="ResourceGroup"),
                    QueryGrouping(type="Dimension", name="ServiceName"),
                    QueryGrouping(type="Dimension", name="ResourceLocation"),
                ]
            )
        )
        
        res = client.query.usage(scope=scope, parameters=query)
        records = []
        if res.rows:
            for row in res.rows:
                date_str = str(row[2])
                # Format YYYYMMDD to YYYY-MM-DD
                if len(date_str) == 8 and date_str.isdigit():
                    date_str = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
                elif "T" in date_str:
                    date_str = date_str.split("T")[0]
                    
                records.append({
                    "costUSD": float(row[0] or 0),
                    "usageQuantity": float(row[1] or 0),
                    "date": date_str,
                    "resourceGroup": row[3] if row[3] else "Unknown",
                    "serviceName": row[4] if row[4] else "Unknown",
                    "location": row[5] if row[5] else "Unknown"
                })

        # Ensure we always return at least 1 record as required by schema min_length=1
        if not records:
            records.append({
                "costUSD": 0.0,
                "usageQuantity": 0.0,
                "date": now.strftime("%Y-%m-%d"),
                "resourceGroup": "NoData",
                "serviceName": "NoData",
                "location": "NoData"
            })

        return {
            "metadata": {
                "subscriptionId": sub_id,
                "apiVersion": "2023-11-01",
                "generatedAt": now.isoformat(),
                "source": "live"
            },
            "records": records
        }

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
