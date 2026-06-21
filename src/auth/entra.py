"""Multi-tenant Microsoft Entra OAuth2/OIDC authorization-code flow."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

from azure.core.credentials import AccessToken
from pydantic import BaseModel, Field

from src.config import Settings, get_settings

ARM_SCOPE = "https://management.azure.com/user_impersonation"


class AuthenticationError(RuntimeError):
    pass


class UserProfile(BaseModel):
    tenant_id: str = Field(alias="tenantId")
    user_id: str = Field(alias="userId")
    email: str = ""
    display_name: str = Field(default="", alias="displayName")

    model_config = {"populate_by_name": True}


class AuthSession(BaseModel):
    profile: UserProfile
    access_token: str = Field(alias="accessToken")
    expires_at: datetime = Field(alias="expiresAt")
    id_token_claims: dict[str, Any] = Field(
        default_factory=dict, alias="idTokenClaims"
    )

    model_config = {"populate_by_name": True}

    @property
    def expired(self) -> bool:
        return self.expires_at <= datetime.now(timezone.utc) + timedelta(minutes=1)


class EntraAuthService:
    def __init__(self, settings: Settings | None = None, client=None) -> None:
        self.settings = settings or get_settings()
        if not self.settings.entra_auth_configured:
            raise AuthenticationError(
                "ENTRA_CLIENT_ID and ENTRA_CLIENT_SECRET are required"
            )
        self.client = client or self._create_client()

    def _create_client(self):
        try:
            import msal
        except ImportError as exc:
            raise AuthenticationError("msal is required for Entra login") from exc
        return msal.ConfidentialClientApplication(
            self.settings.entra_client_id,
            authority=self.settings.entra_authority,
            client_credential=self.settings.entra_client_secret,
        )

    def begin_login(self) -> dict[str, Any]:
        return self.client.initiate_auth_code_flow(
            scopes=[ARM_SCOPE],
            redirect_uri=self.settings.entra_redirect_uri,
            prompt="select_account",
        )

    def complete_login(
        self, flow: dict[str, Any], callback_params: dict[str, Any]
    ) -> AuthSession:
        try:
            result = self.client.acquire_token_by_auth_code_flow(
                flow, callback_params
            )
        except ValueError as exc:
            raise AuthenticationError(
                "The login response failed state or authorization validation"
            ) from exc
        if "access_token" not in result:
            description = result.get("error_description", result.get("error", "unknown"))
            raise AuthenticationError(f"Microsoft login failed: {description}")
        claims = result.get("id_token_claims", {})
        tenant_id = str(claims.get("tid", ""))
        user_id = str(claims.get("oid") or claims.get("sub") or "")
        if not tenant_id or not user_id:
            raise AuthenticationError("The Entra token is missing tid or oid claims")
        profile = UserProfile(
            tenantId=tenant_id,
            userId=user_id,
            email=str(
                claims.get("preferred_username")
                or claims.get("email")
                or claims.get("upn")
                or ""
            ),
            displayName=str(claims.get("name", "")),
        )
        expires_in = int(result.get("expires_in", 3600))
        
        # --- TELEMETRY DUMP FOR VALIDATION ---
        import json
        telemetry = {
            "oid": user_id,
            "tid": tenant_id,
            "tenant_name": str(claims.get("name", "")),
            "home_account_id": result.get("account", {}).get("home_account_id", "")
        }
        print("\n" + "="*50)
        print(f"AUTH TELEMETRY CAPTURED: {json.dumps(telemetry, indent=2)}")
        print("="*50 + "\n", flush=True)
        # -------------------------------------

        return AuthSession(
            profile=profile,
            accessToken=result["access_token"],
            expiresAt=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
            idTokenClaims=claims,
        )

    def logout_url(self) -> str:
        authority = self.settings.entra_authority.rstrip("/")
        redirect = quote(
            self.settings.entra_post_logout_redirect_uri, safe=""
        )
        return (
            f"{authority}/oauth2/v2.0/logout?"
            f"post_logout_redirect_uri={redirect}"
        )


class DelegatedTokenCredential:
    """Azure SDK credential backed by the current delegated ARM token."""

    def __init__(self, session: AuthSession) -> None:
        self.session = session

    def get_token(self, *scopes: str, **kwargs: Any) -> AccessToken:
        if self.session.expired:
            raise AuthenticationError("The delegated Azure token has expired")
        return AccessToken(
            self.session.access_token,
            int(self.session.expires_at.timestamp()),
        )
