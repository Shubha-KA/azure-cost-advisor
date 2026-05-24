"""Azure Resource Graph collector for disks and public IPs (mock-simulated)."""

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
        if not payload.get("unattachedDisks"):
            raise CollectorError(f"{self.collector_name}: unattachedDisks is empty")
        if not payload.get("publicIps"):
            raise CollectorError(f"{self.collector_name}: publicIps is empty")
        if not payload.get("resourceInventory"):
            raise CollectorError(f"{self.collector_name}: resourceInventory is empty")
        return payload

    def _count_records(self, validated: dict[str, Any]) -> int:
        return (
            len(validated["unattachedDisks"])
            + len(validated["publicIps"])
            + len(validated["resourceInventory"])
        )

    def _simulate_api_ingestion(self, validated: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        ingestion_id = f"{self.collector_name}-{now.strftime('%Y%m%d%H%M%S%f')}"

        return {
            **validated,
            "ingestion": {
                "ingestionId": ingestion_id,
                "ingestedAt": now.isoformat(),
                "collector": self.collector_name,
                "simulatedApi": True,
                "mockSources": [
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
            },
        }
