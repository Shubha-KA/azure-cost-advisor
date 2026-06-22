"""Per-currency cost anomaly detection from raw Cost Management facts."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.config import Settings, get_settings
from src.domain.context import OperationContext
from src.processor.normalizer import ProcessorError, RawDataLoader

logger = logging.getLogger(__name__)
ANOMALY_MULTIPLIER = 1.5


class AnomalyDetector:
    def __init__(
        self,
        settings: Settings | None = None,
        context: OperationContext | None = None,
        storage=None,
    ) -> None:
        self.settings = settings or get_settings()
        self.loader = RawDataLoader(self.settings, context, storage)

    def detect(
        self, resources_df: pd.DataFrame | None = None
    ) -> tuple[pd.DataFrame, dict]:
        daily = self._build_daily_cost_series()
        anomalies: list[dict[str, Any]] = []
        for currency, frame in daily.groupby("currency"):
            anomalies.extend(self._detect_currency_anomalies(frame, str(currency)))

        payload = {
            "detected_at": datetime.now(timezone.utc).isoformat(),
            "anomaly_count": len(anomalies),
            "rule": f"daily_cost > prior_7_day_average * {ANOMALY_MULTIPLIER}",
            "source_system": "Azure Cost Management",
            "source_timestamp": datetime.now(timezone.utc).isoformat(),
            "collection_run_id": sorted(
                daily["collection_run_id"].dropna().unique().tolist()
            )
            if not daily.empty
            else [],
            "anomalies": anomalies,
        }
        logger.info("Anomaly detection: %d anomalies found", len(anomalies))
        return resources_df if resources_df is not None else pd.DataFrame(), payload

    def _build_daily_cost_series(self) -> pd.DataFrame:
        try:
            costs = self.loader.load("costs")
        except ProcessorError as exc:
            logger.error("Cannot load costs for anomaly detection: %s", exc)
            return pd.DataFrame(
                columns=["date", "currency", "cost_amount", "collection_run_id"]
            )

        records = costs.get("records", [])
        if not records:
            return pd.DataFrame(
                columns=["date", "currency", "cost_amount", "collection_run_id"]
            )
        df = pd.DataFrame(records)
        cost_column = "costAmount" if "costAmount" in df else "costUSD"
        df["date"] = pd.to_datetime(df["date"])
        df["cost_amount"] = pd.to_numeric(df[cost_column], errors="coerce").fillna(0)
        df["currency"] = df.get(
            "currency", pd.Series("UNKNOWN", index=df.index)
        ).fillna("UNKNOWN").astype(str).str.upper()
        df["collection_run_id"] = df.get(
            "collectionRunId",
            pd.Series(
                costs.get("ingestion", {}).get("ingestionId", "legacy"),
                index=df.index,
            ),
        )
        return (
            df.groupby(["date", "currency"], as_index=False)
            .agg(
                cost_amount=("cost_amount", "sum"),
                collection_run_id=("collection_run_id", "first"),
            )
            .sort_values(["currency", "date"])
        )

    def _detect_currency_anomalies(
        self, daily: pd.DataFrame, currency: str
    ) -> list[dict[str, Any]]:
        if len(daily) < 2:
            return []
        frame = daily.sort_values("date").copy()
        anomalies: list[dict[str, Any]] = []
        for _, row in frame.iterrows():
            prior = frame[frame["date"] < row["date"]].tail(7)
            if prior.empty:
                continue
            expected = float(prior["cost_amount"].mean())
            actual = float(row["cost_amount"])
            threshold = expected * ANOMALY_MULTIPLIER
            if expected <= 0 or actual <= threshold:
                continue
            anomalies.append(
                {
                    "anomaly_type": "daily_spike",
                    "date": row["date"].strftime("%Y-%m-%d"),
                    "dimension": "subscription_total",
                    "dimension_value": "all",
                    "cost_amount": round(actual, 2),
                    "expected_cost_amount": round(expected, 2),
                    "threshold_amount": round(threshold, 2),
                    "currency": currency,
                    "anomaly": True,
                    "multiplier": round(actual / expected, 2),
                    "severity": "high" if actual > expected * 2 else "medium",
                    "description": (
                        f"Daily spend {currency} {actual:.2f} on "
                        f"{row['date'].strftime('%Y-%m-%d')} exceeds 1.5x "
                        f"the prior 7-day average {currency} {expected:.2f}."
                    ),
                    "source_system": "Azure Cost Management",
                    "source_timestamp": datetime.now(timezone.utc).isoformat(),
                    "collection_run_id": row["collection_run_id"],
                }
            )
        return anomalies

    def load_latest(self) -> dict:
        path = self.settings.processed_path / "anomalies_latest.json"
        if not path.exists():
            return {"anomalies": [], "anomaly_count": 0}
        return json.loads(path.read_text(encoding="utf-8"))
