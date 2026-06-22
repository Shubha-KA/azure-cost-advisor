"""Streamlit login and tenant onboarding flow."""

from __future__ import annotations

from typing import Any

import streamlit as st

from src.auth.entra import AuthSession, AuthenticationError, EntraAuthService
from src.onboarding.service import TenantOnboardingService

SESSION_AUTH = "entra_auth_session"
SESSION_FLOW = "entra_auth_flow"
SESSION_DISCOVERED = "entra_discovered_subscriptions"
SESSION_HEALTH = "entra_tenant_health"


def require_authenticated_onboarding(settings) -> AuthSession | None:
    if not settings.entra_auth_enabled:
        return None
    if not settings.entra_auth_configured:
        st.error(
            "Entra authentication is enabled but ENTRA_CLIENT_ID or "
            "ENTRA_CLIENT_SECRET is missing."
        )
        st.stop()

    auth = EntraAuthService(settings)
    if st.query_params.get("logout"):
        for key in (
            SESSION_AUTH,
            SESSION_FLOW,
            SESSION_DISCOVERED,
            SESSION_HEALTH,
        ):
            st.session_state.pop(key, None)
        st.query_params.clear()
        st.markdown(
            f'<meta http-equiv="refresh" content="0; url={auth.logout_url()}">',
            unsafe_allow_html=True,
        )
        st.stop()

    _complete_callback(auth)
    session = _load_session()
    if session is None or session.expired:
        st.title("Sign in")
        st.caption("Use your Microsoft organizational account.")
        flow = auth.begin_login()
        st.session_state[SESSION_FLOW] = flow
        st.link_button(
            "Sign in with Microsoft",
            flow["auth_uri"],
            type="primary",
            use_container_width=True,
        )
        st.stop()

    service = TenantOnboardingService(settings)
    service.register_authenticated_user(session)
    tenant = service.storage.tenants.get(session.profile.tenant_id)
    if not tenant or tenant.onboarding_status != "completed":
        _render_onboarding(service, session)
        st.stop()
    subscriptions = [
        item
        for item in service.storage.subscriptions.list(session.profile.tenant_id)
        if item.selected and item.onboarding_status == "validated"
    ]
    settings.default_tenant_id = session.profile.tenant_id
    if subscriptions:
        settings.default_subscription_id = subscriptions[0].subscription_id
    _render_account_sidebar(auth, session)
    return session


def _complete_callback(auth: EntraAuthService) -> None:
    params = dict(st.query_params)
    if not ("code" in params or "error" in params):
        return
    flow = st.session_state.get(SESSION_FLOW)
    if not flow:
        st.error("Login session was not found. Start sign-in again.")
        st.query_params.clear()
        return
    try:
        session = auth.complete_login(flow, params)
    except AuthenticationError as exc:
        st.error(str(exc))
    else:
        st.session_state[SESSION_AUTH] = session.model_dump(
            by_alias=True, mode="json"
        )
        st.session_state.pop(SESSION_FLOW, None)
        st.query_params.clear()
        st.rerun()


def _load_session() -> AuthSession | None:
    payload = st.session_state.get(SESSION_AUTH)
    return AuthSession.model_validate(payload) if payload else None


def _render_onboarding(
    service: TenantOnboardingService, session: AuthSession
) -> None:
    st.title("Azure tenant onboarding")
    st.success(f"Signed in as {session.profile.display_name or session.profile.email}")

    discovered_payload = st.session_state.get(SESSION_DISCOVERED, [])
    if st.button("Discover Azure subscriptions", type="primary"):
        try:
            discovered = service.discover_subscriptions(session)
            discovered_payload = [
                item.model_dump(by_alias=True) for item in discovered
            ]
            st.session_state[SESSION_DISCOVERED] = discovered_payload
        except Exception as exc:
            st.error(f"Subscription discovery failed: {exc}")

    if not discovered_payload:
        st.info("Discover subscriptions to continue.")
        return

    from src.onboarding.azure_access import DiscoveredSubscription

    discovered = [
        DiscoveredSubscription.model_validate(item)
        for item in discovered_payload
    ]
    labels = {
        item.subscription_id: f"{item.display_name} ({item.subscription_id})"
        for item in discovered
    }
    selected = st.multiselect(
        "Subscriptions",
        options=list(labels),
        format_func=lambda value: labels[value],
    )

    if st.button("Run access validation", disabled=not selected):
        try:
            service.persist_selected_subscriptions(
                session, discovered, selected
            )
            health = service.validate_subscriptions(session, selected)
            st.session_state[SESSION_HEALTH] = [
                item.model_dump(by_alias=True, mode="json")
                for item in health
            ]
        except Exception as exc:
            st.error(f"Validation failed: {exc}")

    health_payload = st.session_state.get(SESSION_HEALTH, [])
    if health_payload:
        _render_health(health_payload)
        selected_health = [
            item
            for item in health_payload
            if item["subscriptionId"] in selected
        ]
        can_complete = bool(selected_health) and all(
            item["validationStatus"] != "failed"
            for item in selected_health
        )
        if st.button(
            "Complete onboarding",
            type="primary",
            disabled=not can_complete,
        ):
            try:
                service.complete_onboarding(session, selected)
                st.success("Tenant onboarding completed.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))


def _render_health(records: list[dict[str, Any]]) -> None:
    st.subheader("Validation results")
    for record in records:
        st.markdown(f"**Subscription `{record['subscriptionId']}`**")
        for check in record["validationResults"].values():
            passed = check["status"] == "passed"
            requirement = "Required" if check["mandatory"] else "Optional"
            icon = "PASS" if passed else "MISSING"
            st.write(
                f"{icon} | {check['name']} | {requirement} | {check['message']}"
            )


def _render_account_sidebar(
    auth: EntraAuthService, session: AuthSession
) -> None:
    with st.sidebar:
        st.divider()
        st.caption(session.profile.display_name or session.profile.email)
        st.link_button(
            "Sign out",
            "?logout=1",
            use_container_width=True,
        )
