"""Plotly and Altair chart builders for the FinOps dashboard."""

from __future__ import annotations

import altair as alt
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# Brand palette — Azure-inspired
COLORS = {
    "primary": "#0078d4",
    "secondary": "#005a9e",
    "success": "#107c10",
    "warning": "#ff8c00",
    "danger": "#d13438",
    "muted": "#64748b",
}

WASTE_COLORS = {
    "HIGH": "#dc2626",
    "MEDIUM": "#f59e0b",
    "LOW": "#10b981",
    "NONE": "#94a3b8",
}

PLOTLY_TEMPLATE = "plotly_white"


def plotly_daily_cost_trend(daily_costs: pd.DataFrame) -> go.Figure:
    if daily_costs.empty:
        fig = go.Figure()
        fig.update_layout(
            title="Daily Cost Trend",
            annotations=[{"text": "No cost data", "showarrow": False, "font": {"size": 14}}],
            height=380,
            template=PLOTLY_TEMPLATE,
        )
        return fig

    df = daily_costs.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["rolling_7d"] = df["daily_cost"].rolling(window=7, min_periods=1).mean()

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df["date"],
            y=df["daily_cost"],
            name="Daily Cost",
            mode="lines+markers",
            line=dict(color=COLORS["primary"], width=2),
            marker=dict(size=6),
            fill="tozeroy",
            fillcolor="rgba(0, 120, 212, 0.08)",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=df["date"],
            y=df["rolling_7d"],
            name="7-Day Avg",
            mode="lines",
            line=dict(color=COLORS["warning"], width=2, dash="dash"),
        )
    )
    fig.update_layout(
        title="Daily Azure Spend Trend",
        xaxis_title="Date",
        yaxis_title="Cost (USD)",
        hovermode="x unified",
        height=380,
        template=PLOTLY_TEMPLATE,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=40, r=20, t=60, b=40),
    )
    return fig


def plotly_service_breakdown(service_costs: pd.DataFrame) -> go.Figure:
    if service_costs.empty:
        fig = go.Figure()
        fig.update_layout(title="Top Services by Cost", height=380, template=PLOTLY_TEMPLATE)
        return fig

    df = service_costs.head(10).copy()
    name_col = "service_name" if "service_name" in df.columns else df.columns[0]
    cost_col = "cost_usd" if "cost_usd" in df.columns else "monthly_cost"

    fig = px.bar(
        df,
        x=cost_col,
        y=name_col,
        orientation="h",
        title="Top Services by Cost",
        labels={cost_col: "Cost (USD)", name_col: "Service"},
        color=cost_col,
        color_continuous_scale=["#cce4f7", "#0078d4"],
    )
    fig.update_layout(
        height=380,
        template=PLOTLY_TEMPLATE,
        showlegend=False,
        coloraxis_showscale=False,
        margin=dict(l=40, r=20, t=60, b=40),
    )
    return fig


def plotly_waste_distribution(resources: pd.DataFrame) -> go.Figure:
    if resources.empty or "waste_level" not in resources.columns:
        fig = go.Figure()
        fig.update_layout(title="Waste Level Distribution", height=320, template=PLOTLY_TEMPLATE)
        return fig

    counts = resources["waste_level"].value_counts().reset_index()
    counts.columns = ["waste_level", "count"]
    colors = [WASTE_COLORS.get(w, COLORS["muted"]) for w in counts["waste_level"]]

    fig = go.Figure(
        data=[
            go.Pie(
                labels=counts["waste_level"],
                values=counts["count"],
                hole=0.45,
                marker=dict(colors=colors),
                textinfo="label+percent",
                textposition="outside",
            )
        ]
    )
    fig.update_layout(
        title="Waste Level Distribution",
        height=320,
        template=PLOTLY_TEMPLATE,
        margin=dict(l=20, r=20, t=50, b=20),
    )
    return fig


def plotly_savings_by_resource(resources: pd.DataFrame) -> go.Figure:
    if resources.empty:
        fig = go.Figure()
        fig.update_layout(title="Estimated Savings by Resource", height=320, template=PLOTLY_TEMPLATE)
        return fig

    flagged = resources[resources["estimated_savings"] > 0].copy()
    if flagged.empty:
        flagged = resources.nlargest(8, "monthly_cost")

    flagged = flagged.nlargest(10, "estimated_savings")
    fig = px.bar(
        flagged,
        x="estimated_savings",
        y="resource_name",
        orientation="h",
        color="waste_level",
        color_discrete_map=WASTE_COLORS,
        title="Top Estimated Savings by Resource",
        labels={"estimated_savings": "Est. Savings (USD/mo)", "resource_name": "Resource"},
    )
    fig.update_layout(
        height=320,
        template=PLOTLY_TEMPLATE,
        margin=dict(l=40, r=20, t=50, b=40),
    )
    return fig


def altair_cost_area(daily_costs: pd.DataFrame) -> alt.Chart:
    if daily_costs.empty:
        return (
            alt.Chart(pd.DataFrame({"date": [], "daily_cost": []}))
            .mark_text(text="No data")
            .properties(title="Cost Trend (Altair)", height=280)
        )

    df = daily_costs.copy()
    df["date"] = pd.to_datetime(df["date"])

    area = (
        alt.Chart(df)
        .mark_area(opacity=0.4, color=COLORS["primary"])
        .encode(
            x=alt.X("date:T", title="Date"),
            y=alt.Y("daily_cost:Q", title="Daily Cost (USD)", stack=None),
            tooltip=[
                alt.Tooltip("date:T", title="Date"),
                alt.Tooltip("daily_cost:Q", title="Cost", format="$,.2f"),
            ],
        )
    )
    line = (
        alt.Chart(df)
        .mark_line(color=COLORS["secondary"], strokeWidth=2)
        .encode(x="date:T", y="daily_cost:Q")
    )
    return (area + line).properties(
        title="Cost Trend — Altair View",
        height=280,
    ).configure_axis(gridColor="#e2e8f0").configure_view(strokeWidth=0)


def altair_waste_stacked_bar(resources: pd.DataFrame) -> alt.Chart:
    if resources.empty:
        return alt.Chart(pd.DataFrame()).mark_bar().properties(title="Waste by Type", height=280)

    df = (
        resources.groupby(["resource_type", "waste_level"], as_index=False)
        .agg(count=("resource_name", "count"), savings=("estimated_savings", "sum"))
    )
    return (
        alt.Chart(df)
        .mark_bar()
        .encode(
            x=alt.X("resource_type:N", title="Resource Type", axis=alt.Axis(labelAngle=-30)),
            y=alt.Y("count:Q", title="Resource Count"),
            color=alt.Color(
                "waste_level:N",
                scale=alt.Scale(
                    domain=list(WASTE_COLORS.keys()),
                    range=list(WASTE_COLORS.values()),
                ),
                legend=alt.Legend(title="Waste Level"),
            ),
            tooltip=["resource_type", "waste_level", "count", alt.Tooltip("savings:Q", format="$,.2f")],
        )
        .properties(title="Waste Distribution by Resource Type", height=280)
    )
