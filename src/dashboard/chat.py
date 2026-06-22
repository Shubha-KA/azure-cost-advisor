"""Conversational FinOps chat interface using st.chat_input."""

from __future__ import annotations

import streamlit as st

from src.ai.advisor import FinOpsAdvisor
from src.auth.entra import AuthSession, DelegatedTokenCredential
from src.ai.prompts import EXAMPLE_QUESTIONS
from src.config import Settings
from src.dashboard.data_loader import DashboardData
from src.storage.factory import create_storage_provider


def init_chat_state() -> None:
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []


def clear_chat() -> None:
    st.session_state.chat_messages = []


def render_chat_interface(data: DashboardData, settings: Settings) -> None:
    init_chat_state()

    st.markdown('<p class="section-title">FinOps Assistant</p>', unsafe_allow_html=True)

    mode = (
        f"Azure OpenAI + {settings.search_provider}"
        if settings.openai_configured
        else "Rule-based (offline)"
    )
    faiss_note = (
        "Azure AI Search"
        if settings.search_provider == "azure_ai_search"
        else "FAISS development fallback"
    )
    st.markdown(
        f'<div class="chat-hint">'
        f'<strong>Mode:</strong> {mode} | <strong>Knowledge base:</strong> {faiss_note}<br>'
        f'Ask about waste, cost spikes, savings opportunities, VMs, disks, public IPs, or AKS.'
        f'</div>',
        unsafe_allow_html=True,
    )

    hint_col1, hint_col2, hint_col3 = st.columns(3)
    for col, question in zip([hint_col1, hint_col2, hint_col3], EXAMPLE_QUESTIONS):
        with col:
            if st.button(question, use_container_width=True, key=f"hint_{hash(question)}"):
                _handle_message(question, settings)
                st.rerun()

    action_col1, _ = st.columns([1, 5])
    with action_col1:
        if st.button("Clear chat", use_container_width=True):
            clear_chat()
            st.rerun()

    if prompt := st.chat_input(
        "Ask about Azure costs, waste, anomalies, or savings…",
        key="finops_chat_input",
    ):
        _handle_message(prompt, settings)
        st.rerun()

    for message in reversed(st.session_state.chat_messages):
        with st.chat_message(message["role"]):
            st.markdown(message["content"])


def _handle_message(prompt: str, settings: Settings) -> None:
    st.session_state.chat_messages.append({"role": "user", "content": prompt})

    history = "\n".join(
        f"{m['role']}: {m['content']}"
        for m in st.session_state.chat_messages[:-1][-8:]
    )

    advisor_kwargs = {}
    auth_payload = st.session_state.get("entra_auth_session")
    if auth_payload:
        session = AuthSession.model_validate(auth_payload)
        subscriptions = [
            item.subscription_id
            for item in create_storage_provider(settings).subscriptions.list(
                session.profile.tenant_id
            )
            if item.selected and item.onboarding_status == "validated"
        ]
        advisor_kwargs = {
            "tenant_id": session.profile.tenant_id,
            "subscription_ids": subscriptions,
            "credential": DelegatedTokenCredential(session),
        }
    advisor = FinOpsAdvisor(settings, **advisor_kwargs)
    with st.spinner("Analyzing with FinOps Advisor…"):
        response = advisor.ask(prompt, chat_history=history)

    st.session_state.chat_messages.append({"role": "assistant", "content": response})
