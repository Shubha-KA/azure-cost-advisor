"""Session authentication and tenant/subscription authorization."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import HTTPException, Request, status

from src.config import Settings

SESSION_COOKIE = "finops_session"


@dataclass(frozen=True)
class RequestIdentity:
    tenant_id: str
    user_id: str
    email: str
    display_name: str
    roles: tuple[str, ...]

    @property
    def platform_admin(self) -> bool:
        return "platform_admin" in self.roles


class SessionTokenService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def issue(self, claims: dict[str, Any]) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "tid": claims["tid"],
            "oid": claims["oid"],
            "email": claims.get("email", ""),
            "name": claims.get("name", ""),
            "roles": claims.get("roles", []),
            "iat": now,
            "exp": now + timedelta(hours=8),
            "iss": "azure-cost-advisor",
            "aud": "azure-cost-advisor-api",
        }
        return jwt.encode(
            payload, self.settings.api_session_secret, algorithm="HS256"
        )

    def decode(self, token: str) -> RequestIdentity:
        try:
            claims = jwt.decode(
                token,
                self.settings.api_session_secret,
                algorithms=["HS256"],
                issuer="azure-cost-advisor",
                audience="azure-cost-advisor-api",
            )
        except jwt.PyJWTError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired session",
            ) from exc
        tenant_id = str(claims.get("tid", ""))
        user_id = str(claims.get("oid", ""))
        if not tenant_id or not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session is missing tenant or user identity",
            )
        return RequestIdentity(
            tenant_id=tenant_id,
            user_id=user_id,
            email=str(claims.get("email", "")),
            display_name=str(claims.get("name", "")),
            roles=tuple(str(role) for role in claims.get("roles", [])),
        )


def get_identity(request: Request) -> RequestIdentity:
    settings: Settings = request.app.state.settings
    if not settings.entra_auth_enabled:
        return RequestIdentity(
            tenant_id=settings.effective_tenant_id,
            user_id="legacy-user",
            email="",
            display_name="Legacy administrator",
            roles=("tenant_admin",),
        )
    token = request.cookies.get(SESSION_COOKIE, "")
    if not token:
        authorization = request.headers.get("Authorization", "")
        if authorization.lower().startswith("bearer "):
            token = authorization[7:].strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return SessionTokenService(settings).decode(token)


def tenant_scope(request: Request, identity: RequestIdentity) -> str:
    requested = request.headers.get("X-Tenant-ID") or identity.tenant_id
    if requested != identity.tenant_id and not identity.platform_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant access denied",
        )
    return requested


def subscription_scope(
    request: Request, identity: RequestIdentity, tenant_id: str
) -> str:
    settings: Settings = request.app.state.settings
    subscription_id = (
        request.headers.get("X-Subscription-ID")
        or settings.effective_subscription_id
    )
    subscriptions = request.app.state.storage.subscriptions.list(tenant_id)
    if subscriptions and subscription_id not in {
        item.subscription_id for item in subscriptions if item.selected
    }:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Subscription access denied",
        )
    return subscription_id
