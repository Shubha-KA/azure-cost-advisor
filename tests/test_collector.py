"""Tests for the collector layer."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.collector.advisor_collector import AdvisorCollector
from src.collector.aks_collector import AksCollector
from src.collector.base import CollectorError, MockDataNotFoundError, SchemaValidationError
from src.collector.cost_collector import CostCollector
from src.collector.metrics_collector import MetricsCollector
from src.collector.resource_graph_collector import ResourceGraphCollector
from src.collector.run import run_all
from src.config import Settings


def test_cost_collector_writes_timestamped_output(test_settings: Settings) -> None:
    test_settings.ensure_data_dirs()
    collector = CostCollector(test_settings)
    result = collector.collect()

    assert result.collector == "cost"
    assert result.record_count >= 1
    assert Path(result.output_path).exists()
    assert (test_settings.raw_path / "costs_latest.json").exists()

    envelope = collector.load_latest_envelope()
    assert "ingestion" in envelope
    assert envelope["ingestion"]["simulatedApi"] is True


def test_cost_collector_exports_csv(test_settings: Settings) -> None:
    collector = CostCollector(test_settings)
    collector.collect()
    csv_path = collector.export_csv()
    df = pd.read_csv(csv_path)
    assert "cost_amount" in df.columns
    assert "currency" in df.columns
    assert "resource_id" in df.columns
    assert "Virtual Machines" in df["service_name"].values


def test_metrics_collector_validates_vm_metrics(test_settings: Settings) -> None:
    collector = MetricsCollector(test_settings)
    result = collector.collect()
    assert result.record_count >= 1
    csv_path = collector.export_usage_csv()
    df = pd.read_csv(csv_path)
    assert "avg_cpu_percent" in df.columns


def test_resource_graph_collector_merges_sources(test_settings: Settings) -> None:
    collector = ResourceGraphCollector(test_settings)
    result = collector.collect()
    envelope = collector.load_latest_envelope()
    assert len(envelope["unattachedDisks"]) >= 1
    assert len(envelope["publicIps"]) >= 1
    assert envelope["summary"]["unattachedDiskCount"] >= 1


def test_advisor_collector_includes_summary(test_settings: Settings) -> None:
    collector = AdvisorCollector(test_settings)
    collector.collect()
    envelope = collector.load_latest_envelope()
    assert envelope["summary"]["totalRecommendations"] >= 1
    assert envelope["summary"]["highImpact"] >= 1


def test_aks_collector_records_clusters(test_settings: Settings) -> None:
    collector = AksCollector(test_settings)
    result = collector.collect()
    envelope = collector.load_latest_envelope()
    assert result.record_count >= 1
    assert envelope["summary"]["clusterCount"] >= 1


def test_run_all_orchestration(test_settings: Settings, monkeypatch) -> None:
    monkeypatch.chdir(test_settings.project_root)
    import src.config as config_module

    monkeypatch.setattr(config_module, "_settings", test_settings)
    report = run_all(export_csv=True, continue_on_error=True)
    assert report.success_count == 5
    assert (test_settings.raw_path / "costs_latest.csv").exists()
    assert (test_settings.raw_path / "usage_latest.csv").exists()


def test_missing_mock_file_raises(test_settings: Settings, tmp_path: Path) -> None:
    collector = CostCollector(test_settings)
    collector.mock_data_dir = tmp_path / "nonexistent"
    with pytest.raises((MockDataNotFoundError, CollectorError)):
        collector.collect()


def test_live_mode_never_uses_mock_without_credential(
    test_settings: Settings,
) -> None:
    test_settings.collection_mode = "live"
    test_settings.azure_subscription_id = ""
    test_settings.azure_tenant_id = ""
    test_settings.azure_client_id = ""
    test_settings.azure_client_secret = ""
    collector = CostCollector(test_settings)

    with pytest.raises(CollectorError, match="live collection requires"):
        collector.collect()


def test_invalid_cost_schema_rejected(test_settings: Settings, tmp_path: Path) -> None:
    mock_dir = test_settings.project_root / "tests" / "mock_data"
    backup = mock_dir / "cost_data.json.bak"
    original = mock_dir / "cost_data.json"
    backup.write_text(original.read_text(encoding="utf-8"), encoding="utf-8")

    try:
        original.write_text('{"metadata": {}, "records": []}', encoding="utf-8")
        collector = CostCollector(test_settings)
        with pytest.raises((SchemaValidationError, CollectorError)):
            collector.collect()
    finally:
        original.write_text(backup.read_text(encoding="utf-8"), encoding="utf-8")
        backup.unlink(missing_ok=True)
