"""Load raw collector JSON and normalize into a unified Pandas DataFrame."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from src.config import Settings, get_settings
from src.processor.schemas import CANONICAL_COLUMNS, ENRICHED_COLUMNS, RAW_FILE_MAP

logger = logging.getLogger(__name__)


class ProcessorError(Exception):
    """Raised when processor normalization fails."""


class RawDataLoader:
    """Reads latest JSON envelopes from data/raw/."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.raw_path = self.settings.raw_path

    def load(self, key: str) -> dict[str, Any]:
        filename = RAW_FILE_MAP.get(key)
        if not filename:
            raise ProcessorError(f"Unknown raw data key: {key}")
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
            if path.exists():
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

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.loader = RawDataLoader(self.settings)

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
        if "costs" in payloads:
            frames.append(self._normalize_other_costs(payloads["costs"]))

        if not frames:
            raise ProcessorError("No records produced during normalization")

        df = pd.concat(frames, ignore_index=True)
        df = self._apply_defaults(df)
        df = self._validate_schema(df)
        logger.info("Normalized %d resources across %d types", len(df), df["resource_type"].nunique())
        return df

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
            cpu = float(res.get("metrics", {}).get("Percentage CPU", {}).get("average", 0))
            mem_bytes = float(
                res.get("metrics", {}).get("Available Memory Bytes", {}).get("average", 0)
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
                    "resource_name": name,
                    "resource_type": "Virtual Machine",
                    "resource_group": rg,
                    "monthly_cost": allocated_cost,
                    "cpu_avg_percent": round(cpu, 2),
                    "memory_avg_percent": round(mem_pct, 2),
                    "waste_level": "NONE",
                    "recommendation": "",
                    "estimated_savings": 0.0,
                    "disk_state": None,
                    "attached": None,
                    "node_utilization": None,
                    "anomaly": False,
                    "rule_id": None,
                }
            )
        return pd.DataFrame(rows)

    @staticmethod
    def _build_vm_cost_lookup(costs: dict[str, Any]) -> dict[tuple[str, str], float]:
        records = costs.get("records", [])
        if not records:
            return {}
        df = pd.DataFrame(records)
        grouped = (
            df.groupby(["resourceGroup", "serviceName"])["costUSD"]
            .sum()
            .to_dict()
        )
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
                    "resource_name": disk.get("diskName", "unknown-disk"),
                    "resource_type": "Managed Disk",
                    "resource_group": disk.get("resourceGroup", ""),
                    "monthly_cost": float(disk.get("monthlyCostEstimateUsd", 0)),
                    "cpu_avg_percent": 0.0,
                    "memory_avg_percent": 0.0,
                    "waste_level": "NONE",
                    "recommendation": "",
                    "estimated_savings": 0.0,
                    "disk_state": "Unattached",
                    "attached": None,
                    "node_utilization": None,
                    "anomaly": False,
                    "rule_id": None,
                }
            )
        return pd.DataFrame(rows)

    def _normalize_public_ips(self, graph: dict[str, Any]) -> pd.DataFrame:
        ips = graph.get("publicIps", [])
        rows = []
        for ip in ips:
            rows.append(
                {
                    "resource_name": ip.get("name", "unknown-pip"),
                    "resource_type": "Public IP Address",
                    "resource_group": ip.get("resourceGroup", ""),
                    "monthly_cost": float(ip.get("monthlyCostEstimateUsd", 0)),
                    "cpu_avg_percent": 0.0,
                    "memory_avg_percent": 0.0,
                    "waste_level": "NONE",
                    "recommendation": "",
                    "estimated_savings": 0.0,
                    "disk_state": None,
                    "attached": bool(ip.get("associated", False)),
                    "node_utilization": None,
                    "anomaly": False,
                    "rule_id": None,
                }
            )
        return pd.DataFrame(rows)

    def _normalize_aks(self, aks: dict[str, Any]) -> pd.DataFrame:
        clusters = aks.get("clusters", [])
        rows = []
        for cluster in clusters:
            util = float(cluster.get("metrics", {}).get("cpuUtilizationPercent", 0))
            rows.append(
                {
                    "resource_name": cluster.get("clusterName", "unknown-aks"),
                    "resource_type": "AKS Cluster",
                    "resource_group": cluster.get("resourceGroup", ""),
                    "monthly_cost": float(cluster.get("monthlyCostEstimateUsd", 0)),
                    "cpu_avg_percent": util,
                    "memory_avg_percent": float(
                        cluster.get("metrics", {}).get("memoryUtilizationPercent", 0)
                    ),
                    "waste_level": "NONE",
                    "recommendation": "",
                    "estimated_savings": 0.0,
                    "disk_state": None,
                    "attached": None,
                    "node_utilization": util,
                    "anomaly": False,
                    "rule_id": None,
                }
            )
        return pd.DataFrame(rows)

    def _normalize_other_costs(self, costs: dict[str, Any]) -> pd.DataFrame:
        """Skip creation of aggregate cost rows. Returns an empty DataFrame.
        The cost aggregation is handled elsewhere (e.g., reporting layer)."""
        # Previously this method generated synthetic "*-aggregate" resources for services like
        # Azure App Service, DNS, etc. Those rows were confusing because they appear as real
        # resources in the dashboard. By returning an empty DataFrame we avoid polluting the
        # resource list with placeholder entries.
        return pd.DataFrame()

    def _apply_defaults(self, df: pd.DataFrame) -> pd.DataFrame:
        for col in ENRICHED_COLUMNS:
            if col not in df.columns:
                if col == "anomaly":
                    df[col] = False
                elif col in ("cpu_avg_percent", "memory_avg_percent", "monthly_cost", "estimated_savings"):
                    df[col] = 0.0
                elif col == "waste_level":
                    df[col] = "NONE"
                else:
                    df[col] = None
        df["monthly_cost"] = pd.to_numeric(df["monthly_cost"], errors="coerce").fillna(0).round(2)
        df["cpu_avg_percent"] = pd.to_numeric(df["cpu_avg_percent"], errors="coerce").fillna(0).round(2)
        df["memory_avg_percent"] = pd.to_numeric(df["memory_avg_percent"], errors="coerce").fillna(0).round(2)
        df["estimated_savings"] = pd.to_numeric(df["estimated_savings"], errors="coerce").fillna(0).round(2)
        df["waste_level"] = df["waste_level"].fillna("NONE").astype(str).str.upper()
        df["recommendation"] = df["recommendation"].fillna("").astype(str)
        return df[ENRICHED_COLUMNS]

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

