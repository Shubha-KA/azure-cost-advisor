"""Estimate monthly savings for flagged waste resources."""

from __future__ import annotations

import logging

import pandas as pd

from src.config import Settings, get_settings

logger = logging.getLogger(__name__)

SAVINGS_RATES: dict[str, float] = {
    "oversized_vm": 0.55,
    "unattached_disk": 1.00,
    "idle_public_ip": 1.00,
    "aks_waste": 0.35,
}


class SavingsEstimator:
    """Computes estimated_savings based on waste rule and monthly cost."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def estimate(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df

        result = df.copy()
        flagged = result["waste_level"] != "NONE"

        for rule_id, rate in SAVINGS_RATES.items():
            mask = flagged & (result["rule_id"] == rule_id)
            result.loc[mask, "estimated_savings"] = (
                result.loc[mask, "monthly_cost"] * rate
            ).round(2)

        unmapped = flagged & (result["estimated_savings"] == 0)
        result.loc[unmapped, "estimated_savings"] = (
            result.loc[unmapped, "monthly_cost"] * 0.25
        ).round(2)

        totals = (
            result[result["savings_currency"].fillna("") != ""]
            .groupby("savings_currency")["estimated_savings"]
            .sum()
            .round(2)
            .to_dict()
            if "savings_currency" in result
            else {}
        )
        logger.info(
            "Savings estimation complete: %s total estimated monthly savings",
            totals,
        )
        return result

    @staticmethod
    def summary(df: pd.DataFrame) -> dict:
        flagged = df[df["waste_level"] != "NONE"]
        by_rule = (
            flagged.groupby("rule_id")["estimated_savings"]
            .sum()
            .round(2)
            .to_dict()
            if not flagged.empty
            else {}
        )
        totals_by_currency = (
            flagged[flagged["savings_currency"].fillna("") != ""]
            .groupby("savings_currency")["estimated_savings"]
            .sum()
            .round(2)
            .to_dict()
            if not flagged.empty and "savings_currency" in flagged
            else {}
        )
        totals_by_currency = {
            currency: amount
            for currency, amount in totals_by_currency.items()
            if amount != 0
        }
        return {
            "total_estimated_savings": totals_by_currency,
            "total_estimated_savings_usd": totals_by_currency.get("USD", 0.0),
            "waste_resource_count": int((df["waste_level"] != "NONE").sum()),
            "savings_by_rule": by_rule,
        }
