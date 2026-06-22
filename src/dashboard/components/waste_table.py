"""Waste analysis table and filters."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.dashboard import charts
from src.dashboard.data_loader import DashboardData
from src.money import format_money


def render_waste_analysis(data: DashboardData) -> None:
    st.markdown('<p class="section-title">Waste Analysis</p>', unsafe_allow_html=True)

    if data.resources.empty:
        findings = data.waste.get("findings", [])
        if findings:
            _render_legacy_waste_table(findings)
        else:
            st.info("No waste data available. Run the pipeline to analyze resources.")
        return

    df = data.resources.copy()

    filter_col1, filter_col2, filter_col3 = st.columns(3)
    with filter_col1:
        waste_filter = st.multiselect(
            "Waste Level",
            options=sorted(df["waste_level"].unique()),
            default=[w for w in df["waste_level"].unique() if w != "NONE"] or list(df["waste_level"].unique()),
        )
    with filter_col2:
        type_filter = st.multiselect(
            "Resource Type",
            options=sorted(df["resource_type"].unique()),
            default=list(df["resource_type"].unique()),
        )
    with filter_col3:
        min_savings = st.number_input("Min Est. Savings", min_value=0.0, value=0.0, step=5.0)

    filtered = df[
        df["waste_level"].isin(waste_filter)
        & df["resource_type"].isin(type_filter)
        & (df["estimated_savings"] >= min_savings)
    ].sort_values("estimated_savings", ascending=False)

    st.caption(f"Showing {len(filtered)} of {len(df)} resources")

    display_cols = [
        "resource_name",
        "resource_type",
        "estimated_monthly_cost",
        "estimated_cost_currency",
        "cost_basis",
        "cpu_avg_percent",
        "memory_avg_percent",
        "waste_level",
        "recommendation",
        "estimated_savings",
        "savings_currency",
    ]
    styled = filtered[display_cols].copy()
    styled["estimated_monthly_cost"] = styled.apply(
        lambda row: format_money(
            row["estimated_monthly_cost"], row["estimated_cost_currency"]
        ),
        axis=1,
    )
    styled["estimated_savings"] = styled.apply(
        lambda row: format_money(
            row["estimated_savings"], row["savings_currency"]
        ),
        axis=1,
    )
    styled.columns = [c.replace("_", " ").title() for c in styled.columns]

    st.dataframe(
        styled,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Cpu Avg Percent": st.column_config.NumberColumn(format="%.1f%%"),
            "Memory Avg Percent": st.column_config.NumberColumn(format="%.1f%%"),
        },
    )

    if not filtered.empty:
        st.altair_chart(
            charts.altair_waste_stacked_bar(filtered),
            use_container_width=True,
        )


def _render_legacy_waste_table(findings: list) -> None:
    df = pd.DataFrame(findings)
    display_cols = [
        c
        for c in [
            "severity",
            "resource_group",
            "resource_name",
            "service_name",
            "category_label",
            "monthly_cost_usd",
            "estimated_monthly_savings_usd",
            "recommendation",
        ]
        if c in df.columns
    ]
    st.dataframe(df[display_cols], use_container_width=True, hide_index=True)
