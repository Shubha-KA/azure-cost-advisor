"""Tests for the AI layer (rule-based mode — no Azure OpenAI required)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.ai.advisor import FinOpsAdvisor
from src.ai.prompts import EXAMPLE_QUESTIONS
from src.config import Settings


@pytest.fixture
def processed_fixtures(test_settings: Settings) -> Path:
    """Seed minimal processed data for rule-based advisor tests."""
    proc = test_settings.processed_path
    proc.mkdir(parents=True, exist_ok=True)

    resources = pd.DataFrame(
        [
            {
                "resource_name": "vm-legacy-01",
                "resource_type": "Virtual Machine",
                "monthly_cost": 285.0,
                "cpu_avg_percent": 2.5,
                "memory_avg_percent": 15.0,
                "waste_level": "HIGH",
                "recommendation": "Resize or deallocate VM",
                "estimated_savings": 120.0,
            },
            {
                "resource_name": "disk-orphan",
                "resource_type": "Managed Disk",
                "monthly_cost": 38.5,
                "cpu_avg_percent": 0.0,
                "memory_avg_percent": 0.0,
                "waste_level": "HIGH",
                "recommendation": "Delete Disk",
                "estimated_savings": 38.5,
            },
        ]
    )
    resources.to_csv(proc / "resources_latest.csv", index=False)

    waste = {
        "findings": [
            {
                "severity": "high",
                "category_label": "Oversized Vm",
                "resource_group": "rg-legacy",
                "resource_name": "vm-legacy-01",
                "service_name": "Virtual Machine",
                "estimated_monthly_savings_usd": 120,
                "recommendation": "Resize VM",
                "avg_cpu_percent": 2.5,
            }
        ],
        "total_estimated_savings_usd": 158.5,
    }
    (proc / "waste_findings_latest.json").write_text(
        json.dumps(waste), encoding="utf-8"
    )

    anomalies = {
        "anomaly_count": 1,
        "anomalies": [
            {
                "date": "2025-05-10",
                "description": "Daily spend exceeded 7-day average",
                "cost_usd": 210.5,
                "expected_cost_usd": 95.0,
                "severity": "high",
            }
        ],
    }
    (proc / "anomalies_latest.json").write_text(
        json.dumps(anomalies), encoding="utf-8"
    )

    summary = {
        "total_cost_usd": 2500.0,
        "total_estimated_savings_usd": 158.5,
        "period_start": "2025-05-01",
        "period_end": "2025-05-14",
    }
    (proc / "summary_latest.json").write_text(
        json.dumps(summary), encoding="utf-8"
    )
    return proc


def test_rule_based_vm_waste_question(
    test_settings: Settings, processed_fixtures: Path
) -> None:
    advisor = FinOpsAdvisor(test_settings)
    answer = advisor.ask("Which VM wastes the most money?")
    assert "vm-legacy-01" in answer or "oversized" in answer.lower()
    assert "Recommendation:" in answer
    assert "savings" in answer.lower()


def test_rule_based_spike_question(
    test_settings: Settings, processed_fixtures: Path
) -> None:
    advisor = FinOpsAdvisor(test_settings)
    answer = advisor.ask("Why did costs spike?")
    assert "spike" in answer.lower() or "2025-05-10" in answer


def test_rule_based_savings_question(
    test_settings: Settings, processed_fixtures: Path
) -> None:
    advisor = FinOpsAdvisor(test_settings)
    answer = advisor.ask("What are my biggest savings opportunities?")
    assert "savings" in answer.lower()
    assert "USD" in answer


def test_rule_based_recommendations(
    test_settings: Settings, processed_fixtures: Path
) -> None:
    advisor = FinOpsAdvisor(test_settings)
    result = advisor.generate_recommendations()
    assert result["source"] == "rule_based"
    assert "vm-legacy-01" in result["recommendations"]


def test_example_questions_defined() -> None:
    assert len(EXAMPLE_QUESTIONS) >= 3
