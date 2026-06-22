"""Canonical processor schema definitions."""

from __future__ import annotations

CANONICAL_COLUMNS = [
    "tenant_id",
    "subscription_id",
    "collection_run_id",
    "processing_run_id",
    "correlation_id",
    "schema_version",
    "resource_id",
    "resource_name",
    "resource_type",
    "resource_group",
    "location",
    "actual_cost_collected_period",
    "actual_cost_currency",
    "estimated_monthly_cost",
    "estimated_cost_currency",
    "cost_basis",
    "cost_period_start",
    "cost_period_end",
    "monthly_cost",
    "cpu_avg_percent",
    "memory_avg_percent",
    "waste_level",
    "recommendation",
    "estimated_savings",
    "savings_currency",
    "source_system",
    "source_timestamp",
    "telemetry_available",
]

ENRICHED_COLUMNS = CANONICAL_COLUMNS + [
    "disk_state",
    "attached",
    "node_utilization",
    "anomaly",
    "rule_id",
    "cost_estimate_method",
    "cost_estimate_source",
]

COST_FACT_COLUMNS = [
    "tenant_id",
    "subscription_id",
    "collection_run_id",
    "processing_run_id",
    "correlation_id",
    "schema_version",
    "date",
    "resource_id",
    "resource_group",
    "service_name",
    "location",
    "cost_amount",
    "usage_quantity",
    "currency",
    "source_system",
    "source_timestamp",
]

WASTE_LEVELS = ("NONE", "LOW", "MEDIUM", "HIGH")

RAW_FILE_MAP = {
    "costs": "costs_latest.json",
    "vm_metrics": "vm_metrics_latest.json",
    "resource_graph": "resource_graph_latest.json",
    "aks_metrics": "aks_metrics_latest.json",
    "advisor": "advisor_latest.json",
}
