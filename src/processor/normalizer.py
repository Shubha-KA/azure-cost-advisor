"""Load raw collector JSON and normalize into a unified Pandas DataFrame."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from src.config import Settings, get_settings
from src.domain.context import OperationContext
from src.storage.factory import create_storage_provider
from src.processor.schemas import (
    CANONICAL_COLUMNS,
    COST_FACT_COLUMNS,
    ENRICHED_COLUMNS,
    RAW_FILE_MAP,
)

logger = logging.getLogger(__name__)


class ProcessorError(Exception):
    """Raised when processor normalization fails."""


class RawDataLoader:
    """Reads latest JSON envelopes from data/raw/."""

    def __init__(
        self,
        settings: Settings | None = None,
        context: OperationContext | None = None,
        storage=None,
    ) -> None:
        self.settings = settings or get_settings()
        self.raw_path = self.settings.raw_path
        self.context = context
        self.storage = storage or (
            create_storage_provider(self.settings) if context else None
        )

    def load(self, key: str) -> dict[str, Any]:
        filename = RAW_FILE_MAP.get(key)
        if not filename:
            raise ProcessorError(f"Unknown raw data key: {key}")
        if self.context and self.storage:
            payload = self.storage.raw_payloads.load_latest(
                self.context.tenant_id,
                self.context.subscription_id,
                filename.removesuffix("_latest.json"),
            )
            if payload is not None:
                return payload
            raise ProcessorError(
                f"Tenant-scoped raw payload not found for "
                f"{self.context.tenant_id}/{self.context.subscription_id}/{key}"
            )
        path = self.raw_path / filename
        if not path.exists():
            raise ProcessorError(
                f"Raw file not found: {path}. Run collectors first (python -m src.collector.run)."
            )
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ProcessorError(f"Invalid JSON in {path.name}: {exc}") from exc

    def load_all_available(self) -> dict[str, dict[str, Any]]:
        payloads: dict[str, dict[str, Any]] = {}
        for key in RAW_FILE_MAP:
            path = self.raw_path / RAW_FILE_MAP[key]
            repository_payload = None
            if self.context and self.storage:
                repository_payload = self.storage.raw_payloads.load_latest(
                    self.context.tenant_id,
                    self.context.subscription_id,
                    RAW_FILE_MAP[key].removesuffix("_latest.json"),
                )
            available = (
                repository_payload is not None
                if self.context
                else path.exists()
            )
            if available:
                try:
                    payloads[key] = self.load(key)
                    logger.info("Loaded raw payload: %s", path.name)
                except ProcessorError as exc:
                    logger.warning("Skipping %s: %s", key, exc)
            else:
                logger.warning("Raw file missing: %s", path.name)
        if not payloads:
            raise ProcessorError("No raw JSON files found in data/raw/")
        return payloads


class DataNormalizer:
    """Merges heterogeneous Azure raw payloads into one enriched resource DataFrame."""

    def __init__(
        self,
        settings: Settings | None = None,
        context: OperationContext | None = None,
        storage=None,
    ) -> None:
        self.settings = settings or get_settings()
        self.storage = storage or create_storage_provider(self.settings)
        self.context = context or OperationContext.create(
            self.settings.effective_tenant_id,
            self.settings.effective_subscription_id,
        )
        self.loader = RawDataLoader(
            self.settings, context, self.storage if context else None
        )

    def normalize(self, payloads: dict[str, dict[str, Any]] | None = None) -> pd.DataFrame:
        payloads = payloads or self.loader.load_all_available()
        frames: list[pd.DataFrame] = []

        if "vm_metrics" in payloads and "costs" in payloads:
            frames.append(self._normalize_vms(payloads["vm_metrics"], payloads["costs"]))
        elif "vm_metrics" in payloads:
            frames.append(self._normalize_vms(payloads["vm_metrics"], {}))
        if "resource_graph" in payloads:
            frames.append(self._normalize_disks(payloads["resource_graph"]))
            frames.append(self._normalize_public_ips(payloads["resource_graph"]))
        if "aks_metrics" in payloads:
            frames.append(self._normalize_aks(payloads["aks_metrics"]))

        populated_frames = [frame for frame in frames if not frame.empty]
        df = (
            pd.concat(populated_frames, ignore_index=True)
            if populated_frames
            else pd.DataFrame(columns=ENRICHED_COLUMNS)
        )
        df = self._apply_defaults(df)
        if "costs" in payloads:
            df = self._attribute_resource_costs(
                df, self.normalize_cost_facts(payloads["costs"])
            )
        df = self._validate_schema(df)
        logger.info("Normalized %d resources across %d types", len(df), df["resource_type"].nunique())
        return df

    def normalize_cost_facts(
        self, costs: dict[str, Any] | None = None
    ) -> pd.DataFrame:
        """Preserve Cost Management rows as a separate normalized fact dataset."""
        costs = costs if costs is not None else self.loader.load("costs")
        records = costs.get("records", [])
        if not records:
            return pd.DataFrame(columns=COST_FACT_COLUMNS)

        source_columns = {
            "date",
            "resourceGroup",
            "serviceName",
            "location",
            "usageQuantity",
        }
        missing = source_columns.difference(records[0])
        if "costAmount" not in records[0] and "costUSD" not in records[0]:
            missing.add("costAmount")
        if missing:
            raise ProcessorError(
                f"Cost records missing required fields: {sorted(missing)}"
            )

        df = pd.DataFrame(records)
        facts = pd.DataFrame(
            {
                "tenant_id": self.context.tenant_id,
                "subscription_id": self.context.subscription_id,
                "collection_run_id": self.context.collection_run_id,
                "processing_run_id": self.context.processing_run_id,
                "correlation_id": self.context.correlation_id,
                "schema_version": self.context.schema_version,
                "date": pd.to_datetime(df["date"], errors="coerce"),
                "resource_id": df.get(
                    "resourceId", pd.Series("", index=df.index)
                ).fillna("").astype(str).map(self.normalize_resource_id),
                "resource_group": df["resourceGroup"].fillna("Unknown").astype(str),
                "service_name": df["serviceName"].fillna("Unknown").astype(str),
                "location": df["location"].fillna("Unknown").astype(str),
                "cost_amount": pd.to_numeric(
                    df["costAmount"] if "costAmount" in df else df["costUSD"],
                    errors="coerce",
                ),
                "usage_quantity": pd.to_numeric(
                    df["usageQuantity"], errors="coerce"
                ),
                "currency": df.get(
                    "currency", pd.Series("UNKNOWN", index=df.index)
                ).fillna("UNKNOWN").astype(str).str.upper(),
                "source_system": df.get(
                    "sourceSystem",
                    pd.Series("Azure Cost Management", index=df.index),
                ).fillna("Azure Cost Management").astype(str),
                "source_timestamp": df.get(
                    "sourceTimestamp",
                    pd.Series(
                        costs.get("metadata", {}).get("generatedAt", ""),
                        index=df.index,
                    ),
                ).fillna("").astype(str),
            }
        )

        if facts["date"].isna().any():
            raise ProcessorError("Cost facts contain invalid dates")
        if facts["cost_amount"].isna().any():
            raise ProcessorError("Cost facts contain invalid cost values")
        if facts["usage_quantity"].isna().any():
            raise ProcessorError("Cost facts contain invalid usage quantities")

        facts["date"] = facts["date"].dt.strftime("%Y-%m-%d")
        facts["cost_amount"] = facts["cost_amount"].astype(float)
        facts["usage_quantity"] = facts["usage_quantity"].astype(float)
        facts = facts[COST_FACT_COLUMNS]
        logger.info(
            "Normalized %d Cost Management records into cost facts", len(facts)
        )
        return facts

    def _normalize_vms(
        self, metrics: dict[str, Any], costs: dict[str, Any]
    ) -> pd.DataFrame:
        resources = metrics.get("resources", [])
        if not resources:
            return pd.DataFrame()

        cost_df = self._build_vm_cost_lookup(costs)
        rows: list[dict[str, Any]] = []
        for res in resources:
            rg = res["resourceGroup"]
            name = res["resourceName"]
            metrics_payload = res.get("metrics", {})
            cpu = float(
                metrics_payload.get("Percentage CPU", {}).get("average", 0)
            )
            if "Available Memory Percentage" in metrics_payload:
                mem_pct = 100.0 - float(
                    metrics_payload["Available Memory Percentage"].get("average", 0)
                )
            else:
                mem_bytes = float(
                    metrics_payload.get("Available Memory Bytes", {}).get("average", 0)
                )
                mem_pct = self._memory_utilization_percent(mem_bytes)

            monthly_cost = float(cost_df.get((rg, "Virtual Machines"), 0.0))
            vm_count = max(
                1,
                sum(
                    1
                    for r in resources
                    if r["resourceGroup"] == rg
                ),
            )
            allocated_cost = round(monthly_cost / vm_count, 2)

            rows.append(
                {
                    **self._resource_cost_fields(
                        resource_id=res.get("resourceId", ""),
                        resource_group=rg,
                        location=res.get("location", ""),
                        estimate=allocated_cost,
                        estimate_currency="",
                        source_system="Azure Monitor",
                        source_timestamp=res.get(
                            "sourceTimestamp",
                            metrics.get("metadata", {}).get("generatedAt", ""),
                        ),
                        collection_run_id=res.get(
                            "collectionRunId",
                            metrics.get("ingestion", {}).get(
                                "ingestionId", "legacy"
                            ),
                        ),
                    ),
                    "resource_name": name,
                    "resource_type": "Virtual Machine",
                    "monthly_cost": allocated_cost,
                    "cpu_avg_percent": round(cpu, 2),
                    "memory_avg_percent": round(mem_pct, 2),
                    "waste_level": "NONE",
                    "recommendation": "",
                    "estimated_savings": 0.0,
                    "savings_currency": "",
                    "telemetry_available": "Percentage CPU" in metrics_payload,
                    "disk_state": None,
                    "attached": None,
                    "node_utilization": None,
                    "anomaly": False,
                    "rule_id": None,
                    "cost_estimate_method": (
                        "resource_group_service_cost_allocation"
                        if allocated_cost
                        else None
                    ),
                    "cost_estimate_source": (
                        "Azure Cost Management"
                        if allocated_cost
                        else None
                    ),
                }
            )
        return pd.DataFrame(rows)

    @staticmethod
    def _build_vm_cost_lookup(costs: dict[str, Any]) -> dict[tuple[str, str], float]:
        records = costs.get("records", [])
        if not records:
            return {}
        df = pd.DataFrame(records)
        cost_column = "costAmount" if "costAmount" in df else "costUSD"
        grouped = df.groupby(["resourceGroup", "serviceName"])[cost_column].sum().to_dict()
        return {(rg, svc): float(val) for (rg, svc), val in grouped.items()}

    @staticmethod
    def _memory_utilization_percent(available_bytes: float) -> float:
        if available_bytes <= 0:
            return 0.0
        assumed_total_gb = 16.0
        available_gb = available_bytes / 1e9
        used_pct = max(0.0, min(100.0, (1.0 - available_gb / assumed_total_gb) * 100))
        return used_pct

    def _normalize_disks(self, graph: dict[str, Any]) -> pd.DataFrame:
        disks = graph.get("unattachedDisks", [])
        rows = []
        for disk in disks:
            rows.append(
                {
                    **self._resource_cost_fields(
                        resource_id=disk.get("diskId", ""),
                        resource_group=disk.get("resourceGroup", ""),
                        location=disk.get("location", ""),
                        estimate=float(disk.get("monthlyCostEstimateUsd", 0)),
                        estimate_currency="USD",
                        source_system="Azure Resource Graph",
                        source_timestamp=graph.get("metadata", {}).get(
                            "generatedAt", ""
                        ),
                        collection_run_id=graph.get("ingestion", {}).get(
                            "ingestionId", "legacy"
                        ),
                    ),
                    "resource_name": disk.get("diskName", "unknown-disk"),
                    "resource_type": "Managed Disk",
                    "monthly_cost": float(disk.get("monthlyCostEstimateUsd", 0)),
                    "cpu_avg_percent": 0.0,
                    "memory_avg_percent": 0.0,
                    "waste_level": "NONE",
                    "recommendation": "",
                    "estimated_savings": 0.0,
                    "savings_currency": "USD",
                    "telemetry_available": False,
                    "disk_state": "Unattached",
                    "attached": None,
                    "node_utilization": None,
                    "anomaly": False,
                    "rule_id": None,
                    "cost_estimate_method": disk.get(
                        "costEstimateMethod",
                        "legacy_disk_monthly_cost_estimate_usd",
                    ),
                    "cost_estimate_source": "synthetic_resource_graph_estimate",
                }
            )
        return pd.DataFrame(rows)

    def _normalize_public_ips(self, graph: dict[str, Any]) -> pd.DataFrame:
        ips = graph.get("publicIps", [])
        rows = []
        for ip in ips:
            rows.append(
                {
                    **self._resource_cost_fields(
                        resource_id=ip.get("id", ip.get("resourceId", "")),
                        resource_group=ip.get("resourceGroup", ""),
                        location=ip.get("location", ""),
                        estimate=float(ip.get("monthlyCostEstimateUsd", 0)),
                        estimate_currency="USD",
                        source_system="Azure Resource Graph",
                        source_timestamp=graph.get("metadata", {}).get(
                            "generatedAt", ""
                        ),
                        collection_run_id=graph.get("ingestion", {}).get(
                            "ingestionId", "legacy"
                        ),
                    ),
                    "resource_name": ip.get("name", "unknown-pip"),
                    "resource_type": "Public IP Address",
                    "monthly_cost": float(ip.get("monthlyCostEstimateUsd", 0)),
                    "cpu_avg_percent": 0.0,
                    "memory_avg_percent": 0.0,
                    "waste_level": "NONE",
                    "recommendation": "",
                    "estimated_savings": 0.0,
                    "savings_currency": "USD",
                    "telemetry_available": False,
                    "disk_state": None,
                    "attached": bool(ip.get("associated", False)),
                    "node_utilization": None,
                    "anomaly": False,
                    "rule_id": None,
                    "cost_estimate_method": ip.get(
                        "costEstimateMethod",
                        "legacy_public_ip_monthly_cost_estimate_usd",
                    ),
                    "cost_estimate_source": "synthetic_resource_graph_estimate",
                }
            )
        return pd.DataFrame(rows)

    def _normalize_aks(self, aks: dict[str, Any]) -> pd.DataFrame:
        clusters = aks.get("clusters", [])
        rows = []
        for cluster in clusters:
            util = float(cluster.get("metrics", {}).get("cpuUtilizationPercent", 0))
            monthly_estimate = float(cluster.get("monthlyCostEstimateUsd", 0))
            rows.append(
                {
                    **self._resource_cost_fields(
                        resource_id=cluster.get("resourceId", ""),
                        resource_group=cluster.get("resourceGroup", ""),
                        location=cluster.get("location", ""),
                        estimate=monthly_estimate,
                        estimate_currency="USD" if monthly_estimate else "",
                        source_system="Azure Monitor",
                        source_timestamp=cluster.get(
                            "sourceTimestamp",
                            aks.get("metadata", {}).get("generatedAt", ""),
                        ),
                        collection_run_id=cluster.get(
                            "collectionRunId",
                            aks.get("ingestion", {}).get("ingestionId", "legacy"),
                        ),
                    ),
                    "resource_name": cluster.get("clusterName", "unknown-aks"),
                    "resource_type": "AKS Cluster",
                    "monthly_cost": monthly_estimate,
                    "cpu_avg_percent": util,
                    "memory_avg_percent": float(
                        cluster.get("metrics", {}).get("memoryUtilizationPercent", 0)
                    ),
                    "waste_level": "NONE",
                    "recommendation": "",
                    "estimated_savings": 0.0,
                    "savings_currency": "USD" if monthly_estimate else "",
                    "telemetry_available": bool(cluster.get("metrics")),
                    "disk_state": None,
                    "attached": None,
                    "node_utilization": util,
                    "anomaly": False,
                    "rule_id": None,
                    "cost_estimate_method": (
                        "collector_monthly_cost_estimate_usd"
                        if monthly_estimate
                        else None
                    ),
                    "cost_estimate_source": (
                        "synthetic_collector_estimate"
                        if monthly_estimate
                        else None
                    ),
                }
            )
        return pd.DataFrame(rows)

    def _apply_defaults(self, df: pd.DataFrame) -> pd.DataFrame:
        context_defaults = {
            "tenant_id": self.context.tenant_id,
            "subscription_id": self.context.subscription_id,
            "collection_run_id": self.context.collection_run_id,
            "processing_run_id": self.context.processing_run_id,
            "correlation_id": self.context.correlation_id,
            "schema_version": self.context.schema_version,
        }
        for col in ENRICHED_COLUMNS:
            if col not in df.columns:
                if col in context_defaults:
                    df[col] = context_defaults[col]
                    continue
                if col == "anomaly":
                    df[col] = False
                elif col == "telemetry_available":
                    df[col] = False
                elif col in (
                    "cpu_avg_percent",
                    "memory_avg_percent",
                    "monthly_cost",
                    "actual_cost_collected_period",
                    "estimated_monthly_cost",
                    "estimated_savings",
                ):
                    df[col] = 0.0
                elif col == "waste_level":
                    df[col] = "NONE"
                else:
                    df[col] = None
        df["monthly_cost"] = pd.to_numeric(df["monthly_cost"], errors="coerce").fillna(0).round(2)
        df["actual_cost_collected_period"] = pd.to_numeric(
            df["actual_cost_collected_period"], errors="coerce"
        ).fillna(0).round(2)
        df["estimated_monthly_cost"] = pd.to_numeric(
            df["estimated_monthly_cost"], errors="coerce"
        ).fillna(0).round(2)
        df["cpu_avg_percent"] = pd.to_numeric(df["cpu_avg_percent"], errors="coerce").fillna(0).round(2)
        df["memory_avg_percent"] = pd.to_numeric(df["memory_avg_percent"], errors="coerce").fillna(0).round(2)
        df["estimated_savings"] = pd.to_numeric(df["estimated_savings"], errors="coerce").fillna(0).round(2)
        df["waste_level"] = df["waste_level"].fillna("NONE").astype(str).str.upper()
        df["recommendation"] = df["recommendation"].fillna("").astype(str)
        return df[ENRICHED_COLUMNS]

    def _attribute_resource_costs(
        self, resources: pd.DataFrame, cost_facts: pd.DataFrame
    ) -> pd.DataFrame:
        if resources.empty or cost_facts.empty:
            return resources

        facts = cost_facts[cost_facts["resource_id"] != ""].copy()
        if facts.empty:
            return resources

        grouped = (
            facts.groupby(["resource_id", "currency"], as_index=False)["cost_amount"]
            .sum()
        )
        currency_counts = grouped.groupby("resource_id")["currency"].nunique()
        ambiguous = set(currency_counts[currency_counts > 1].index)
        lookup = (
            grouped[~grouped["resource_id"].isin(ambiguous)]
            .set_index("resource_id")
            .to_dict(orient="index")
        )
        start = pd.to_datetime(cost_facts["date"]).min()
        end = pd.to_datetime(cost_facts["date"]).max()
        observed_days = max(1, (end - start).days + 1)
        result = resources.copy()

        for index, row in result.iterrows():
            match = lookup.get(self.normalize_resource_id(row.get("resource_id", "")))
            if not match:
                continue
            actual = round(float(match["cost_amount"]), 2)
            currency = str(match["currency"]).upper()
            estimated_monthly = round(actual * 30 / observed_days, 2)
            result.at[index, "actual_cost_collected_period"] = actual
            result.at[index, "actual_cost_currency"] = currency
            result.at[index, "estimated_monthly_cost"] = estimated_monthly
            result.at[index, "estimated_cost_currency"] = currency
            result.at[index, "monthly_cost"] = estimated_monthly
            result.at[index, "cost_basis"] = (
                "actual" if observed_days >= 28 else "extrapolated"
            )
            result.at[index, "cost_estimate_method"] = (
                "cost_management_actual_period"
                if observed_days >= 28
                else f"cost_management_{observed_days}_day_x_30"
            )
            result.at[index, "cost_estimate_source"] = "Azure Cost Management"
            result.at[index, "cost_period_start"] = start.strftime("%Y-%m-%d")
            result.at[index, "cost_period_end"] = end.strftime("%Y-%m-%d")
            result.at[index, "savings_currency"] = currency
        return result

    def _resource_cost_fields(
        self,
        *,
        resource_id: Any,
        resource_group: str,
        location: str,
        estimate: float,
        estimate_currency: str,
        source_system: str,
        source_timestamp: str,
        collection_run_id: str,
    ) -> dict[str, Any]:
        return {
            "resource_id": self.normalize_resource_id(resource_id),
            "resource_group": resource_group,
            "location": location,
            "actual_cost_collected_period": 0.0,
            "actual_cost_currency": "",
            "estimated_monthly_cost": estimate,
            "estimated_cost_currency": estimate_currency,
            "cost_basis": "synthetic" if estimate else "unknown",
            "cost_period_start": None,
            "cost_period_end": None,
            "source_system": source_system,
            "source_timestamp": source_timestamp,
            "collection_run_id": collection_run_id,
        }

    @staticmethod
    def normalize_resource_id(value: Any) -> str:
        return str(value or "").strip().rstrip("/").lower()

    def _validate_schema(self, df: pd.DataFrame) -> pd.DataFrame:
        missing = [c for c in CANONICAL_COLUMNS if c not in df.columns]
        if missing:
            raise ProcessorError(f"Normalized DataFrame missing columns: {missing}")
        # Allow empty DataFrames – upstream collectors may return no resources.
        # This is expected when the Azure subscription has no resources or permissions are limited.
        # Previously we raised an error here, which broke the pipeline after disabling aggregates.
        # Instead, we log a warning and return the empty DataFrame.
        if df.empty:
            logger.warning("Normalized DataFrame is empty – no resources found.")
            return df
        if df["resource_name"].isna().any():
            raise ProcessorError("resource_name contains null values")
        return df

