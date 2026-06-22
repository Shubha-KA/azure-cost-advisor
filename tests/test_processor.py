"""Tests for the processor layer."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.collector.run import run_all
from src.config import Settings
from src.dashboard.data_loader import DashboardDataLoader
from src.processor.anomaly_detector import AnomalyDetector
from src.processor.normalizer import DataNormalizer, ProcessorError
from src.processor.report_generator import ReportGenerator
from src.domain.context import OperationContext
from src.processor.run import _reconcile_costs, _resource_fact_document, run_processing
from src.processor.savings_estimator import SavingsEstimator
from src.processor.schemas import CANONICAL_COLUMNS, COST_FACT_COLUMNS
from src.processor.waste_detector import WasteDetector


@pytest.fixture
def seeded_raw_data(test_settings: Settings) -> Path:
    """Copy project mock data through collectors into test_settings raw path."""
    mock_src = test_settings.project_root / "tests" / "mock_data"
    if not mock_src.exists():
        pytest.skip("Mock data directory not found")

    import src.config as config_module
    config_module._settings = test_settings
    run_all(export_csv=True, continue_on_error=True)
    return test_settings.raw_path


def test_normalizer_produces_canonical_schema(
    test_settings: Settings, seeded_raw_data: Path
) -> None:
    df = DataNormalizer(test_settings).normalize()
    for col in CANONICAL_COLUMNS:
        assert col in df.columns
    assert len(df) >= 1


def test_cost_normalizer_preserves_all_records(
    test_settings: Settings, seeded_raw_data: Path
) -> None:
    normalizer = DataNormalizer(test_settings)
    payload = normalizer.loader.load("costs")
    facts = normalizer.normalize_cost_facts(payload)

    assert list(facts.columns) == COST_FACT_COLUMNS
    assert len(facts) == len(payload["records"])
    assert facts["cost_amount"].sum() == pytest.approx(
        sum(
            record.get("costAmount", record.get("costUSD", 0))
            for record in payload["records"]
        )
    )


def test_oversized_vm_rule(test_settings: Settings, seeded_raw_data: Path) -> None:
    df = DataNormalizer(test_settings).normalize()
    df = WasteDetector(test_settings).detect(df)
    idle_vms = df[
        (df["resource_type"] == "Virtual Machine") & (df["cpu_avg_percent"] < 10)
    ]
    assert len(idle_vms) >= 1
    assert (idle_vms["waste_level"] == "HIGH").all()
    assert (idle_vms["recommendation"].str.len() > 0).all()


def test_unattached_disk_rule(test_settings: Settings, seeded_raw_data: Path) -> None:
    df = DataNormalizer(test_settings).normalize()
    df = WasteDetector(test_settings).detect(df)
    disks = df[df["disk_state"] == "Unattached"]
    assert len(disks) >= 1
    assert (disks["recommendation"] == "Delete Disk").all()


def test_idle_public_ip_rule(test_settings: Settings, seeded_raw_data: Path) -> None:
    df = DataNormalizer(test_settings).normalize()
    df = WasteDetector(test_settings).detect(df)
    ips = df[(df["resource_type"] == "Public IP Address") & (df["attached"] == False)]  # noqa: E712
    assert len(ips) >= 1
    assert (ips["recommendation"] == "Delete Public IP").all()


def test_resource_fact_attributes_only_include_utilization_for_compute() -> None:
    context = OperationContext.create("tenant-a", "subscription-a")
    public_ip = _resource_fact_document(
        {
            "resource_id": "/subscriptions/a/resourceGroups/rg/providers/Microsoft.Network/publicIPAddresses/pip-a",
            "resource_name": "pip-a",
            "resource_type": "Public IP Address",
            "resource_group": "rg",
            "cpu_avg_percent": 0.0,
            "memory_avg_percent": 0.0,
            "node_utilization": None,
            "source_system": "Azure Resource Graph",
            "source_timestamp": "2026-06-01T00:00:00Z",
        },
        context,
    )
    vm = _resource_fact_document(
        {
            "resource_id": "/subscriptions/a/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-a",
            "resource_name": "vm-a",
            "resource_type": "Virtual Machine",
            "resource_group": "rg",
            "cpu_avg_percent": 2.0,
            "memory_avg_percent": 12.0,
            "node_utilization": None,
            "source_system": "Azure Monitor",
            "source_timestamp": "2026-06-01T00:00:00Z",
        },
        context,
    )

    assert "cpu_avg_percent" not in public_ip["attributes"]
    assert "memory_avg_percent" not in public_ip["attributes"]
    assert vm["attributes"]["cpu_avg_percent"] == 2.0
    assert vm["attributes"]["memory_avg_percent"] == 12.0


def test_aks_waste_rule(test_settings: Settings, seeded_raw_data: Path) -> None:
    df = DataNormalizer(test_settings).normalize()
    df = WasteDetector(test_settings).detect(df)
    aks = df[
        (df["resource_type"] == "AKS Cluster")
        & (df["node_utilization"].fillna(100) < 20)
    ]
    assert len(aks) >= 1
    assert (aks["recommendation"] == "Enable Autoscaler").all()


def test_anomaly_detection(test_settings: Settings, seeded_raw_data: Path) -> None:
    _, payload = AnomalyDetector(test_settings).detect()
    assert "anomalies" in payload
    assert payload.get("anomaly_count", 0) >= 0


def test_savings_estimator(test_settings: Settings, seeded_raw_data: Path) -> None:
    df = DataNormalizer(test_settings).normalize()
    df = WasteDetector(test_settings).detect(df)
    df = SavingsEstimator(test_settings).estimate(df)
    flagged = df[df["waste_level"] != "NONE"]
    assert (flagged["estimated_savings"] > 0).all()


def test_run_processing_exports(test_settings: Settings, seeded_raw_data: Path) -> None:
    import src.config as config_module

    config_module._settings = test_settings
    _, report = run_processing()
    assert report.resource_count >= 1
    assert report.raw_cost_record_count == report.cost_fact_count
    assert report.raw_totals == report.processed_totals
    assert report.processed_totals == report.summary_totals
    assert report.reconciliation_status == "passed"
    assert (test_settings.processed_path / "resources_latest.csv").exists()
    assert (test_settings.processed_path / "resources_latest.json").exists()
    assert (test_settings.processed_path / "cost_facts_latest.csv").exists()
    assert (test_settings.processed_path / "cost_facts_latest.json").exists()
    assert (test_settings.processed_path / "summary_latest.json").exists()
    assert (test_settings.processed_path / "report_latest.md").exists()

    dashboard = DashboardDataLoader(test_settings).load()
    assert len(dashboard.cost_facts) == report.cost_fact_count
    assert dashboard.total_costs == report.summary_totals
    assert dashboard.savings_totals == report.total_estimated_savings


def test_live_cost_records_cannot_normalize_to_empty() -> None:
    payload = {
        "metadata": {"source": "live"},
        "records": [{"costUSD": 12.5}],
    }
    empty_facts = pd.DataFrame(columns=COST_FACT_COLUMNS)

    with pytest.raises(
        ProcessorError,
        match="Live Cost Management records exist but processed cost facts are empty",
    ):
        _reconcile_costs(payload, empty_facts)


def test_reconciliation_keeps_currency_totals_separate() -> None:
    payload = {
        "metadata": {"source": "live"},
        "records": [
            {"costAmount": 10, "currency": "USD"},
            {"costAmount": 20, "currency": "INR"},
        ],
    }
    facts = pd.DataFrame(
        [
            {"cost_amount": 10, "currency": "USD"},
            {"cost_amount": 20, "currency": "INR"},
        ]
    )
    result = _reconcile_costs(payload, facts)
    assert result["processed_totals"] == {"INR": 20, "USD": 10}


def test_missing_raw_raises(test_settings: Settings, tmp_path: Path) -> None:
    empty_raw = tmp_path / "raw"
    empty_raw.mkdir()
    test_settings.data_raw_dir = str(empty_raw)
    with pytest.raises(ProcessorError):
        DataNormalizer(test_settings).normalize()
