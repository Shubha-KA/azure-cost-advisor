"""Direct, read-only Azure Resource Graph inventory queries for chat."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from azure.mgmt.resourcegraph import ResourceGraphClient
from azure.mgmt.resourcegraph.models import QueryRequest

from src.config import Settings


class InventoryQueryError(RuntimeError):
    pass


RESOURCE_TYPES = {
    "vm": "microsoft.compute/virtualmachines",
    "aks": "microsoft.containerservice/managedclusters",
    "public_ip": "microsoft.network/publicipaddresses",
    "storage": "microsoft.storage/storageaccounts",
    "disk": "microsoft.compute/disks",
    "app_service": "microsoft.web/sites",
    "key_vault": "microsoft.keyvault/vaults",
    "vnet": "microsoft.network/virtualnetworks",
    "gateway": "microsoft.network/applicationgateways",
}


def inventory_intent(question: str) -> str:
    q = question.lower()
    checks = [
        ("resource_group", ("resource group", "resource groups")),
        ("aks", ("aks", "kubernetes", "managed cluster")),
        ("public_ip", ("public ip", "public ips")),
        ("storage", ("storage account", "storage accounts")),
        ("disk", ("disk", "disks")),
        ("app_service", ("app service", "web app", "web apps")),
        ("key_vault", ("key vault", "key vaults")),
        ("vnet", ("vnet", "virtual network")),
        ("gateway", ("application gateway",)),
        ("vm", ("virtual machine", "virtual machines", "vms")),
    ]
    for intent, terms in checks:
        if any(term in q for term in terms):
            return intent
    if any(term in q for term in ("resource", "inventory", "what is deployed")):
        return "all"
    raise InventoryQueryError("Question is not a supported inventory query")


def is_inventory_question(question: str) -> bool:
    try:
        inventory_intent(question)
        return True
    except InventoryQueryError:
        return False


class ResourceGraphInventoryService:
    def __init__(
        self,
        settings: Settings,
        *,
        tenant_id: str | None = None,
        subscription_ids: list[str] | None = None,
        credential=None,
        client=None,
    ) -> None:
        self.settings = settings
        self.tenant_id = tenant_id or settings.effective_tenant_id
        self.subscription_ids = subscription_ids or [
            settings.effective_subscription_id
        ]
        if client is not None:
            self.client = client
        else:
            if credential is None:
                if settings.entra_auth_enabled:
                    raise InventoryQueryError(
                        "A tenant-scoped credential is required for live inventory "
                        "queries in Entra authentication mode"
                    )
                from src.collector.auth import get_azure_credential

                credential = get_azure_credential()
            self.client = ResourceGraphClient(credential)

    def query(self, question: str) -> dict[str, Any]:
        intent = inventory_intent(question)
        if intent == "resource_group":
            kql = (
                "ResourceContainers "
                "| where type =~ 'microsoft.resources/subscriptions/resourcegroups' "
                "| project name, type, resourceGroup=name, location "
                "| order by name asc"
            )
        elif intent == "all":
            kql = (
                "Resources | project name, type, resourceGroup, location, id "
                "| order by type asc, name asc | limit 200"
            )
        else:
            kql = (
                f"Resources | where type =~ '{RESOURCE_TYPES[intent]}' "
                "| project name, type, resourceGroup, location, id "
                "| order by name asc | limit 200"
            )
        response = self.client.resources(
            QueryRequest(
                subscriptions=self.subscription_ids,
                query=kql,
            )
        )
        now = datetime.now(timezone.utc)
        records = list(response.data or [])
        return {
            "source": "Azure Resource Graph",
            "source_system": "Azure Resource Graph",
            "timestamp": now.isoformat(),
            "source_timestamp": now.isoformat(),
            "collection_run_id": f"inventory-{now.strftime('%Y%m%d%H%M%S%f')}",
            "tenant_id": self.tenant_id,
            "subscription_scope": self.subscription_ids,
            "subscription_id": ",".join(self.subscription_ids),
            "result_count": len(records),
            "records": records,
        }
