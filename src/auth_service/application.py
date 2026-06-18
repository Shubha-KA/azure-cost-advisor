"""Authentication service application logic."""

from __future__ import annotations

import base64
import hashlib
import json

from cryptography.fernet import Fernet, InvalidToken
from fastapi import Body, HTTPException, Request
from fastapi.responses import RedirectResponse

from src.api.security import SESSION_COOKIE, SessionTokenService, get_identity, tenant_scope
from src.auth.entra import EntraAuthService
from src.compliance.lifecycle import TenantLifecycleService
from src.events.contracts import EventType, PlatformEvent
from src.onboarding.service import TenantOnboardingService

FLOW_COOKIE = "finops_auth_flow"


class AuthApplicationService:
    def __init__(self, app) -> None:
        self.app = app

    @property
    def settings(self):
        return self.app.state.settings

    @property
    def storage(self):
        return self.app.state.storage

    @property
    def events(self):
        return self.app.state.events

    def cipher(self):
        secret = self.settings.api_session_secret.encode("utf-8")
        return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret).digest()))

    def login(self):
        if not self.settings.entra_auth_enabled:
            return RedirectResponse(f"{self.settings.frontend_url}/dashboard")
        flow = EntraAuthService(self.settings).begin_login()
        response = RedirectResponse(str(flow["auth_uri"]))
        response.set_cookie(
            FLOW_COOKIE,
            self.cipher().encrypt(json.dumps(flow).encode()).decode(),
            httponly=True,
            secure=self.settings.api_session_cookie_secure,
            samesite="lax",
            max_age=600,
        )
        return response

    def callback(self, request: Request):
        try:
            flow = json.loads(
                self.cipher().decrypt(
                    request.cookies.get(FLOW_COOKIE, "").encode(), ttl=600
                )
            )
        except (InvalidToken, ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(400, "Login flow expired or invalid") from exc
        session = EntraAuthService(self.settings).complete_login(
            flow, dict(request.query_params)
        )
        TenantOnboardingService(
            self.settings, storage=self.storage
        ).register_authenticated_user(session)
        self.events.publish(
            PlatformEvent(
                eventType=EventType.TENANT_ONBOARDED,
                tenantId=session.profile.tenant_id,
                correlationId=str(flow.get("state", session.profile.user_id)),
                producer="auth-service",
                payload={"userId": session.profile.user_id},
            )
        )
        user = next(
            item
            for item in self.storage.tenant_users.list(session.profile.tenant_id)
            if item.user_id == session.profile.user_id
        )
        token = SessionTokenService(self.settings).issue(
            {
                "tid": session.profile.tenant_id,
                "oid": session.profile.user_id,
                "email": session.profile.email,
                "name": session.profile.display_name,
                "roles": user.roles,
            }
        )
        response = RedirectResponse(f"{self.settings.frontend_url}/dashboard")
        response.set_cookie(
            SESSION_COOKIE,
            token,
            httponly=True,
            secure=self.settings.api_session_cookie_secure,
            samesite="lax",
            max_age=8 * 60 * 60,
        )
        response.delete_cookie(FLOW_COOKIE)
        return response

    def logout(self):
        url = (
            EntraAuthService(self.settings).logout_url()
            if self.settings.entra_auth_enabled
            else self.settings.frontend_url
        )
        response = RedirectResponse(url, status_code=303)
        response.delete_cookie(SESSION_COOKIE)
        return response

    def me(self, request: Request):
        return get_identity(request).__dict__

    def tenants(self, request: Request):
        identity = get_identity(request)
        rows = (
            self.storage.tenants.list()
            if identity.platform_admin
            else [self.storage.tenants.get(identity.tenant_id)]
        )
        return [
            item.model_dump(by_alias=True, mode="json")
            for item in rows
            if item is not None
        ]

    def subscriptions(self, request: Request):
        identity = get_identity(request)
        tenant_id = tenant_scope(request, identity)
        return [
            item.model_dump(by_alias=True, mode="json")
            for item in self.storage.subscriptions.list(tenant_id)
        ]

    def tenant_health(self, request: Request):
        identity = get_identity(request)
        tenant_id = tenant_scope(request, identity)
        return [
            item.model_dump(by_alias=True, mode="json")
            for item in self.storage.tenant_health.list(tenant_id)
        ]

    def offboard(self, tenant_id: str, request: Request, body: dict = Body(default={})):
        identity = get_identity(request)
        if tenant_id != identity.tenant_id and not identity.platform_admin:
            raise HTTPException(403, "Tenant access denied")
        lifecycle = TenantLifecycleService(self.settings, self.storage)
        return lifecycle.request_deletion(
            tenant_id, str(body.get("requestedBy") or identity.user_id)
        )
