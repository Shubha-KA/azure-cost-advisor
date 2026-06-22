"""AI recommendation cards from FAISS/RAG or rule-based engine."""

from __future__ import annotations

import re

import pandas as pd
import streamlit as st

from src.ai.advisor import FinOpsAdvisor
from src.config import Settings
from src.dashboard.data_loader import DashboardData
from src.money import format_money


def render_recommendation_cards(
    data: DashboardData,
    settings: Settings,
    *,
    allow_regenerate: bool = True,
) -> None:
    st.markdown('<p class="section-title">AI FinOps Recommendations</p>', unsafe_allow_html=True)

    rec = data.recommendations
    source = rec.get("source", "none")
    faiss_status = "✅ FAISS index ready" if data.faiss_ready else "⚠️ FAISS index not built"
    openai_status = "✅ Azure OpenAI" if settings.openai_configured else "⚠️ Rule-based mode"

    status_col1, status_col2, status_col3 = st.columns(3)
    status_col1.caption(f"**Engine:** {source}")
    status_col2.caption(f"**{openai_status}**")
    status_col3.caption(f"**{faiss_status}**")

    if allow_regenerate:
        regen_col, build_col = st.columns(2)
        with regen_col:
            if st.button("Regenerate Recommendations", type="primary", use_container_width=True):
                with st.spinner("Generating recommendations via FinOps Advisor..."):
                    advisor = FinOpsAdvisor(settings)
                    if settings.openai_configured and not data.faiss_ready:
                        advisor.build_index(rebuild=True)
                    rec = advisor.generate_recommendations()
                    st.session_state["latest_recommendations"] = rec
                    st.rerun()
        with build_col:
            if st.button("Rebuild FAISS Index", use_container_width=True):
                with st.spinner("Building FAISS index..."):
                    advisor = FinOpsAdvisor(settings)
                    count = advisor.build_index(rebuild=True)
                    st.success(f"Index built: {count} vectors")

    if st.session_state.get("latest_recommendations"):
        rec = st.session_state["latest_recommendations"]

    cards = _extract_recommendation_cards(rec, data.resources)
    if cards:
        for card in cards:
            _render_card(card)
    else:
        st.markdown(rec.get("recommendations", "_No recommendations available._"))
        st.caption(f"Generated: {rec.get('generated_at', 'N/A')}")


def _extract_recommendation_cards(
    rec: dict, resources: pd.DataFrame
) -> list[dict]:
    cards: list[dict] = []

    if not resources.empty:
        flagged = resources[resources["waste_level"] != "NONE"].sort_values(
            "estimated_savings", ascending=False
        )
        for _, row in flagged.head(8).iterrows():
            cards.append(
                {
                    "title": f"{row['resource_name']} ({row['resource_type']})",
                    "body": row.get("recommendation", "") or "Review and remediate this resource.",
                    "savings": float(row.get("estimated_savings", 0)),
                    "currency": str(row.get("savings_currency", "")),
                    "level": str(row.get("waste_level", "MEDIUM")).lower(),
                    "metrics": (
                        f"CPU: {row.get('cpu_avg_percent', 0):.1f}% | "
                        f"Cost: {format_money(row.get('estimated_monthly_cost', row.get('monthly_cost', 0)), row.get('estimated_cost_currency', ''))}/mo "
                        f"({row.get('cost_basis', 'unknown')})"
                    ),
                }
            )

    text = rec.get("recommendations", "")
    if text and len(cards) < 3:
        sections = re.split(r"\n#{1,3}\s+", text)
        for section in sections:
            section = section.strip()
            if not section or len(section) < 20:
                continue
            lines = section.split("\n")
            title = lines[0].strip().strip("#")
            body = "\n".join(lines[1:]).strip()[:400]
            savings_match = re.search(r"\$[\d,]+", body)
            cards.append(
                {
                    "title": title[:80],
                    "body": body,
                    "savings": _parse_dollar(savings_match.group()) if savings_match else 0,
                    "level": "medium",
                    "metrics": "",
                }
            )

    return cards[:12]


def _parse_dollar(value: str) -> float:
    try:
        return float(value.replace("$", "").replace(",", ""))
    except ValueError:
        return 0.0


def _render_card(card: dict) -> None:

    """Render a recommendation card using safe markdown.

    This version avoids embedding raw HTML to prevent unsafe rendering.
    """
    level = card.get("level", "medium")
    # Build markdown content safely
    title_md = f"### {card.get('title', '')}"
    body_md = card.get("body", "")
    metrics_md = card.get("metrics", "")
    savings = card.get("savings", 0)
    currency = card.get("currency", "")
    # Assemble parts
    parts = [title_md]
    if body_md:
        parts.append(body_md)
    if metrics_md:
        parts.append(metrics_md)
    if savings > 0:
        parts.append(
            f"**Estimated savings:** {format_money(savings, currency)}/month"
        )
    # Add a level badge as plain text
    parts.append(f"*Level: {level.upper()}*")
    md_content = "\n\n".join(parts)
    st.markdown(md_content)

