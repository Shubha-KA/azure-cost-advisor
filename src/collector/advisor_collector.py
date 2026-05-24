"""Azure Advisor recommendations collector (mock-simulated)."""

from __future__ import annotations

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

    def _apply_ingestion_transforms(self, body: dict) -> None:
        recs = body.get("recommendations", [])
        body["summary"] = {
            "totalRecommendations": len(recs),
            "highImpact": sum(1 for r in recs if r.get("impact") == "High"),
            "totalMonthlySavingsUsd": round(
                sum(r.get("monthlySavingsUsd", 0) for r in recs), 2
            ),
        }
