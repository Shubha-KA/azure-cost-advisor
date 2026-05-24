"""Canonical processor schema definitions."""

from __future__ import annotations

CANONICAL_COLUMNS = [
    "resource_name",
    "resource_type",
    "monthly_cost",
    "cpu_avg_percent",
    "memory_avg_percent",
    "waste_level",
    "recommendation",
    "estimated_savings",
]

ENRICHED_COLUMNS = CANONICAL_COLUMNS + [
    "resource_group",
    "disk_state",
    "attached",
    "node_utilization",
    "anomaly",
    "rule_id",
]

WASTE_LEVELS = ("NONE", "LOW", "MEDIUM", "HIGH")

RAW_FILE_MAP = {
    "costs": "costs_latest.json",
    "vm_metrics": "vm_metrics_latest.json",
    "resource_graph": "resource_graph_latest.json",
    "aks_metrics": "aks_metrics_latest.json",
    "advisor": "advisor_latest.json",
}
