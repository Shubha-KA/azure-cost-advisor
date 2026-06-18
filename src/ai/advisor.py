"""Conversational FinOps assistant with RAG and rule-based fallback."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.ai.inventory import ResourceGraphInventoryService
from src.ai.rag import RAGError, RAGPipeline
from src.ai.router import route_query
from src.config import Settings, get_settings
from src.domain.context import OperationContext
from src.domain.models import Recommendation
from src.money import format_money, format_money_totals
from src.storage.factory import create_storage_provider

logger = logging.getLogger(__name__)


class FinOpsAdvisor:
    """
    High-level advisor API for chat and recommendations.

    Uses Azure OpenAI + FAISS RAG when configured; otherwise rule-based responses
    formatted for FinOps engineers.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        tenant_id: str | None = None,
        subscription_ids: list[str] | None = None,
        credential=None,
        search_provider=None,
        llm=None,
    ) -> None:
        self.settings = settings or get_settings()
        self.storage = create_storage_provider(self.settings)
        self.tenant_id = tenant_id or self.settings.effective_tenant_id
        self.subscription_ids = subscription_ids or [
            self.settings.effective_subscription_id
        ]
        self.credential = credential
        self.rag = RAGPipeline(
            self.settings,
            storage=self.storage,
            search_provider=search_provider,
            llm=llm,
        )

    def build_index(self, rebuild: bool = False) -> int:
        if not self.settings.openai_configured:
            logger.warning("Skipping index build — Azure OpenAI not configured")
            return 0
        return sum(
            self.rag.build_index(
                rebuild=rebuild,
                tenant_id=self.tenant_id,
                subscription_id=subscription_id,
            )
            for subscription_id in self.subscription_ids
        )

    def ask(self, question: str, chat_history: str = "") -> str:
        """Answer a FinOps question using RAG, live Azure inventory, or rule‑based fallback.

        The method first detects inventory‑type queries (resource groups, VMs, disks, public IPs) and
        performs a live Azure Resource Graph request via `ResourceGraphCollector`. If that fails
        it falls back to the RAG pipeline when OpenAI is configured, and finally to the existing
        rule‑based response.
        """
        # 1️⃣ Detect inventory‑type questions that should query Azure live via Resource Graph.
        route = route_query(question)
        if route == "live_inventory":
            try:
                return self._handle_live_inventory(question)
            except Exception as exc:
                logger.warning("Live inventory lookup failed: %s", exc)
                return (
                    "Live Azure inventory query failed.\n\n"
                    "Source: Azure Resource Graph (LIVE)\n"
                    f"Subscription scope: {', '.join(self.subscription_ids)}\n"
                    f"Error: {exc}"
                )

        # 2️⃣ If Azure OpenAI is configured, use the RAG pipeline (FAISS index).
        if self.settings.openai_configured:
            try:
                result = self.rag.invoke(
                    question,
                    chat_history=chat_history,
                    tenant_id=self.tenant_id,
                    subscription_id=self.subscription_ids[0],
                    operation=route,
                )
                return result.get("answer", self._rule_based_answer(question))
            except RAGError as exc:
                logger.warning("RAG failed, using rule‑based fallback: %s", exc)

        # 3️⃣ Default: rule‑based responses using processed CSV data.
        return self._rule_based_answer(question)

    def generate_recommendations(self) -> dict[str, Any]:
        """Generate and persist a FinOps recommendations report."""
        if self.settings.openai_configured:
            try:
                result = self.rag.generate_recommendations(
                    tenant_id=self.tenant_id,
                    subscription_id=self.subscription_ids[0],
                )
                output = {
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "source": result.get("source", "azure_openai_rag"),
                    "source_system": "Azure OpenAI + AI Search",
                    "source_timestamp": datetime.now(timezone.utc).isoformat(),
                    "collection_run_id": f"recommendations-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
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

    def _handle_live_inventory(self, question: str) -> str:
        result = ResourceGraphInventoryService(
            self.settings,
            tenant_id=self.tenant_id,
            subscription_ids=self.subscription_ids,
            credential=self.credential,
        ).query(question)
        rows = result["records"]
        lines = [
            f"Live Azure inventory: {len(rows)} result(s).",
            "",
            f"Source: {result['source_system']} (LIVE)",
            f"Timestamp: {result['timestamp']}",
            f"Subscription scope: {', '.join(result['subscription_scope'])}",
            f"Result count: {result['result_count']}",
            f"Collection run: {result['collection_run_id']}",
            "",
        ]
        if not rows:
            lines.append("No matching Azure resources were returned.")
        for row in rows[:50]:
            lines.append(
                f"- {row.get('name', 'unknown')} | {row.get('type', 'unknown')} | "
                f"{row.get('resourceGroup', '')} | {row.get('location', '')}"
            )
        if len(rows) > 50:
            lines.append(f"- ... {len(rows) - 50} additional results omitted")
        return "\n".join(lines)

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
            f"Monthly cost: {format_money(top['monthly_cost'], top.get('estimated_cost_currency', 'USD'))}.\n\n"
            f"Recommendation:\n"
            f"{top['recommendation'] or 'Resize or deallocate the VM.'}\n\n"
            f"Estimated savings:\n"
            f"{format_money(top['estimated_savings'], top.get('savings_currency', 'USD'))}/month."
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
            f"Actual spend: {format_money(top.get('cost_amount', top.get('cost_usd', 0)), top.get('currency', 'USD'))} vs expected "
            f"{format_money(top.get('expected_cost_amount', top.get('expected_cost_usd', 0)), top.get('currency', 'USD'))}.\n\n"
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
        savings_totals = (
            flagged.groupby("savings_currency")["estimated_savings"].sum().to_dict()
            if not flagged.empty and "savings_currency" in flagged
            else (
                {"USD": float(flagged["estimated_savings"].sum())}
                if not flagged.empty
                else {}
            )
        )

        lines = [
            f"Total estimated monthly savings across {len(flagged)} resources: {format_money_totals(savings_totals)}.",
            "",
            "Top opportunities:",
        ]
        for i, (_, row) in enumerate(flagged.head(5).iterrows(), 1):
            lines.append(
                f"{i}. {row['resource_name']} ({row['resource_type']}) — "
                f"{format_money(row['estimated_savings'], row.get('savings_currency', 'USD'))}/month — {row['recommendation']}"
            )

        if flagged.empty:
            lines.append("No waste flags in current data. Review advisor recommendations.")

        lines.extend(
            [
                "",
                "Recommendation:",
                "Prioritize HIGH waste_level resources and delete unattached disks first.",
                "",
                f"Estimated savings:\n{format_money_totals(savings_totals)}/month.",
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
            f"{format_money(row.get('estimated_savings', 0), row.get('savings_currency', 'USD'))}/month."
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
            f"**Total spend:** {format_money_totals(summary.get('total_cost', {'USD': summary.get('total_cost_usd', 0)}))}",
            f"**Est. savings:** {format_money_totals(summary.get('total_estimated_savings', {'USD': summary.get('total_estimated_savings_usd', 0)}))}/month",
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
                        f"- Estimated savings: {format_money(row['estimated_savings'], row.get('savings_currency', 'USD'))}/month",
                        "",
                    ]
                )

        for a in anomalies.get("anomalies", [])[:3]:
            lines.append(f"- **Anomaly:** {a.get('description', '')}")

        output = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "rule_based",
            "source_system": "Processed resource analysis",
            "source_timestamp": datetime.now(timezone.utc).isoformat(),
            "collection_run_id": f"recommendations-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
            "recommendations": "\n".join(lines),
            "context_documents": 0,
        }
        self._persist_recommendations(output)
        return output

    def _persist_recommendations(self, output: dict[str, Any]) -> Path:
        context = self._current_context()
        output.update(context.document_fields())
        recommendation = Recommendation(
            **context.document_fields(),
            content=str(output.get("recommendations", "")),
            title="FinOps recommendations",
            sourceSystem=str(output.get("source_system", "unknown")),
            sourceTimestamp=str(output.get("source_timestamp", "")),
            evidence={
                "source": output.get("source", ""),
                "contextDocuments": output.get("context_documents", 0),
            },
        )
        self.storage.recommendations.upsert_many(
            context.tenant_id, [recommendation]
        )
        path = self.settings.processed_path / "recommendations_latest.json"
        self.settings.processed_path.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(output, indent=2), encoding="utf-8")
        return path

    def _current_context(self) -> OperationContext:
        metadata = self.storage.processing_metadata.list_latest(
            self.tenant_id, self.subscription_ids[0]
        )
        processing = next(
            (
                item
                for item in metadata
                if item.get("metadataType") == "processingRun"
            ),
            None,
        )
        if processing:
            return OperationContext(
                tenantId=self.tenant_id,
                subscriptionId=self.subscription_ids[0],
                collectionRunId=processing["collectionRunId"],
                processingRunId=processing["processingRunId"],
                correlationId=processing["correlationId"],
                schemaVersion=1,
            )
        resources = self.settings.processed_path / "resources_latest.csv"
        if resources.exists():
            frame = pd.read_csv(resources, nrows=1)
            if not frame.empty and all(
                key in frame.columns
                for key in (
                    "tenant_id",
                    "subscription_id",
                    "collection_run_id",
                    "processing_run_id",
                    "correlation_id",
                )
            ):
                row = frame.iloc[0]
                return OperationContext(
                    tenantId=str(row["tenant_id"]),
                    subscriptionId=str(row["subscription_id"]),
                    collectionRunId=str(row["collection_run_id"]),
                    processingRunId=str(row["processing_run_id"]),
                    correlationId=str(row["correlation_id"]),
                    schemaVersion=1,
                )
        return OperationContext.create(
            self.settings.effective_tenant_id,
            self.settings.effective_subscription_id,
        )

    def load_latest_recommendations(self) -> dict[str, Any]:
        path = self.settings.processed_path / "recommendations_latest.json"
        if not path.exists():
            return {
                "recommendations": "No recommendations generated yet.",
                "source": "none",
            }
        return json.loads(path.read_text(encoding="utf-8"))
