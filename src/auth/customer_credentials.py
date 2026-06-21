"""Customer-tenant Azure credentials for unattended collection."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from src.repositories.errors import StorageConfigurationError, TenantScopeError

logger = logging.getLogger(__name__)


class CustomerTenantCredentialFactory:
    """Create an ARM credential scoped to a customer's Entra tenant.

    Collection credentials are runtime-aware:

    * AKS / managed identity mode uses a projected workload identity token as a
      client assertion for the platform's multi-tenant collection application.
    * Local Docker Compose mode does not use workload identity. It uses either a
      configured service principal secret or DefaultAzureCredential, which can
      include Azure CLI / developer credentials.
    """

    def __init__(
        self,
        settings,
        storage,
        *,
        assertion_provider: Callable[[], str] | None = None,
        credential_builder: Callable[..., Any] | None = None,
    ) -> None:
        self.settings = settings
        self.storage = storage
        self.assertion_provider = assertion_provider or self._read_assertion
        self.credential_builder = credential_builder
        self._credentials: dict[tuple[str, str], Any] = {}

    def for_subscription(self, tenant_id: str, subscription_id: str):
        if not tenant_id or not subscription_id:
            raise TenantScopeError("tenantId and subscriptionId are required")
        if not self.settings.entra_auth_enabled:
            return self._legacy_credential()
        subscriptions = {
            item.subscription_id: item
            for item in self.storage.subscriptions.list(tenant_id)
        }
        subscription = subscriptions.get(subscription_id)
        if subscription is None:
            raise TenantScopeError(
                "Subscription is not registered in the requested tenant"
            )

        authority_tenant_id = str(
            (subscription.model_extra or {}).get("sourceTenantId")
            or tenant_id
        )
        client_id = self.settings.collection_entra_client_id
        if not client_id:
            raise StorageConfigurationError(
                "COLLECTION_ENTRA_CLIENT_ID is required for cross-tenant collection"
            )

        if not self._use_workload_identity():
            return self._local_credential(authority_tenant_id)

        cache_key = (authority_tenant_id, client_id)
        if cache_key not in self._credentials:
            builder = self.credential_builder
            if builder is None:
                from azure.identity import ClientAssertionCredential

                builder = ClientAssertionCredential
            logger.info(
                "collection_credential_strategy strategy=workload_identity tenant_id=%s client_id=%s",
                authority_tenant_id,
                client_id,
            )
            self._credentials[cache_key] = builder(
                tenant_id=authority_tenant_id,
                client_id=client_id,
                func=self.assertion_provider,
            )
        return self._credentials[cache_key]

    def _use_workload_identity(self) -> bool:
        return bool(self.settings.use_managed_identity)

    def _local_credential(self, authority_tenant_id: str):
        """Return a non-workload-identity credential for local Docker Compose.

        Prefer an explicit client secret when present because it is deterministic
        in containers. Otherwise use DefaultAzureCredential with workload and
        managed identity legs excluded so local runs never accidentally take the
        AKS code path.
        """

        if self.settings.azure_client_id and self.settings.azure_client_secret:
            cache_key = (authority_tenant_id, self.settings.azure_client_id, "client_secret")
            if cache_key not in self._credentials:
                from azure.identity import ClientSecretCredential

                logger.info(
                    "collection_credential_strategy strategy=client_secret tenant_id=%s client_id=%s",
                    authority_tenant_id,
                    self.settings.azure_client_id,
                )
                self._credentials[cache_key] = ClientSecretCredential(
                    tenant_id=authority_tenant_id,
                    client_id=self.settings.azure_client_id,
                    client_secret=self.settings.azure_client_secret,
                )
            return self._credentials[cache_key]

        cache_key = (authority_tenant_id, "default", "local")
        if cache_key not in self._credentials:
            from azure.identity import DefaultAzureCredential

            logger.info(
                "collection_credential_strategy strategy=default_azure_credential tenant_id=%s",
                authority_tenant_id,
            )
            self._credentials[cache_key] = DefaultAzureCredential(
                exclude_workload_identity_credential=True,
                exclude_managed_identity_credential=True,
            )
        return self._credentials[cache_key]

    def _legacy_credential(self):
        if self.settings.collection_mode.lower() not in {"live", "auto"}:
            return None
        if not (
            self.settings.use_managed_identity
            or self.settings.azure_credentials_configured
        ):
            return None
        from azure.identity import DefaultAzureCredential

        return DefaultAzureCredential(
            managed_identity_client_id=self.settings.azure_client_id or None
        )

    def _read_assertion(self) -> str:
        token_path = self.settings.azure_federated_token_file
        if not token_path:
            raise StorageConfigurationError(
                "AZURE_FEDERATED_TOKEN_FILE is required for AKS Workload Identity"
            )
        try:
            assertion = Path(token_path).read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise StorageConfigurationError(
                f"Unable to read workload identity token: {exc}"
            ) from exc
        if not assertion:
            raise StorageConfigurationError(
                "AKS Workload Identity token file is empty"
            )
        return assertion
