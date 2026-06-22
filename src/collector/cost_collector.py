"""Azure Cost Management API collector (mock-simulated)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd

from src.collector.base import BaseCollector
from src.collector.schemas import CostDataPayload


class CostCollector(BaseCollector[CostDataPayload]):
    """Ingests cost/usage records from mock Cost Management API responses."""

    collector_name = "cost"
    mock_filename = "cost_data.json"
    schema_model = CostDataPayload
    output_prefix = "costs"
    allow_mock_fallback = False

    def _count_records(self, validated: CostDataPayload) -> int:
        return len(validated.records)

    def _fetch_live_data(self) -> dict[str, Any]:
        from src.collector.auth import get_azure_credential
        from azure.mgmt.costmanagement import CostManagementClient
        from azure.mgmt.costmanagement.models import QueryDefinition, QueryDataset, QueryAggregation, QueryGrouping, QueryTimePeriod
        from datetime import datetime, timezone, timedelta
        from typing import Any

        credential = self.credential or get_azure_credential()
        client = CostManagementClient(credential)
        sub_id = self.context.subscription_id
        scope = f"/subscriptions/{sub_id}"

        now = datetime.now(timezone.utc)
        start = now - timedelta(days=self.settings.cost_lookback_days)
        collection_run_id = f"cost-{uuid4()}"
        
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
                    QueryGrouping(type="Dimension", name="ResourceId"),
                    QueryGrouping(type="Dimension", name="ResourceGroup"),
                    QueryGrouping(type="Dimension", name="ServiceName"),
                    QueryGrouping(type="Dimension", name="ResourceLocation"),
                ]
            )
        )
        
        res = client.query.usage(scope=scope, parameters=query)
        records = []
        columns = [column.name for column in (res.columns or [])]
        if res.rows:
            for row in res.rows:
                values = dict(zip(columns, row))
                date_str = str(values.get("UsageDate", ""))
                # Format YYYYMMDD to YYYY-MM-DD
                if len(date_str) == 8 and date_str.isdigit():
                    date_str = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
                elif "T" in date_str:
                    date_str = date_str.split("T")[0]
                    
                records.append({
                    "costAmount": float(values.get("PreTaxCost", 0) or 0),
                    "usageQuantity": float(values.get("UsageQuantity", 0) or 0),
                    "date": date_str,
                    "resourceId": values.get("ResourceId") or "",
                    "resourceGroup": values.get("ResourceGroup") or "Unknown",
                    "serviceName": values.get("ServiceName") or "Unknown",
                    "location": values.get("ResourceLocation") or "Unknown",
                    "currency": values.get("Currency") or "UNKNOWN",
                    "sourceSystem": "Azure Cost Management",
                    "sourceTimestamp": now.isoformat(),
                    "collectionRunId": collection_run_id,
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
                "resource_id": r.get("resourceId", ""),
                "resource_group": r["resourceGroup"],
                "service_name": r["serviceName"],
                "location": r["location"],
                "cost_amount": r.get("costAmount", r.get("costUSD", 0)),
                "usage_quantity": r["usageQuantity"],
                "currency": r.get("currency", "UNKNOWN"),
                "source_system": r.get("sourceSystem", "Azure Cost Management"),
                "source_timestamp": r.get("sourceTimestamp", ""),
                "collection_run_id": r.get("collectionRunId", ""),
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
