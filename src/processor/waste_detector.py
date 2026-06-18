"""Apply FinOps waste detection rules to normalized resources."""

from __future__ import annotations

import logging

import pandas as pd

from src.config import Settings, get_settings

logger = logging.getLogger(__name__)

CPU_OVERSIZED_THRESHOLD = 10.0
AKS_UNDERUTILIZATION_THRESHOLD = 20.0


class WasteDetector:
    """Evaluates business rules and sets waste_level + recommendation on each resource."""

    RULES = {
        "oversized_vm": {
            "id": "oversized_vm",
            "description": "VM average CPU below 10%",
        },
        "unattached_disk": {
            "id": "unattached_disk",
            "description": "Managed disk in Unattached state",
        },
        "idle_public_ip": {
            "id": "idle_public_ip",
            "description": "Public IP not associated with a resource",
        },
        "aks_waste": {
            "id": "aks_waste",
            "description": "AKS node utilization below 20%",
        },
    }

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def detect(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            logger.warning("Waste detection received empty DataFrame")
            return df

        result = df.copy()
        result = self._apply_oversized_vm_rule(result)
        result = self._apply_unattached_disk_rule(result)
        result = self._apply_idle_public_ip_rule(result)
        result = self._apply_aks_waste_rule(result)

        waste_count = int((result["waste_level"] != "NONE").sum())
        logger.info(
            "Waste detection complete: %d / %d resources flagged",
            waste_count,
            len(result),
        )
        return result

    def _apply_oversized_vm_rule(self, df: pd.DataFrame) -> pd.DataFrame:
        mask = (df["resource_type"] == "Virtual Machine") & (
            df["telemetry_available"].fillna(False)
        ) & (
            df["cpu_avg_percent"] < CPU_OVERSIZED_THRESHOLD
        )
        df.loc[mask, "waste_level"] = "HIGH"
        df.loc[mask, "recommendation"] = (
            "Rightsize or deallocate VM — average CPU below 10%."
        )
        df.loc[mask, "rule_id"] = self.RULES["oversized_vm"]["id"]
        logger.debug("Oversized VM rule matched %d resources", mask.sum())
        return df

    def _apply_unattached_disk_rule(self, df: pd.DataFrame) -> pd.DataFrame:
        mask = df["disk_state"] == "Unattached"
        df.loc[mask, "waste_level"] = "HIGH"
        df.loc[mask, "recommendation"] = "Delete Disk"
        df.loc[mask, "rule_id"] = self.RULES["unattached_disk"]["id"]
        logger.debug("Unattached disk rule matched %d resources", mask.sum())
        return df

    def _apply_idle_public_ip_rule(self, df: pd.DataFrame) -> pd.DataFrame:
        mask = (df["resource_type"] == "Public IP Address") & (df["attached"] == False)  # noqa: E712
        df.loc[mask, "waste_level"] = "MEDIUM"
        df.loc[mask, "recommendation"] = "Delete Public IP"
        df.loc[mask, "rule_id"] = self.RULES["idle_public_ip"]["id"]
        logger.debug("Idle public IP rule matched %d resources", mask.sum())
        return df

    def _apply_aks_waste_rule(self, df: pd.DataFrame) -> pd.DataFrame:
        mask = (df["resource_type"] == "AKS Cluster") & (
            df["telemetry_available"].fillna(False)
        ) & (
            df["node_utilization"].fillna(100) < AKS_UNDERUTILIZATION_THRESHOLD
        )
        df.loc[mask, "waste_level"] = "HIGH"
        df.loc[mask, "recommendation"] = "Enable Autoscaler"
        df.loc[mask, "rule_id"] = self.RULES["aks_waste"]["id"]
        logger.debug("AKS waste rule matched %d resources", mask.sum())
        return df

    def to_findings_payload(self, df: pd.DataFrame) -> dict:
        """Convert flagged rows to legacy findings format for AI/dashboard layers."""
        flagged = df[df["waste_level"] != "NONE"].copy()
        findings = []
        for _, row in flagged.iterrows():
            findings.append(
                {
                    "resource_group": row.get("resource_group", ""),
                    "resource_name": row["resource_name"],
                    "service_name": row["resource_type"],
                    "waste_category": row.get("rule_id", "unknown"),
                    "category_label": row.get("rule_id", "unknown").replace("_", " ").title(),
                    "severity": row["waste_level"].lower(),
                    "monthly_cost": float(row["monthly_cost"]),
                    "cost_currency": row.get("estimated_cost_currency", ""),
                    "cost_basis": row.get("cost_basis", "unknown"),
                    "avg_cpu_percent": float(row["cpu_avg_percent"]),
                    "avg_memory_percent": float(row["memory_avg_percent"]),
                    "recommendation": row["recommendation"],
                    "estimated_monthly_savings": float(row["estimated_savings"]),
                    "savings_currency": row.get("savings_currency", ""),
                    "source_system": row.get("source_system", ""),
                    "source_timestamp": row.get("source_timestamp", ""),
                    "collection_run_id": row.get("collection_run_id", ""),
                }
            )
        return {
            "finding_count": len(findings),
            "total_estimated_savings": {
                currency: round(
                    sum(
                        f["estimated_monthly_savings"]
                        for f in findings
                        if f["savings_currency"] == currency
                    ),
                    2,
                )
                for currency in sorted(
                    {f["savings_currency"] for f in findings if f["savings_currency"]}
                )
            },
            "findings": findings,
        }
