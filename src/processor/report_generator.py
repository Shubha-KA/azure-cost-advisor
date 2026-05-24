"""Export processed resources and summary reports to data/processed/."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.config import Settings, get_settings
from src.processor.schemas import CANONICAL_COLUMNS
from src.processor.savings_estimator import SavingsEstimator

logger = logging.getLogger(__name__)


class ReportGenerator:
    """Writes JSON, CSV, and summary reports for downstream consumers."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.settings.processed_path.mkdir(parents=True, exist_ok=True)

    def generate(
        self,
        resources_df: pd.DataFrame,
        anomalies_payload: dict,
        savings_summary: dict,
    ) -> dict[str, Path]:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        canonical = resources_df[CANONICAL_COLUMNS].copy()
        waste_payload = self._build_waste_payload(resources_df)

        outputs: dict[str, Path] = {}
        outputs["resources_csv"] = self._write_csv(canonical, timestamp)
        outputs["resources_json"] = self._write_json(
            canonical, f"resources_{timestamp}.json", "resources_latest.json"
        )
        outputs["waste_findings"] = self._write_json(
            waste_payload,
            f"waste_findings_{timestamp}.json",
            "waste_findings_latest.json",
        )
        outputs["anomalies"] = self._write_json(
            anomalies_payload,
            f"anomalies_{timestamp}.json",
            "anomalies_latest.json",
        )
        summary = self._build_cost_summary(resources_df, savings_summary, anomalies_payload)
        outputs["summary"] = self._write_json(
            summary, f"summary_{timestamp}.json", "summary_latest.json"
        )
        outputs["processing_report"] = self._write_json(
            self._build_processing_report(resources_df, savings_summary, anomalies_payload),
            f"processing_report_{timestamp}.json",
            "processing_report_latest.json",
        )
        outputs["summary_markdown"] = self._write_markdown_summary(
            resources_df, summary, savings_summary, anomalies_payload, timestamp
        )

        logger.info("Generated %d processed outputs in %s", len(outputs), self.settings.processed_path)
        return outputs

    def _write_csv(self, df: pd.DataFrame, timestamp: str) -> Path:
        ts_path = self.settings.processed_path / f"resources_{timestamp}.csv"
        latest_path = self.settings.processed_path / "resources_latest.csv"
        df.to_csv(ts_path, index=False)
        df.to_csv(latest_path, index=False)
        return latest_path

    def _write_json(
        self, payload: dict | list | pd.DataFrame, ts_name: str, latest_name: str
    ) -> Path:
        if isinstance(payload, pd.DataFrame):
            data: Any = payload.to_dict(orient="records")
        else:
            data = payload

        ts_path = self.settings.processed_path / ts_name
        latest_path = self.settings.processed_path / latest_name
        serialized = json.dumps(data, indent=2, default=str)
        ts_path.write_text(serialized, encoding="utf-8")
        latest_path.write_text(serialized, encoding="utf-8")
        return latest_path

    def _build_waste_payload(self, df: pd.DataFrame) -> dict:
        from src.processor.waste_detector import WasteDetector

        return WasteDetector(self.settings).to_findings_payload(df)

    def _build_cost_summary(
        self,
        df: pd.DataFrame,
        savings_summary: dict,
        anomalies_payload: dict,
    ) -> dict:
        total_cost = round(float(df["monthly_cost"].sum()), 2)
        by_type = (
            df.groupby("resource_type")["monthly_cost"]
            .sum()
            .sort_values(ascending=False)
            .reset_index()
            .rename(columns={"monthly_cost": "cost_usd"})
        )
        top_services = [
            {"service_name": row["resource_type"], "cost_usd": round(row["cost_usd"], 2)}
            for _, row in by_type.head(10).iterrows()
        ]
        by_rg = (
            df.groupby("resource_group")["monthly_cost"]
            .sum()
            .sort_values(ascending=False)
            .reset_index()
        )
        top_rgs = [
            {"resource_group": row["resource_group"], "cost_usd": round(row["monthly_cost"], 2)}
            for _, row in by_rg.head(10).iterrows()
            if pd.notna(row["resource_group"])
        ]

        return {
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
            "total_cost_usd": total_cost,
            "avg_daily_cost_usd": round(total_cost / 30, 2),
            "period_start": datetime.now(timezone.utc).strftime("%Y-%m-01"),
            "period_end": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "unique_services": int(df["resource_type"].nunique()),
            "unique_resource_groups": int(df["resource_group"].nunique()),
            "peak_day": {"date": None, "cost_usd": 0},
            "top_services": top_services,
            "top_resource_groups": top_rgs,
            "top_locations": [],
            "daily_trend": [],
            "total_estimated_savings_usd": savings_summary.get(
                "total_estimated_savings_usd", 0
            ),
            "anomaly_count": anomalies_payload.get("anomaly_count", 0),
            "waste_resource_count": savings_summary.get("waste_resource_count", 0),
        }

    def _build_processing_report(
        self,
        df: pd.DataFrame,
        savings_summary: dict,
        anomalies_payload: dict,
    ) -> dict:
        waste_breakdown = (
            df[df["waste_level"] != "NONE"]
            .groupby(["rule_id", "waste_level"])
            .agg(
                resource_count=("resource_name", "count"),
                total_monthly_cost=("monthly_cost", "sum"),
                total_estimated_savings=("estimated_savings", "sum"),
            )
            .reset_index()
            .to_dict(orient="records")
        )
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "resource_count": len(df),
            "waste_breakdown": waste_breakdown,
            "savings_summary": savings_summary,
            "anomaly_summary": {
                "anomaly_count": anomalies_payload.get("anomaly_count", 0),
                "rule": anomalies_payload.get("rule", ""),
            },
            "waste_level_distribution": df["waste_level"]
            .value_counts()
            .to_dict(),
        }

    def _write_markdown_summary(
        self,
        df: pd.DataFrame,
        summary: dict,
        savings_summary: dict,
        anomalies_payload: dict,
        timestamp: str,
    ) -> Path:
        flagged = df[df["waste_level"] != "NONE"].sort_values(
            "estimated_savings", ascending=False
        )
        lines = [
            "# Azure Cost Processing Report",
            "",
            f"**Generated:** {summary['analyzed_at']}",
            "",
            "## Executive Summary",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Total Monthly Cost | ${summary['total_cost_usd']:,.2f} |",
            f"| Waste Resources | {savings_summary.get('waste_resource_count', 0)} |",
            f"| Est. Monthly Savings | ${savings_summary.get('total_estimated_savings_usd', 0):,.2f} |",
            f"| Cost Anomalies | {anomalies_payload.get('anomaly_count', 0)} |",
            "",
            "## Top Waste Findings",
            "",
        ]
        if flagged.empty:
            lines.append("_No waste detected._")
        else:
            lines.append(
                "| Resource | Type | Waste Level | Recommendation | Est. Savings |"
            )
            lines.append("|---|---|---|---|---|")
            for _, row in flagged.head(15).iterrows():
                lines.append(
                    f"| {row['resource_name']} | {row['resource_type']} | "
                    f"{row['waste_level']} | {row['recommendation']} | "
                    f"${row['estimated_savings']:,.2f} |"
                )

        lines.extend(["", "## Anomalies", ""])
        anomalies = anomalies_payload.get("anomalies", [])
        if not anomalies:
            lines.append("_No anomalies detected._")
        else:
            for a in anomalies[:10]:
                lines.append(f"- {a.get('description', 'Unknown anomaly')}")

        ts_path = self.settings.processed_path / f"report_{timestamp}.md"
        latest_path = self.settings.processed_path / "report_latest.md"
        content = "\n".join(lines)
        ts_path.write_text(content, encoding="utf-8")
        latest_path.write_text(content, encoding="utf-8")
        return latest_path

    def load_latest_resources(self) -> pd.DataFrame:
        path = self.settings.processed_path / "resources_latest.csv"
        if not path.exists():
            raise FileNotFoundError("No processed resources found. Run the processor first.")
        return pd.read_csv(path)

    def load_latest_summary(self) -> dict:
        path = self.settings.processed_path / "summary_latest.json"
        if not path.exists():
            raise FileNotFoundError("No summary found. Run the processor first.")
        return json.loads(path.read_text(encoding="utf-8"))
