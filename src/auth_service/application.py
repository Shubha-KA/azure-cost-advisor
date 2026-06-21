"""Authentication service application logic."""

from __future__ import annotations

import base64
import hashlib
import json
import uuid
from datetime import timedelta

from cryptography.fernet import Fernet, InvalidToken
from fastapi import Body, HTTPException, Request
from fastapi.responses import RedirectResponse

from src.api.security import SESSION_COOKIE, SessionTokenService, get_identity, tenant_scope
from src.auth.entra import EntraAuthService, AuthSession
from src.domain.models import ServerSession, utc_now
from src.compliance.lifecycle import TenantLifecycleService
from src.events.contracts import EventType, PlatformEvent
from src.onboarding.service import TenantOnboardingService
import httpx
import logging

logger = logging.getLogger(__name__)

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
        onboarding_service = TenantOnboardingService(
            self.settings, storage=self.storage
        )
        onboarding_service.register_authenticated_user(session)
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

        # Determine redirect destination based on tenant onboarding and initial
        # collection status. A completed onboarding record is not sufficient:
        # the first collection must also finish successfully.
        if self._onboarding_state(session.profile.tenant_id)["status"] == "ready":
            redirect_path = "/dashboard"
        else:
            redirect_path = "/onboarding"

        response = RedirectResponse(f"{self.settings.frontend_url}{redirect_path}")
        response.set_cookie(
            SESSION_COOKIE,
            token,
            httponly=True,
            secure=self.settings.api_session_cookie_secure,
            samesite="lax",
            max_age=8 * 60 * 60,
        )
        
        # Save Entra session server-side to avoid cookie limits
        session_id = str(uuid.uuid4())
        server_session = ServerSession(
            session_id=session_id,
            tenant_id=session.profile.tenant_id,
            user_id=session.profile.user_id,
            auth_session=session.model_dump(by_alias=True, mode="json"),
            expires_at=utc_now() + timedelta(hours=8),
        )
        self.storage.sessions.upsert(server_session)
        
        response.set_cookie(
            "finops_sid",
            session_id,
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
        response.delete_cookie("finops_sid")
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

    def _get_entra_session(self, request: Request) -> AuthSession:
        session_id = request.cookies.get("finops_sid")
        if not session_id:
            raise HTTPException(401, "Missing Entra session for onboarding")
        try:
            server_session = self.storage.sessions.get(session_id)
            if not server_session:
                raise HTTPException(401, "Invalid or expired Entra session")
            if server_session.expires_at < utc_now():
                self.storage.sessions.delete(session_id)
                raise HTTPException(401, "Entra session expired")
            return AuthSession.model_validate(server_session.auth_session)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(401, "Failed to load Entra session") from exc

    def onboarding_status(self, request: Request):
        identity = get_identity(request)
        return self._onboarding_state(identity.tenant_id)

    def _onboarding_state(self, tenant_id: str) -> dict:
        tenant = self.storage.tenants.get(tenant_id)
        if not tenant:
            return {"status": "unknown"}
        if tenant.onboarding_status != "completed":
            health_records = self.storage.tenant_health.list(tenant_id)
            selected_subscriptions = [
                item
                for item in self.storage.subscriptions.list(tenant_id)
                if item.selected
            ]
            failed_health = [
                item
                for item in health_records
                if item.validation_status == "failed"
            ]
            if failed_health:
                return {
                    "status": "permission_validation_failed",
                    "message": "Required Azure permissions are missing.",
                    "validationResults": [
                        item.model_dump(by_alias=True, mode="json")
                        for item in failed_health
                    ],
                }
            pending_validation = [
                item
                for item in selected_subscriptions
                if item.onboarding_status in {
                    "validation_pending",
                    "validation_failed",
                }
            ]
            if pending_validation:
                return {
                    "status": "permission_validation_required",
                    "message": "Selected subscriptions must pass permission validation before collection can start.",
                    "subscriptions": [
                        item.model_dump(by_alias=True, mode="json")
                        for item in pending_validation
                    ],
                    "validationResults": [
                        item.model_dump(by_alias=True, mode="json")
                        for item in health_records
                    ],
                }
            return {"status": tenant.onboarding_status}

        subscriptions = [
            item for item in self.storage.subscriptions.list(tenant_id)
            if item.selected and item.onboarding_status == "validated"
        ]
        if not subscriptions:
            return {
                "status": "pending_collection",
                "message": "No validated selected subscriptions are ready for collection.",
            }

        details = []
        for subscription in subscriptions:
            runs = [
                item for item in self.storage.processing_metadata.list_latest(
                    tenant_id, subscription.subscription_id
                )
                if item.get("metadataType") == "collectionRun"
            ]
            latest = runs[0] if runs else None
            details.append(
                {
                    "subscriptionId": subscription.subscription_id,
                    "displayName": subscription.display_name,
                    "collection": latest,
                }
            )
            if latest is None:
                return {
                    "status": "pending_collection",
                    "message": "Initial collection has not started yet.",
                    "subscriptions": details,
                }
            if latest.get("status") == "running":
                return {
                    "status": "collecting",
                    "message": "Initial collection is running.",
                    "subscriptions": details,
                }
            if latest.get("status") != "completed":
                return {
                    "status": "collection_failed",
                    "message": "Collection failed",
                    "errors": latest.get("errors", []),
                    "subscriptions": details,
                }

        return {"status": "ready", "subscriptions": details}

    def discover_subscriptions(self, request: Request):
        get_identity(request)  # ensure authenticated
        session = self._get_entra_session(request)
        service = TenantOnboardingService(self.settings, self.storage)
        discovered = service.discover_subscriptions(session)
        return [
            item.model_dump(by_alias=True)
            for item in discovered
            if item.state == "Enabled"
        ]

    async def select_subscriptions(self, request: Request, body: dict):
        identity = get_identity(request)
        session = self._get_entra_session(request)
        subscription_ids = body.get("subscriptionIds", [])
        if not subscription_ids:
            raise HTTPException(400, "No subscriptions provided")

        service = TenantOnboardingService(self.settings, self.storage)
        discovered = service.discover_subscriptions(session)
        service.persist_selected_subscriptions(session, discovered, subscription_ids)
        
        health_records = service.validate_subscriptions(session, subscription_ids)
        if any(item.validation_status == "failed" for item in health_records):
            return {
                "success": False,
                "message": "Required Azure permissions are missing. Collection has not started.",
                "validationResults": [item.model_dump(by_alias=True, mode="json") for item in health_records]
            }

        service.complete_onboarding(session, subscription_ids)

        import asyncio
        asyncio.create_task(
            self._trigger_collections(session.profile.tenant_id, subscription_ids)
        )

        return {
            "success": True,
            "validationResults": [item.model_dump(by_alias=True, mode="json") for item in health_records]
        }

    async def retry_collection(self, request: Request):
        identity = get_identity(request)
        subscription_ids = [
            item.subscription_id
            for item in self.storage.subscriptions.list(identity.tenant_id)
            if item.selected and item.onboarding_status == "validated"
        ]
        if not subscription_ids:
            raise HTTPException(400, "No validated selected subscriptions to collect")
        await self._trigger_collections(identity.tenant_id, subscription_ids)
        return {"success": True, "subscriptionIds": subscription_ids}

    async def _trigger_collections(self, tenant_id: str, subscription_ids: list[str]):
        import jwt
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)
        internal_token = jwt.encode(
            {
                "iss": "azure-cost-advisor",
                "aud": self.settings.internal_api_audience,
                "exp": now + timedelta(hours=1),
            },
            self.settings.api_session_secret,
            algorithm="HS256",
        )
        headers = {"Authorization": f"Bearer {internal_token}"}
        async with httpx.AsyncClient(timeout=10) as client:
            for sub_id in subscription_ids:
                url = f"{self.settings.collection_service_url}/internal/collections"
                payload = {"tenantId": tenant_id, "subscriptionId": sub_id}
                try:
                    logger.info(
                        "collection_trigger_start url=%s payload=%s",
                        url,
                        payload,
                    )
                    response = await client.post(url, json=payload, headers=headers)
                    if response.status_code >= 400:
                        logger.error(
                            "collection_trigger_failed url=%s status_code=%s response=%s",
                            url,
                            response.status_code,
                            response.text,
                        )
                    else:
                        logger.info(
                            "collection_trigger_success url=%s status_code=%s response=%s",
                            url,
                            response.status_code,
                            response.text[:1000],
                        )
                except httpx.RequestError as exc:
                    logger.error(
                        "collection_trigger_request_error url=%s payload=%s exception=%s message=%s",
                        url,
                        payload,
                        type(exc).__name__,
                        str(exc),
                    )
