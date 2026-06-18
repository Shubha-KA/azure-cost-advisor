"""Deterministic query routing for live and historical FinOps questions."""

from src.ai.inventory import is_inventory_question


def route_query(question: str) -> str:
    if is_inventory_question(question):
        return "live_inventory"
    query = question.lower()
    if any(
        term in query
        for term in (
            "current state",
            "right now",
            "currently deployed",
            "live status",
        )
    ):
        return "live_inventory"
    if any(
        term in query
        for term in ("recommend", "saving", "optimiz", "waste", "rightsize")
    ):
        return "recommendation"
    if any(
        term in query
        for term in ("histor", "last month", "trend", "previous", "over time")
    ):
        return "historical"
    return "cost_analysis"
