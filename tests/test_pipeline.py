"""Integration test for the end-to-end pipeline."""

from __future__ import annotations

import pytest

from src.config import Settings
from src.pipeline import run_pipeline


@pytest.fixture(autouse=True)
def _reset_settings_singleton():
    import src.config as config_module

    config_module._settings = None
    yield
    config_module._settings = None


def test_pipeline_skip_ai(test_settings: Settings, monkeypatch) -> None:
    monkeypatch.chdir(test_settings.project_root)

    import src.config as config_module
    monkeypatch.setattr(config_module, "_settings", test_settings)

    result = run_pipeline(skip_ai=True)
    assert sum(result["summary"]["total_cost"].values()) > 0
    assert result["summary"]["cost_reconciliation"]["status"] == "passed"
    assert result["summary"]["cost_fact_count"] > 0
    assert (test_settings.processed_path / "cost_facts_latest.csv").exists()
    assert (test_settings.processed_path / "summary_latest.json").exists()
