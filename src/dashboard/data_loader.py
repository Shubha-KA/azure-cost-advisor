"""Load processed reports, raw costs, and FAISS index metadata for the dashboard."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from src.config import Settings, get_settings

logger = logging.getLogger(__name__)


@dataclass
class DashboardData:
    """Container for all dashboard data sources."""

    summary: dict[str, Any] = field(default_factory=dict)
    resources: pd.DataFrame = field(default_factory=pd.DataFrame)
    waste: dict[str, Any] = field(default_factory=dict)
    anomalies: dict[str, Any] = field(default_factory=dict)
    recommendations: dict[str, Any] = field(default_factory=dict)
    processing_report: dict[str, Any] = field(default_factory=dict)
    daily_costs: pd.DataFrame = field(default_factory=pd.DataFrame)
    service_costs: pd.DataFrame = field(default_factory=pd.DataFrame)
    faiss_manifest: dict[str, Any] = field(default_factory=dict)
    data_available: bool = False

    @property
    def total_monthly_cost(self) -> float:
        if self.summary.get("total_cost_usd"):
            return float(self.summary["total_cost_usd"])
        if not self.resources.empty and "monthly_cost" in self.resources.columns:
            return float(self.resources["monthly_cost"].sum())
        return 0.0

    @property
    def total_savings(self) -> float:
        if self.waste.get("total_estimated_savings_usd"):
            return float(self.waste["total_estimated_savings_usd"])
        if not self.resources.empty and "estimated_savings" in self.resources.columns:
            return float(self.resources["estimated_savings"].sum())
        return float(self.summary.get("total_estimated_savings_usd", 0))

    @property
    def anomaly_count(self) -> int:
        return int(self.anomalies.get("anomaly_count", 0))

    @property
    def faiss_ready(self) -> bool:
        return bool(self.faiss_manifest.get("chunk_count", 0))


class DashboardDataLoader:
    """Loads JSON/CSV artifacts from data/processed/ and data/raw/."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def load(self) -> DashboardData:
        data = DashboardData()
        processed = self.settings.processed_path
        raw = self.settings.raw_path

        data.summary = self._load_json(processed / "summary_latest.json")
        data.waste = self._load_json(processed / "waste_findings_latest.json")
        data.anomalies = self._load_json(processed / "anomalies_latest.json")
        data.recommendations = self._load_json(processed / "recommendations_latest.json")
        data.processing_report = self._load_json(
            processed / "processing_report_latest.json"
        )
        data.faiss_manifest = self._load_json(
            self.settings.embeddings_path / "manifest.json"
        )

        resources_path = processed / "resources_latest.csv"
        if resources_path.exists():
            data.resources = pd.read_csv(resources_path)
            logger.info("Loaded %d resources", len(data.resources))

        data.daily_costs = self._load_daily_costs(raw, data.summary)
        data.service_costs = self._load_service_costs(raw, data.summary, data.resources)

        data.data_available = bool(
            data.summary or not data.resources.empty or data.waste.get("findings")
        )

        if not data.summary and data.data_available:
            data.summary = self._build_fallback_summary(data)

        return data

    def _load_json(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            logger.warning("Failed to parse %s: %s", path.name, exc)
            return {}

    def _load_daily_costs(
        self, raw_path: Path, summary: dict[str, Any]
    ) -> pd.DataFrame:
        if summary.get("daily_trend"):
            df = pd.DataFrame(summary["daily_trend"])
            if "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"])
            return df

        costs_path = raw_path / "costs_latest.json"
        if not costs_path.exists():
            return pd.DataFrame(columns=["date", "daily_cost"])

        payload = self._load_json(costs_path)
        records = payload.get("records", [])
        if not records:
            return pd.DataFrame(columns=["date", "daily_cost"])

        df = pd.DataFrame(records)
        df["date"] = pd.to_datetime(df["date"])
        daily = (
            df.groupby("date")["costUSD"]
            .sum()
            .reset_index()
            .rename(columns={"costUSD": "daily_cost"})
            .sort_values("date")
        )
        return daily

    def _load_service_costs(
        self,
        raw_path: Path,
        summary: dict[str, Any],
        resources: pd.DataFrame,
    ) -> pd.DataFrame:
        if summary.get("top_services"):
            return pd.DataFrame(summary["top_services"])

        costs_path = raw_path / "costs_latest.json"
        if costs_path.exists():
            payload = self._load_json(costs_path)
            records = payload.get("records", [])
            if records:
                df = pd.DataFrame(records)
                return (
                    df.groupby("serviceName")["costUSD"]
                    .sum()
                    .reset_index()
                    .rename(columns={"serviceName": "service_name", "costUSD": "cost_usd"})
                    .sort_values("cost_usd", ascending=False)
                )

        if not resources.empty and "resource_type" in resources.columns:
            return (
                resources.groupby("resource_type")["monthly_cost"]
                .sum()
                .reset_index()
                .rename(columns={"resource_type": "service_name", "monthly_cost": "cost_usd"})
                .sort_values("cost_usd", ascending=False)
            )

        return pd.DataFrame(columns=["service_name", "cost_usd"])

    @staticmethod
    def _build_fallback_summary(data: DashboardData) -> dict[str, Any]:
        return {
            "total_cost_usd": data.total_monthly_cost,
            "total_estimated_savings_usd": data.total_savings,
            "anomaly_count": data.anomaly_count,
            "top_services": data.service_costs.head(10).to_dict(orient="records")
            if not data.service_costs.empty
            else [],
            "top_resource_groups": [],
            "daily_trend": data.daily_costs.to_dict(orient="records")
            if not data.daily_costs.empty
            else [],
        }
