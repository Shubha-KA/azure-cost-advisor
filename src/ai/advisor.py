"""Conversational FinOps assistant with RAG and rule-based fallback."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.ai.rag import RAGError, RAGPipeline
from src.config import Settings, get_settings

logger = logging.getLogger(__name__)


class FinOpsAdvisor:
    """
    High-level advisor API for chat and recommendations.

    Uses Azure OpenAI + FAISS RAG when configured; otherwise rule-based responses
    formatted for FinOps engineers.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.rag = RAGPipeline(self.settings)

    def build_index(self, rebuild: bool = False) -> int:
        if not self.settings.openai_configured:
            logger.warning("Skipping index build — Azure OpenAI not configured")
            return 0
        return self.rag.build_index(rebuild=rebuild)

    def ask(self, question: str, chat_history: str = "") -> str:
        """Answer a FinOps question using RAG or rule-based logic."""
        if self.settings.openai_configured:
            try:
                result = self.rag.invoke(question, chat_history=chat_history)
                return result.get("answer", self._rule_based_answer(question))
            except RAGError as exc:
                logger.warning("RAG failed, using rule-based fallback: %s", exc)

        return self._rule_based_answer(question)

    def generate_recommendations(self) -> dict[str, Any]:
        """Generate and persist a FinOps recommendations report."""
        if self.settings.openai_configured:
            try:
                if not (self.settings.embeddings_path / "faiss_index" / "index.faiss").exists():
                    self.build_index(rebuild=True)
                result = self.rag.generate_recommendations()
                output = {
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "source": result.get("source", "azure_openai_rag"),
                    "recommendations": result.get("answer", ""),
                    "context_documents": len(result.get("context", [])),
                }
                self._persist_recommendations(output)
                return output
            except RAGError as exc:
                logger.warning("RAG recommendations failed: %s", exc)

        return self._rule_based_recommendations()

    def _load_context(self) -> dict[str, Any]:
        processed = self.settings.processed_path
        context: dict[str, Any] = {}

        resources_path = processed / "resources_latest.csv"
        if resources_path.exists():
            context["resources"] = pd.read_csv(resources_path)

        for key, filename in [
            ("waste", "waste_findings_latest.json"),
            ("anomalies", "anomalies_latest.json"),
            ("summary", "summary_latest.json"),
        ]:
            path = processed / filename
            if path.exists():
                context[key] = json.loads(path.read_text(encoding="utf-8"))

        return context

    def _rule_based_answer(self, question: str) -> str:
        ctx = self._load_context()
        q = question.lower()
        resources: pd.DataFrame = ctx.get("resources", pd.DataFrame())

        if resources.empty:
            return (
                "No processed cost data is available.\n\n"
                "Recommendation:\n"
                "Run the data pipeline first (`python -m src.collector.run` "
                "then `python -m src.processor.run`)."
            )

        if "waste" in q and ("vm" in q or "virtual" in q or "money" in q or "most" in q):
            return self._answer_top_vm_waste(resources)

        if "spike" in q or "anomal" in q or "why" in q and "cost" in q:
            return self._answer_cost_spike(ctx.get("anomalies", {}))

        if "saving" in q or "opportunit" in q or "biggest" in q:
            return self._answer_savings_opportunities(resources, ctx.get("waste", {}))

        flagged = resources[resources["waste_level"] != "NONE"]
        if not flagged.empty:
            row = flagged.sort_values("estimated_savings", ascending=False).iloc[0]
            return self._format_resource_response(row)

        return (
            "I can help analyze Azure costs, waste, and anomalies.\n\n"
            "Try asking:\n"
            "- Which VM wastes the most money?\n"
            "- Why did costs spike?\n"
            "- What are my biggest savings opportunities?"
        )

    def _answer_top_vm_waste(self, resources: pd.DataFrame) -> str:
        vms = resources[
            (resources["resource_type"] == "Virtual Machine")
            & (resources["waste_level"] != "NONE")
        ]
        if vms.empty:
            vms = resources[resources["resource_type"] == "Virtual Machine"]

        if vms.empty:
            return "No virtual machine data found in the current analysis."

        top = vms.sort_values("estimated_savings", ascending=False).iloc[0]
        cpu = float(top["cpu_avg_percent"])
        diagnosis = (
            "This VM appears oversized."
            if cpu < 10
            else "This VM shows waste indicators based on utilization and cost."
        )
        return (
            f"{diagnosis}\n"
            f"Resource: {top['resource_name']}\n"
            f"CPU remained below {cpu:.0f}%.\n"
            f"Monthly cost: ${float(top['monthly_cost']):.2f}.\n\n"
            f"Recommendation:\n"
            f"{top['recommendation'] or 'Resize or deallocate the VM.'}\n\n"
            f"Estimated savings:\n"
            f"${float(top['estimated_savings']):.0f}/month."
        )

    def _answer_cost_spike(self, anomalies: dict) -> str:
        items = anomalies.get("anomalies", [])
        if not items:
            return (
                "No cost anomalies were detected in the current period.\n\n"
                "Recommendation:\n"
                "Review daily cost trends in the Overview tab and configure "
                "Cost Management budget alerts."
            )

        top = items[0]
        return (
            f"Costs spiked on {top.get('date', 'unknown date')}.\n"
            f"{top.get('description', 'Daily spend exceeded the 7-day average threshold.')}\n"
            f"Actual spend: ${top.get('cost_usd', 0):.2f} vs expected "
            f"${top.get('expected_cost_usd', 0):.2f}.\n\n"
            f"Recommendation:\n"
            "Investigate Databricks jobs, scaling events, and non-production "
            "resources left running over the spike date.\n\n"
            f"Estimated savings:\n"
            "Varies — typically 15–40% of spike amount if root cause is addressed."
        )

    def _answer_savings_opportunities(
        self, resources: pd.DataFrame, waste: dict
    ) -> str:
        flagged = resources[resources["waste_level"] != "NONE"].sort_values(
            "estimated_savings", ascending=False
        )
        total = float(flagged["estimated_savings"].sum()) if not flagged.empty else 0.0

        lines = [
            f"Total estimated monthly savings across {len(flagged)} resources: ${total:.0f}.",
            "",
            "Top opportunities:",
        ]
        for i, (_, row) in enumerate(flagged.head(5).iterrows(), 1):
            lines.append(
                f"{i}. {row['resource_name']} ({row['resource_type']}) — "
                f"${float(row['estimated_savings']):.0f}/month — {row['recommendation']}"
            )

        if flagged.empty:
            lines.append("No waste flags in current data. Review advisor recommendations.")

        lines.extend(
            [
                "",
                "Recommendation:",
                "Prioritize HIGH waste_level resources and delete unattached disks first.",
                "",
                f"Estimated savings:\n${total:.0f}/month.",
            ]
        )
        return "\n".join(lines)

    @staticmethod
    def _format_resource_response(row: pd.Series) -> str:
        cpu = float(row.get("cpu_avg_percent", 0))
        diagnosis = (
            "This VM appears oversized."
            if row.get("resource_type") == "Virtual Machine" and cpu < 10
            else f"This {row.get('resource_type', 'resource')} has been flagged for waste."
        )
        return (
            f"{diagnosis}\n"
            f"CPU remained below {cpu:.0f}%.\n\n"
            f"Recommendation:\n"
            f"{row.get('recommendation', 'Review and remediate.')}\n\n"
            f"Estimated savings:\n"
            f"${float(row.get('estimated_savings', 0)):.0f}/month."
        )

    def _rule_based_recommendations(self) -> dict[str, Any]:
        ctx = self._load_context()
        summary = ctx.get("summary", {})
        waste = ctx.get("waste", {})
        anomalies = ctx.get("anomalies", {})
        resources: pd.DataFrame = ctx.get("resources", pd.DataFrame())

        lines = [
            "## FinOps Recommendations (Rule-Based Mode)",
            "",
            f"**Total spend:** ${summary.get('total_cost_usd', 0):,.2f}",
            f"**Est. savings:** ${summary.get('total_estimated_savings_usd', 0):,.2f}/month",
            "",
        ]

        if not resources.empty:
            flagged = resources[resources["waste_level"] != "NONE"].sort_values(
                "estimated_savings", ascending=False
            )
            for i, (_, row) in enumerate(flagged.head(7).iterrows(), 1):
                lines.extend(
                    [
                        f"### {i}. {row['resource_name']} ({row['resource_type']})",
                        f"- Waste level: {row['waste_level']}",
                        f"- Recommendation: {row['recommendation']}",
                        f"- Estimated savings: ${float(row['estimated_savings']):.0f}/month",
                        "",
                    ]
                )

        for a in anomalies.get("anomalies", [])[:3]:
            lines.append(f"- **Anomaly:** {a.get('description', '')}")

        output = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "rule_based",
            "recommendations": "\n".join(lines),
            "context_documents": 0,
        }
        self._persist_recommendations(output)
        return output

    def _persist_recommendations(self, output: dict[str, Any]) -> Path:
        path = self.settings.processed_path / "recommendations_latest.json"
        self.settings.processed_path.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(output, indent=2), encoding="utf-8")
        return path

    def load_latest_recommendations(self) -> dict[str, Any]:
        path = self.settings.processed_path / "recommendations_latest.json"
        if not path.exists():
            return {
                "recommendations": "No recommendations generated yet.",
                "source": "none",
            }
        return json.loads(path.read_text(encoding="utf-8"))
