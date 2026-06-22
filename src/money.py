"""Currency-safe money formatting and aggregation helpers."""

from __future__ import annotations

from collections.abc import Mapping
import math


def format_money(amount: float, currency: str | None) -> str:
    code = str(currency or "UNKNOWN").strip().upper()
    if code == "NAN":
        code = "UNKNOWN"
    numeric = float(amount or 0)
    if math.isnan(numeric):
        numeric = 0.0
    return f"{code} {numeric:,.2f}"


def format_money_totals(totals: Mapping[str, float]) -> str:
    return " | ".join(
        format_money(amount, currency)
        for currency, amount in sorted(totals.items())
    )
