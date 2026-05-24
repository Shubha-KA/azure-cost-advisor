"""Custom CSS for the FinOps dashboard."""

from __future__ import annotations

import streamlit as st

CUSTOM_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'IBM Plex Sans', sans-serif;
    }

    .main-header {
        background: linear-gradient(135deg, #0078d4 0%, #005a9e 50%, #004578 100%);
        padding: 1.5rem 2rem;
        border-radius: 12px;
        margin-bottom: 1.5rem;
        color: white;
        box-shadow: 0 4px 20px rgba(0, 120, 212, 0.25);
    }

    .main-header h1 {
        color: white !important;
        margin: 0;
        font-size: 1.75rem;
        font-weight: 700;
    }

    .main-header p {
        color: rgba(255,255,255,0.9) !important;
        margin: 0.25rem 0 0 0;
        font-size: 0.95rem;
    }

    div[data-testid="stMetric"] {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 0.75rem 1rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }

    div[data-testid="stMetric"] label {
        color: #64748b !important;
        font-size: 0.8rem !important;
        font-weight: 500 !important;
    }

    div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
        color: #0f172a !important;
        font-weight: 700 !important;
    }

    .rec-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-left: 4px solid #0078d4;
        border-radius: 8px;
        padding: 1rem 1.25rem;
        margin-bottom: 0.75rem;
        box-shadow: 0 1px 4px rgba(0,0,0,0.05);
    }

    .rec-card-high {
        border-left-color: #dc2626;
    }

    .rec-card-medium {
        border-left-color: #f59e0b;
    }

    .rec-card-low {
        border-left-color: #10b981;
    }

    .rec-card-title {
        font-weight: 600;
        color: #0f172a;
        font-size: 1rem;
        margin-bottom: 0.35rem;
    }

    .rec-card-body {
        color: #475569;
        font-size: 0.875rem;
        line-height: 1.5;
    }

    .rec-card-savings {
        color: #059669;
        font-weight: 600;
        font-size: 0.9rem;
        margin-top: 0.5rem;
    }

    .status-pill {
        display: inline-block;
        padding: 0.15rem 0.6rem;
        border-radius: 999px;
        font-size: 0.75rem;
        font-weight: 600;
    }

    .pill-high { background: #fee2e2; color: #b91c1c; }
    .pill-medium { background: #fef3c7; color: #b45309; }
    .pill-low { background: #d1fae5; color: #047857; }
    .pill-none { background: #f1f5f9; color: #64748b; }

    .section-title {
        font-size: 1.15rem;
        font-weight: 600;
        color: #0f172a;
        margin: 1.25rem 0 0.75rem 0;
        padding-bottom: 0.35rem;
        border-bottom: 2px solid #0078d4;
    }

    .chat-hint {
        background: #eff6ff;
        border: 1px solid #bfdbfe;
        border-radius: 8px;
        padding: 0.75rem 1rem;
        font-size: 0.85rem;
        color: #1e40af;
        margin-bottom: 1rem;
    }

    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
"""


def inject_styles() -> None:
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def render_header(title: str, subtitle: str) -> None:
    st.markdown(
        f'<div class="main-header"><h1>{title}</h1><p>{subtitle}</p></div>',
        unsafe_allow_html=True,
    )
