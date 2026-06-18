"""Load processed reports, raw costs, and FAISS index metadata for the dashboard."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from src.config import Settings, get_settings
from src.storage.factory import create_storage_provider

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
    cost_facts: pd.DataFrame = field(default_factory=pd.DataFrame)
    daily_costs: pd.DataFrame = field(default_factory=pd.DataFrame)
    service_costs: pd.DataFrame = field(default_factory=pd.DataFrame)
    faiss_manifest: dict[str, Any] = field(default_factory=dict)
    data_available: bool = False

    @property
    def total_costs(self) -> dict[str, float]:
        if self.summary.get("total_cost"):
            return {
                str(currency): float(amount)
                for currency, amount in self.summary["total_cost"].items()
            }
        if "total_cost_usd" in self.summary:
            return {"USD": float(self.summary["total_cost_usd"])}
        if not self.cost_facts.empty:
            amount_col = (
                "cost_amount" if "cost_amount" in self.cost_facts else "cost_usd"
            )
            currency = (
                self.cost_facts["currency"].fillna("USD")
                if "currency" in self.cost_facts
                else pd.Series("USD", index=self.cost_facts.index)
            )
            return (
                self.cost_facts.assign(_currency=currency)
                .groupby("_currency")[amount_col]
                .sum()
                .to_dict()
            )
        return {}

    @property
    def total_monthly_cost(self) -> float:
        return sum(self.total_costs.values()) if len(self.total_costs) <= 1 else 0.0

    @property
    def savings_totals(self) -> dict[str, float]:
        if self.waste.get("total_estimated_savings"):
            return {
                str(currency): float(amount)
                for currency, amount in self.waste["total_estimated_savings"].items()
            }
        if not self.resources.empty and "savings_currency" in self.resources:
            flagged = self.resources[
                self.resources["savings_currency"].fillna("") != ""
            ]
            return (
                flagged.groupby("savings_currency")["estimated_savings"]
                .sum()
                .to_dict()
            )
        legacy = self.waste.get(
            "total_estimated_savings_usd",
            self.summary.get("total_estimated_savings_usd", 0),
        )
        return {"USD": float(legacy)} if legacy else {}

    @property
    def total_savings(self) -> float:
        return sum(self.savings_totals.values()) if len(self.savings_totals) <= 1 else 0.0

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
        self.storage = create_storage_provider(self.settings)

    def load(self) -> DashboardData:
        data = DashboardData()
        processed = self.settings.processed_path
        raw = self.settings.raw_path
        tenant_id = self.settings.effective_tenant_id
        subscription_id = self.settings.effective_subscription_id

        repository_resources = self.storage.resources.list_latest(
            tenant_id, subscription_id
        )
        repository_costs = self.storage.cost_facts.list_latest(
            tenant_id, subscription_id
        )
        repository_recommendations = self.storage.recommendations.list_latest(
            tenant_id, subscription_id
        )

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
        if repository_resources:
            data.resources = pd.DataFrame(
                [
                    {
                        **item.attributes,
                        **item.model_dump(mode="json", exclude={"attributes"}),
                        "monthly_cost": item.estimated_monthly_cost,
                    }
                    for item in repository_resources
                ]
            )
        elif resources_path.exists():
            data.resources = pd.read_csv(resources_path)
            logger.info("Loaded %d resources", len(data.resources))

        cost_facts_path = processed / "cost_facts_latest.csv"
        if repository_costs:
            data.cost_facts = pd.DataFrame(
                [item.model_dump(mode="json") for item in repository_costs]
            )
        elif cost_facts_path.exists():
            data.cost_facts = pd.read_csv(cost_facts_path)
            logger.info("Loaded %d cost facts", len(data.cost_facts))
        if repository_recommendations:
            latest = repository_recommendations[-1]
            data.recommendations = {
                "recommendations": latest.content,
                "source_system": latest.source_system,
                "source_timestamp": str(latest.source_timestamp),
                **latest.model_dump(by_alias=True, mode="json"),
            }

        data.daily_costs = self._load_daily_costs(
            raw, data.summary, data.cost_facts
        )
        data.service_costs = self._load_service_costs(
            raw, data.summary, data.cost_facts, data.resources
        )

        data.data_available = bool(
            data.summary
            or not data.cost_facts.empty
            or not data.resources.empty
            or data.waste.get("findings")
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
        self,
        raw_path: Path,
        summary: dict[str, Any],
        cost_facts: pd.DataFrame,
    ) -> pd.DataFrame:
        if not cost_facts.empty:
            df = cost_facts.copy()
            df["date"] = pd.to_datetime(df["date"])
            amount_col = "cost_amount" if "cost_amount" in df else "cost_usd"
            return (
                df.groupby(["date", "currency"])[amount_col]
                .sum()
                .reset_index()
                .rename(columns={amount_col: "cost_amount"})
                .sort_values("date")
            )

        if summary.get("daily_trend"):
            df = pd.DataFrame(summary["daily_trend"])
            if "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"])
            return df

        costs_path = raw_path / "costs_latest.json"
        if not costs_path.exists():
            return pd.DataFrame(columns=["date", "currency", "cost_amount"])

        payload = self._load_json(costs_path)
        records = payload.get("records", [])
        if not records:
            return pd.DataFrame(columns=["date", "currency", "cost_amount"])

        df = pd.DataFrame(records)
        df["date"] = pd.to_datetime(df["date"])
        daily = (
            df.groupby(["date", "currency"])["costAmount" if "costAmount" in df else "costUSD"]
            .sum()
            .reset_index()
            .rename(columns={
                "costAmount" if "costAmount" in df else "costUSD": "cost_amount"
            })
            .sort_values("date")
        )
        return daily

    def _load_service_costs(
        self,
        raw_path: Path,
        summary: dict[str, Any],
        cost_facts: pd.DataFrame,
        resources: pd.DataFrame,
    ) -> pd.DataFrame:
        if not cost_facts.empty:
            amount_col = "cost_amount" if "cost_amount" in cost_facts else "cost_usd"
            return (
                cost_facts.groupby(["service_name", "currency"])[amount_col]
                .sum()
                .reset_index()
                .rename(columns={amount_col: "cost_amount"})
                .sort_values("cost_amount", ascending=False)
            )

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

        return pd.DataFrame(columns=["service_name", "currency", "cost_amount"])

    @staticmethod
    def _build_fallback_summary(data: DashboardData) -> dict[str, Any]:
        return {
            "schema_version": 2,
            "total_cost": data.total_costs,
            "total_estimated_savings": data.savings_totals,
            "anomaly_count": data.anomaly_count,
            "top_services": data.service_costs.head(10).to_dict(orient="records")
            if not data.service_costs.empty
            else [],
            "top_resource_groups": [],
            "daily_trend": data.daily_costs.to_dict(orient="records")
            if not data.daily_costs.empty
            else [],
        }
