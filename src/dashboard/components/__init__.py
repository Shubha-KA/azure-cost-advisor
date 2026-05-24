"""Dashboard UI components."""

from src.dashboard.components.anomaly_panel import render_anomaly_panel
from src.dashboard.components.executive_summary import render_executive_summary
from src.dashboard.components.recommendation_cards import render_recommendation_cards
from src.dashboard.components.waste_table import render_waste_analysis

__all__ = [
    "render_anomaly_panel",
    "render_executive_summary",
    "render_recommendation_cards",
    "render_waste_analysis",
]
