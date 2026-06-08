"""Azure Advisor recommendations collector (mock-simulated)."""

from __future__ import annotations

from typing import Any
from src.collector.base import BaseCollector
from src.collector.schemas import AdvisorRecommendationsPayload


class AdvisorCollector(BaseCollector[AdvisorRecommendationsPayload]):
    """Ingests Azure Advisor cost/security/performance recommendations."""

    collector_name = "advisor"
    mock_filename = "advisor_recommendations.json"
    schema_model = AdvisorRecommendationsPayload
    output_prefix = "advisor"

    def _count_records(self, validated: AdvisorRecommendationsPayload) -> int:
        return len(validated.recommendations)

    def _fetch_live_data(self) -> dict[str, Any]:
        from src.collector.auth import get_azure_credential
        from azure.mgmt.advisor import AdvisorManagementClient
        from datetime import datetime, timezone
        from typing import Any
        import re

        credential = get_azure_credential()
        sub_id = self.settings.azure_subscription_id
        client = AdvisorManagementClient(credential, sub_id)

        res = client.recommendations.list()
        
        recs = []
        for r in res:
            cat = r.category if isinstance(r.category, str) else (r.category.value if hasattr(r.category, "value") else str(r.category))
            if cat != "Cost":
                continue

            rg_match = re.search(r"/resourceGroups/([^/]+)/", r.resource_metadata.get("resourceId", "") if r.resource_metadata else "", re.IGNORECASE)
            resource_group = rg_match.group(1) if rg_match else "Unknown"

            savings = 0.0
            if r.extended_properties and "savingsAmount" in r.extended_properties:
                try:
                    savings = float(r.extended_properties["savingsAmount"])
                except ValueError:
                    pass

            recs.append({
                "recommendationId": r.id.split("/")[-1] if r.id else "unknown",
                "category": cat,
                "impact": r.impact if isinstance(r.impact, str) else (r.impact.value if hasattr(r.impact, "value") else str(r.impact)),
                "impactedField": r.impacted_field or "target_resource_id",
                "problem": r.short_description.problem if r.short_description else "Unknown issue",
                "solution": r.short_description.solution if r.short_description else "Review recommendation",
                "resourceId": r.resource_metadata.get("resourceId", "Unknown") if r.resource_metadata else "Unknown",
                "resourceGroup": resource_group,
                "resourceName": r.impacted_value or "Unknown",
                "monthlySavingsUsd": savings,
                "lastUpdated": r.last_updated.isoformat() if hasattr(r, "last_updated") and r.last_updated else datetime.now(timezone.utc).isoformat()
            })

        if not recs:
            recs.append({
                "recommendationId": "none",
                "category": "Cost",
                "impact": "Low",
                "impactedField": "target_resource_id",
                "problem": "No recommendations",
                "solution": "Your environment is fully optimized.",
                "resourceId": "none",
                "resourceGroup": "none",
                "resourceName": "none",
                "monthlySavingsUsd": 0.0,
                "lastUpdated": datetime.now(timezone.utc).isoformat()
            })

        return {
            "metadata": {
                "subscriptionId": sub_id,
                "apiVersion": "2020-01-01",
                "generatedAt": datetime.now(timezone.utc).isoformat(),
                "source": "live"
            },
            "recommendations": recs
        }

    def _apply_ingestion_transforms(self, body: dict) -> None:
        recs = body.get("recommendations", [])
        body["summary"] = {
            "totalRecommendations": len(recs),
            "highImpact": sum(1 for r in recs if r.get("impact") == "High"),
            "totalMonthlySavingsUsd": round(
                sum(r.get("monthlySavingsUsd", 0) for r in recs), 2
            ),
        }
