"""Cost anomaly display panel."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.dashboard.data_loader import DashboardData


def render_anomaly_panel(data: DashboardData) -> None:
    st.markdown('<p class="section-title">Cost Anomalies</p>', unsafe_allow_html=True)

    anomalies = data.anomalies.get("anomalies", [])
    if not anomalies:
        st.success("No cost anomalies detected in the current billing period.")
        return

    df = pd.DataFrame(anomalies)
    st.caption(data.anomalies.get("rule", "today_cost > average_7_day_cost × 1.5"))

    col1, col2 = st.columns([2, 1])
    with col1:
        st.dataframe(df, use_container_width=True, hide_index=True)
    with col2:
        if "cost_amount" in df.columns and "expected_cost_amount" in df.columns:
            fig = go.Figure()
            fig.add_trace(
                go.Bar(
                    name="Actual",
                    x=df["date"],
                    y=df["cost_amount"],
                    text=df["currency"],
                    marker_color="#dc2626",
                )
            )
            fig.add_trace(
                go.Bar(
                    name="Expected",
                    x=df["date"],
                    y=df["expected_cost_amount"],
                    text=df["currency"],
                    marker_color="#94a3b8",
                )
            )
            fig.update_layout(
                title="Anomaly vs Expected",
                barmode="group",
                height=300,
                template="plotly_white",
                margin=dict(l=20, r=20, t=40, b=20),
            )
            st.plotly_chart(fig, use_container_width=True)

    for item in anomalies[:5]:
        severity = item.get("severity", "medium")
        st.warning(f"**{item.get('date', '')}** — {item.get('description', '')}")
