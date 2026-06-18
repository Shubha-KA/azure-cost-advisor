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
    amount_col = "cost_amount" if "cost_amount" in df else "daily_cost"
    if "currency" not in df:
        df["currency"] = "USD"
    df["rolling_7d"] = df.groupby("currency")[amount_col].transform(
        lambda values: values.rolling(window=7, min_periods=1).mean()
    )

    fig = go.Figure()
    for currency, currency_df in df.groupby("currency"):
        fig.add_trace(
            go.Scatter(
                x=currency_df["date"],
                y=currency_df[amount_col],
                name=f"Daily Cost ({currency})",
                mode="lines+markers",
                customdata=[currency] * len(currency_df),
                hovertemplate="%{x}<br>%{customdata} %{y:,.2f}<extra></extra>",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=currency_df["date"],
                y=currency_df["rolling_7d"],
                name=f"7-Day Avg ({currency})",
                mode="lines",
                line=dict(dash="dash"),
                customdata=[currency] * len(currency_df),
                hovertemplate="%{x}<br>%{customdata} %{y:,.2f}<extra></extra>",
            )
        )
    fig.update_layout(
        title="Daily Azure Spend Trend",
        xaxis_title="Date",
        yaxis_title="Cost amount (see currency in legend)",
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
    cost_col = (
        "cost_amount"
        if "cost_amount" in df.columns
        else ("cost_usd" if "cost_usd" in df.columns else "monthly_cost")
    )
    if "currency" not in df:
        df["currency"] = "USD"

    fig = px.bar(
        df,
        x=cost_col,
        y=name_col,
        orientation="h",
        title="Top Services by Cost",
        labels={cost_col: "Cost amount", name_col: "Service"},
        color="currency",
        custom_data=["currency"],
    )
    fig.update_layout(
        height=380,
        template=PLOTLY_TEMPLATE,
        showlegend=False,
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
        labels={"estimated_savings": "Estimated savings", "resource_name": "Resource"},
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
    amount_col = "cost_amount" if "cost_amount" in df else "daily_cost"
    if "currency" not in df:
        df["currency"] = "USD"

    area = (
        alt.Chart(df)
        .mark_area(opacity=0.4, color=COLORS["primary"])
        .encode(
            x=alt.X("date:T", title="Date"),
            y=alt.Y(f"{amount_col}:Q", title="Daily cost amount", stack=None),
            color=alt.Color("currency:N", title="Currency"),
            tooltip=[
                alt.Tooltip("date:T", title="Date"),
                alt.Tooltip(f"{amount_col}:Q", title="Cost", format=",.2f"),
                alt.Tooltip("currency:N", title="Currency"),
            ],
        )
    )
    line = (
        alt.Chart(df)
        .mark_line(color=COLORS["secondary"], strokeWidth=2)
        .encode(
            x="date:T",
            y=f"{amount_col}:Q",
            color=alt.Color("currency:N", title="Currency"),
        )
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
            tooltip=[
                "resource_type",
                "waste_level",
                "count",
                alt.Tooltip("savings:Q", format=",.2f"),
            ],
        )
        .properties(title="Waste Distribution by Resource Type", height=280)
    )
