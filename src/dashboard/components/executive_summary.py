"""Executive summary KPIs and overview charts."""

from __future__ import annotations

import streamlit as st

from src.dashboard import charts
from src.dashboard.data_loader import DashboardData
from src.money import format_money_totals


def render_executive_summary(data: DashboardData) -> None:
    st.markdown('<p class="section-title">Executive Summary</p>', unsafe_allow_html=True)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric(
        "Total Cost (Collected Period)",
        format_money_totals(data.total_costs) or "N/A",
        help="Azure Cost Management spend for the collected lookback period",
    )
    col2.metric(
        "Est. Monthly Savings",
        format_money_totals(data.savings_totals) or "N/A",
        delta=None,
        delta_color="inverse",
    )
    col3.metric(
        "Cost Anomalies",
        data.anomaly_count,
        help="Days where spend exceeded 1.5× the 7-day rolling average",
    )
    waste_count = int((data.resources["waste_level"] != "NONE").sum()) if not data.resources.empty else 0
    col4.metric(
        "Waste Resources",
        waste_count,
        help="Resources flagged with HIGH, MEDIUM, or LOW waste level",
    )

    st.markdown("")

    chart_left, chart_right = st.columns(2)
    with chart_left:
        st.plotly_chart(
            charts.plotly_daily_cost_trend(data.daily_costs),
            use_container_width=True,
        )
    with chart_right:
        st.plotly_chart(
            charts.plotly_waste_distribution(data.resources),
            use_container_width=True,
        )

    chart_row2_left, chart_row2_right = st.columns(2)
    with chart_row2_left:
        st.plotly_chart(
            charts.plotly_service_breakdown(data.service_costs),
            use_container_width=True,
        )
    with chart_row2_right:
        st.plotly_chart(
            charts.plotly_savings_by_resource(data.resources),
            use_container_width=True,
        )

    if not data.daily_costs.empty:
        st.altair_chart(
            charts.altair_cost_area(data.daily_costs),
            use_container_width=True,
        )
