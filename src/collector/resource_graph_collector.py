"""Azure Resource Graph inventory collector with labeled cost estimates."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from src.collector.base import BaseCollector, CollectorError
from src.collector.schemas import (
    MockMetadata,
    PublicIpsPayload,
    ResourceGraphPayload,
    UnattachedDisksPayload,
)


class ResourceGraphCollector(BaseCollector[Any]):
    """
    Merges multiple Resource Graph mock query results:
    unattached disks, public IPs, and inventory.
    """

    collector_name = "resource_graph"
    mock_filename = "resource_graph_inventory.json"
    schema_model = dict  # type: ignore[assignment]
    output_prefix = "resource_graph"
    allow_mock_fallback = False

    def _load_mock_json(self) -> dict[str, Any]:
        disks_path = self.mock_data_dir / "unattached_disks.json"
        ips_path = self.mock_data_dir / "public_ips.json"
        inventory_path = self.mock_data_dir / self.mock_filename

        for path in (disks_path, ips_path, inventory_path):
            if not path.exists():
                raise CollectorError(
                    f"{self.collector_name}: required mock file missing: {path.name}"
                )

        disks = json.loads(disks_path.read_text(encoding="utf-8"))
        ips = json.loads(ips_path.read_text(encoding="utf-8"))
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))

        self._validate_sub_schemas(disks, ips, inventory)

        return {
            "metadata": disks["metadata"],
            "unattachedDisks": disks["data"],
            "publicIps": ips["publicIps"],
            "resourceInventory": inventory["data"],
        }

    def _validate_sub_schemas(
        self,
        disks: dict[str, Any],
        ips: dict[str, Any],
        inventory: dict[str, Any],
    ) -> None:
        try:
            UnattachedDisksPayload.model_validate(disks)
            PublicIpsPayload.model_validate(ips)
            ResourceGraphPayload.model_validate(inventory)
            self.logger.debug("%s sub-schema validation passed", self.collector_name)
        except ValidationError as exc:
            raise CollectorError(
                f"{self.collector_name}: sub-schema validation failed"
            ) from exc

    def _validate_schema(self, payload: dict[str, Any]) -> dict[str, Any]:
        MockMetadata.model_validate(payload["metadata"])
        if payload.get("unattachedDisks") is None:
            raise CollectorError(f"{self.collector_name}: unattachedDisks is missing")
        if payload.get("publicIps") is None:
            raise CollectorError(f"{self.collector_name}: publicIps is missing")
        if payload.get("resourceInventory") is None:
            raise CollectorError(f"{self.collector_name}: resourceInventory is missing")
        return payload

    def _count_records(self, validated: dict[str, Any]) -> int:
        return (
            len(validated["unattachedDisks"])
            + len(validated["publicIps"])
            + len(validated["resourceInventory"])
        )

    def _fetch_live_data(self) -> dict[str, Any]:
        from src.collector.auth import get_azure_credential
        from azure.mgmt.resourcegraph import ResourceGraphClient
        from azure.mgmt.resourcegraph.models import QueryRequest

        credential = self.credential or get_azure_credential()
        client = ResourceGraphClient(credential)
        sub_id = self.context.subscription_id
        subs = [sub_id]

        # 1. Unattached Disks
        disks_q = """
        Resources 
        | where type =~ 'microsoft.compute/disks' 
        | where properties.diskState == 'Unattached' 
        | project diskId=id, resourceGroup, diskName=name, location, diskSizeGb=toint(properties.diskSizeGB), sku=tostring(sku.name), managedBy=tostring(properties.managedBy)
        """
        disks_res = client.resources(QueryRequest(subscriptions=subs, query=disks_q))
        disks_data = []
        for d in disks_res.data:
            d["daysUnattached"] = 30
            d["monthlyCostEstimateUsd"] = float(d.get("diskSizeGb", 0)) * 0.15
            d["costBasis"] = "synthetic"
            d["costEstimateCurrency"] = "USD"
            d["costEstimateMethod"] = "disk_size_gb_x_0.15_usd"
            disks_data.append(d)

        # 2. Public IPs
        ips_q = """
        Resources 
        | where type =~ 'microsoft.network/publicipaddresses' 
        | project id, name, resourceGroup, location, ipAddress=tostring(properties.ipAddress), allocationMethod=tostring(properties.publicIPAllocationMethod), sku=tostring(sku.name), associated=isnotempty(properties.ipConfiguration), associatedResource=tostring(properties.ipConfiguration.id)
        """
        ips_res = client.resources(QueryRequest(subscriptions=subs, query=ips_q))
        ips_data = []
        for ip in ips_res.data:
            ip["monthlyCostEstimateUsd"] = 3.65 if not ip["associated"] else 0.0
            ip["costBasis"] = "synthetic" if not ip["associated"] else "unknown"
            ip["costEstimateCurrency"] = "USD" if not ip["associated"] else ""
            ip["costEstimateMethod"] = (
                "flat_3.65_usd_unassociated_public_ip"
                if not ip["associated"]
                else ""
            )
            ips_data.append(ip)

        # 3. Inventory
        inv_q = "Resources | project id, name, type, resourceGroup, location, properties | limit 1000"
        inv_res = client.resources(QueryRequest(subscriptions=subs, query=inv_q))
        
        inv_data = inv_res.data

        return {
            "metadata": {
                "subscriptionId": sub_id,
                "apiVersion": "2021-03-01",
                "generatedAt": datetime.now(timezone.utc).isoformat(),
                "source": "live"
            },
            "unattachedDisks": disks_data,
            "publicIps": ips_data,
            "resourceInventory": inv_data,
        }

    def _simulate_api_ingestion(self, validated: dict[str, Any], is_live: bool = False) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        ingestion_id = f"{self.collector_name}-{now.strftime('%Y%m%d%H%M%S%f')}"

        return {
            **validated,
            "ingestion": {
                "ingestionId": ingestion_id,
                "ingestedAt": now.isoformat(),
                "collector": self.collector_name,
                "simulatedApi": not is_live,
                "mockSources": None if is_live else [
                    "unattached_disks.json",
                    "public_ips.json",
                    "resource_graph_inventory.json",
                ],
                "subscriptionId": validated["metadata"].get("subscriptionId"),
            },
            "summary": {
                "unattachedDiskCount": len(validated["unattachedDisks"]),
                "unassociatedPublicIpCount": sum(
                    1 for ip in validated["publicIps"] if not ip.get("associated", True)
                ),
                "inventoryResourceCount": len(validated["resourceInventory"]),
                "totalOrphanedCostEstimateUsd": round(
                    sum(d.get("monthlyCostEstimateUsd", 0) for d in validated["unattachedDisks"])
                    + sum(
                        ip.get("monthlyCostEstimateUsd", 0)
                        for ip in validated["publicIps"]
                        if not ip.get("associated", True)
                    ),
                    2,
                ),
                "costBasis": "synthetic",
                "costEstimateCurrency": "USD",
            },
        }
