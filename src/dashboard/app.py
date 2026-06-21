"""Azure Cost Optimization Advisor — Streamlit dashboard."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.config import get_settings
from src.auth.entra import DelegatedTokenCredential
from src.dashboard.chat import render_chat_interface
from src.dashboard.components import (
    render_anomaly_panel,
    render_executive_summary,
    render_recommendation_cards,
    render_waste_analysis,
)
from src.dashboard.data_loader import DashboardDataLoader
from src.dashboard.onboarding import require_authenticated_onboarding
from src.dashboard.styles import inject_styles, render_header
from src.pipeline import run_pipeline
from src.services.multi_tenant_pipeline import MultiTenantPipelineService

st.set_page_config(
    page_title="Azure Cost Optimization Advisor",
    page_icon="☁️",
    layout="wide",
    initial_sidebar_state="expanded",
)


def render_sidebar(settings, auth_session=None) -> None:
    with st.sidebar:
        st.markdown("## ☁️")
        st.title("FinsOpsIQ")
        st.caption("AI-Powered Azure FinOps")

        st.divider()
        st.subheader("Data Pipeline")

        skip_ai = st.checkbox(
            "Skip AI step",
            value=not settings.openai_configured,
            help="Skip FAISS indexing and Azure OpenAI recommendations",
        )

        if st.button("Run Full Pipeline", type="primary", use_container_width=True):
            with st.spinner("Collecting → Processing → AI indexing…"):
                try:
                    if auth_session is not None:
                        service = MultiTenantPipelineService(
                            settings,
                            credential_factory=lambda tenant_id, subscription_id: (
                                DelegatedTokenCredential(auth_session)
                            ),
                        )
                        result = service.run_once(
                            tenant_id=auth_session.profile.tenant_id
                        )
                        if any(
                            item.status == "failed"
                            for item in result.results
                        ):
                            raise RuntimeError(
                                "One or more subscription runs failed"
                            )
                    else:
                        run_pipeline(skip_ai=skip_ai)
                    st.success("Pipeline completed.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Pipeline failed: {exc}")

        st.divider()
        st.subheader("System Status")
        st.markdown(
            f"| Component | Status |\n"
            f"|---|---|\n"
            f"| Azure API | {'✅' if settings.azure_credentials_configured else '⚠️ Mock'} |\n"
            f"| Azure OpenAI | {'✅' if settings.openai_configured else '⚠️ Offline'} |\n"
            f"| Raw data | `{settings.raw_path}` |\n"
            f"| Processed | `{settings.processed_path}` |\n"
            f"| FAISS index | `{settings.faiss_index_path}` |"
        )


def render_empty_state() -> None:
    st.warning("No analysis data found.")
    st.info(
        "Click **Run Full Pipeline** in the sidebar to collect Azure cost data, "
        "detect waste and anomalies, build the FAISS knowledge base, and generate recommendations.\n\n"
        "Works with synthetic demo data — configure `.env` for live Azure and OpenAI."
    )


def main() -> None:
    inject_styles()
    settings = get_settings()
    auth_session = require_authenticated_onboarding(settings)
    render_sidebar(settings, auth_session)

    render_header(
        "☁️ Azure Cost Optimization Advisor",
        "Analyze spend · Detect waste · Estimate savings · Chat with FinOps AI",
    )

    data = DashboardDataLoader(settings).load()

    if not data.data_available:
        render_empty_state()
        return

    tab_exec, tab_waste, tab_trends, tab_recs, tab_anomalies, tab_chat = st.tabs(
        [
            "Executive Summary",
            "Waste Analysis",
            "Cost Trends",
            "AI Recommendations",
            "Anomalies",
            "FinOps Chat",
        ]
    )

    with tab_exec:
        render_executive_summary(data)

    with tab_waste:
        render_waste_analysis(data)

    with tab_trends:
        from src.dashboard import charts

        st.markdown('<p class="section-title">Cost Trend Analysis</p>', unsafe_allow_html=True)
        if data.daily_costs.empty:
            st.info("No daily cost trend data. Run the collector to ingest cost records.")
        else:
            st.plotly_chart(
                charts.plotly_daily_cost_trend(data.daily_costs),
                use_container_width=True,
                key="daily_cost_trend_chart",
            )
            st.altair_chart(
                charts.altair_cost_area(data.daily_costs),
                use_container_width=True,
            )
            st.plotly_chart(
                charts.plotly_service_breakdown(data.service_costs),
                use_container_width=True,
                key="service_breakdown_chart",
            )

    with tab_recs:
        render_recommendation_cards(data, settings)

    with tab_anomalies:
        render_anomaly_panel(data)

    with tab_chat:
        render_chat_interface(data, settings)


if __name__ == "__main__":
    main()
