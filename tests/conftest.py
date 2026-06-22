"""Pytest fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.config import Settings


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        AZURE_SUBSCRIPTION_ID="",
        AZURE_TENANT_ID="",
        AZURE_CLIENT_ID="",
        AZURE_CLIENT_SECRET="",
        AZURE_OPENAI_ENDPOINT="",
        AZURE_OPENAI_API_KEY="",
        DATA_RAW_DIR=str(tmp_path / "raw"),
        DATA_PROCESSED_DIR=str(tmp_path / "processed"),
        DATA_EMBEDDINGS_DIR=str(tmp_path / "embeddings"),
        COST_LOOKBACK_DAYS=14,
        ANOMALY_ZSCORE_THRESHOLD=2.0,
        WASTE_IDLE_CPU_THRESHOLD=5.0,
        WASTE_MIN_MONTHLY_COST=5.0,
    )


@pytest.fixture
def sample_costs() -> pd.DataFrame:
    import numpy as np

    dates = pd.date_range("2025-01-01", periods=14, freq="D")
    rows = []
    for d in dates:
        rows.append(
            {
                "date": d.strftime("%Y-%m-%d"),
                "resource_group": "rg-test",
                "service_name": "Virtual Machines",
                "location": "eastus",
                "cost_usd": 10.0 + np.random.default_rng(1).uniform(-1, 1),
                "usage_quantity": 50.0,
                "currency": "USD",
            }
        )
        rows.append(
            {
                "date": d.strftime("%Y-%m-%d"),
                "resource_group": "rg-test",
                "service_name": "Azure Application Gateway",
                "location": "eastus",
                "cost_usd": 5.0,
                "usage_quantity": 80.0,
                "currency": "USD",
            }
        )
    # Inject spike
    rows.append(
        {
            "date": "2025-01-10",
            "resource_group": "rg-test",
            "service_name": "Azure Databricks",
            "location": "eastus",
            "cost_usd": 200.0,
            "usage_quantity": 90.0,
            "currency": "USD",
        }
    )
    return pd.DataFrame(rows)


@pytest.fixture
def sample_usage() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "resource_group": "rg-test",
                "resource_name": "vm-idle-01",
                "service_name": "Virtual Machines",
                "avg_cpu_percent": 2.0,
                "avg_memory_percent": 15.0,
                "avg_network_mbps": 5.0,
                "hours_observed": 168,
                "sku": "Standard_D4s_v5",
            },
            {
                "resource_group": "rg-test",
                "resource_name": "appgw-01",
                "service_name": "Azure Application Gateway",
                "avg_cpu_percent": 30.0,
                "avg_memory_percent": 20.0,
                "avg_network_mbps": 10.0,
                "hours_observed": 168,
                "sku": "WAF_v2",
            },
        ]
    )
