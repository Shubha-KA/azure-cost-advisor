"""Cost anomaly detection from raw cost time series."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.config import Settings, get_settings
from src.processor.normalizer import ProcessorError, RawDataLoader

logger = logging.getLogger(__name__)

ANOMALY_MULTIPLIER = 1.5


class AnomalyDetector:
    """
    Flags cost anomalies when:
        today_cost > average_7_day_cost * 1.5
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.loader = RawDataLoader(self.settings)

    def detect(self, resources_df: pd.DataFrame | None = None) -> tuple[pd.DataFrame, dict]:
        daily = self._build_daily_cost_series()
        anomalies = self._detect_daily_anomalies(daily)
        payload = self._build_payload(anomalies)

        if resources_df is not None and not resources_df.empty and anomalies:
            resources_df = self._flag_resource_anomalies(resources_df, daily, anomalies)

        logger.info("Anomaly detection: %d anomalies found", len(anomalies))
        return resources_df if resources_df is not None else pd.DataFrame(), payload

    def _build_daily_cost_series(self) -> pd.DataFrame:
        try:
            costs = self.loader.load("costs")
        except ProcessorError as exc:
            logger.error("Cannot load costs for anomaly detection: %s", exc)
            return pd.DataFrame(columns=["date", "daily_cost"])

        records = costs.get("records", [])
        if not records:
            return pd.DataFrame(columns=["date", "daily_cost"])

        df = pd.DataFrame(records)
        df["date"] = pd.to_datetime(df["date"])
        df["costUSD"] = pd.to_numeric(df["costUSD"], errors="coerce").fillna(0)
        daily = (
            df.groupby("date")["costUSD"]
            .sum()
            .reset_index()
            .rename(columns={"costUSD": "daily_cost"})
            .sort_values("date")
        )
        return daily

    def _detect_daily_anomalies(self, daily: pd.DataFrame) -> list[dict[str, Any]]:
        if len(daily) < 2:
            logger.warning("Insufficient daily cost data for anomaly detection")
            return []

        daily = daily.copy()
        daily["rolling_7d_avg"] = (
            daily["daily_cost"].rolling(window=7, min_periods=1).mean().shift(1)
        )
        latest = daily.iloc[-1]
        today_cost = float(latest["daily_cost"])
        avg_7d = float(latest["rolling_7d_avg"]) if pd.notna(latest["rolling_7d_avg"]) else float(
            daily["daily_cost"].iloc[:-1].mean() if len(daily) > 1 else today_cost
        )

        anomalies: list[dict[str, Any]] = []
        threshold = avg_7d * ANOMALY_MULTIPLIER

        if today_cost > threshold and avg_7d > 0:
            anomalies.append(
                {
                    "anomaly_type": "daily_spike",
                    "date": latest["date"].strftime("%Y-%m-%d"),
                    "dimension": "subscription_total",
                    "dimension_value": "all",
                    "cost_usd": round(today_cost, 2),
                    "expected_cost_usd": round(avg_7d, 2),
                    "threshold_usd": round(threshold, 2),
                    "anomaly": True,
                    "multiplier": round(today_cost / avg_7d, 2),
                    "severity": "high" if today_cost > avg_7d * 2 else "medium",
                    "description": (
                        f"Daily spend ${today_cost:.2f} exceeds 1.5× the 7-day average "
                        f"${avg_7d:.2f} (threshold ${threshold:.2f})."
                    ),
                }
            )

        for _, row in daily.iloc[:-1].iterrows():
            prior = daily[daily["date"] < row["date"]].tail(7)
            if prior.empty:
                continue
            avg_prior = float(prior["daily_cost"].mean())
            day_cost = float(row["daily_cost"])
            if avg_prior > 0 and day_cost > avg_prior * ANOMALY_MULTIPLIER:
                anomalies.append(
                    {
                        "anomaly_type": "daily_spike",
                        "date": row["date"].strftime("%Y-%m-%d"),
                        "dimension": "subscription_total",
                        "dimension_value": "all",
                        "cost_usd": round(day_cost, 2),
                        "expected_cost_usd": round(avg_prior, 2),
                        "threshold_usd": round(avg_prior * ANOMALY_MULTIPLIER, 2),
                        "anomaly": True,
                        "multiplier": round(day_cost / avg_prior, 2),
                        "severity": "high" if day_cost > avg_prior * 2 else "medium",
                        "description": (
                            f"Daily spend ${day_cost:.2f} on {row['date'].strftime('%Y-%m-%d')} "
                            f"exceeds 1.5× prior 7-day average ${avg_prior:.2f}."
                        ),
                    }
                )

        return anomalies

    def _flag_resource_anomalies(
        self,
        resources_df: pd.DataFrame,
        daily: pd.DataFrame,
        anomalies: list[dict[str, Any]],
    ) -> pd.DataFrame:
        if not anomalies:
            return resources_df
        anomaly_dates = {a["date"] for a in anomalies}
        if daily.empty:
            return resources_df
        latest_date = daily["date"].max().strftime("%Y-%m-%d")
        if latest_date in anomaly_dates:
            resources_df = resources_df.copy()
            resources_df.loc[resources_df["monthly_cost"] > 0, "anomaly"] = True
        return resources_df

    def _build_payload(self, anomalies: list[dict[str, Any]]) -> dict:
        return {
            "detected_at": datetime.now(timezone.utc).isoformat(),
            "anomaly_count": len(anomalies),
            "rule": f"today_cost > average_7_day_cost * {ANOMALY_MULTIPLIER}",
            "anomalies": anomalies,
        }

    def load_latest(self) -> dict:
        path = self.settings.processed_path / "anomalies_latest.json"
        if not path.exists():
            return {"anomalies": [], "anomaly_count": 0}
        return json.loads(path.read_text(encoding="utf-8"))
