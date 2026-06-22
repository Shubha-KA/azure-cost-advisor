"""Conversational FinOps assistant with RAG and rule-based fallback."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.ai.inventory import ResourceGraphInventoryService
from src.ai.prompts import FINOPS_RECOMMENDATION_ANALYSIS_PROMPT
from src.ai.rag import RAGError, RAGPipeline
from src.ai.router import classify_intent
from src.config import Settings, get_settings
from src.domain.context import OperationContext
from src.domain.models import Recommendation
from src.money import format_money, format_money_totals
from src.repositories.errors import StorageConfigurationError
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

    def _with_debug(self, answer: str, debug_lines: list[str]) -> str:
        if not self.settings.ai_debug_mode:
            return answer
        clean_debug = [line for line in debug_lines if line]
        if not clean_debug:
            return answer
        return "\n".join([answer.rstrip(), "", "Debug Details", *clean_debug])

    def ask(self, question: str, chat_history: str = "") -> str:
        """Answer a FinOps question using RAG, live Azure inventory, or rule‑based fallback.

        The method first detects inventory‑type queries (resource groups, VMs, disks, public IPs) and
        performs a live Azure Resource Graph request via `ResourceGraphCollector`. If that fails
        it falls back to the RAG pipeline when OpenAI is configured, and finally to the existing
        rule‑based response.
        """
        # 1️⃣ Detect inventory‑type questions that should query Azure live via Resource Graph.
        classification = classify_intent(question)
        route = classification.route
        if route == "live_inventory":
            try:
                return self._handle_live_inventory(question)
            except Exception as exc:
                logger.warning("Live inventory lookup failed: %s", exc)
                return self._with_debug(
                    "I could not retrieve the deployed resource inventory right now. "
                    "Please try again, or refresh the subscription connection.",
                    [
                        "Live Azure inventory query failed",
                        "Source: Azure Resource Graph (LIVE)",
                        f"Subscription scope: {', '.join(self.subscription_ids)}",
                        f"Error: {exc}",
                    ],
                )

        # 2️⃣ If Azure OpenAI is configured, use the RAG pipeline (FAISS index).
        if route == "cost_analysis":
            return self._answer_cost_analysis(question, classification)

        if route == "recommendation":
            return self._answer_recommendation_query(question, classification)

        if route == "idle_resources":
            return self._answer_idle_resources_query(question, classification)

        if route == "utilization":
            return self._answer_utilization_query(question, classification)

        if route in {"knowledge_advisory", "general_rag"}:
            return self._answer_knowledge_advisory_query(
                question, classification, chat_history
            )

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
            except (RAGError, StorageConfigurationError) as exc:
                logger.warning("RAG failed, using rule‑based fallback: %s", exc)

        # 3️⃣ Default: rule‑based responses using processed CSV data.
        return self._rule_based_answer(question)

    def _answer_knowledge_advisory_query(
        self, question: str, classification: Any, chat_history: str = ""
    ) -> str:
        context = self._load_repository_context()
        structured_facts = self._structured_facts_for_question(question, context)
        try:
            result = self.rag.invoke_hybrid(
                question,
                structured_facts=structured_facts,
                chat_history=chat_history,
                tenant_id=self.tenant_id,
                subscription_id=self.subscription_ids[0],
                operation=classification.route,
            )
            return self._with_debug(
                result.get("answer", "").strip() or self._rule_based_answer(question),
                [
                    f"Detected intent: {classification.intent}",
                    f"Route selected: {classification.route}",
                    "Retrieval source: Azure AI Search + Cosmos structured facts",
                    f"Retrieved documents: {len(result.get('context', []))}",
                    f"Search latency ms: {round(result.get('search_latency_ms', 0), 2)}",
                ],
            )
        except (RAGError, StorageConfigurationError) as exc:
            logger.warning("Hybrid RAG failed, using structured fallback: %s", exc)
            return self._with_debug(
                self._structured_advisory_fallback(question, context),
                [
                    f"Detected intent: {classification.intent}",
                    f"Route selected: {classification.route}",
                    "Hybrid RAG failed before completion",
                    f"Error: {exc}",
                ],
            )

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
        else:
            rows = []
            for subscription_id in self.subscription_ids:
                rows.extend(
                    item.model_dump(mode="json")
                    for item in self.storage.resources.list_latest(
                        self.tenant_id, subscription_id
                    )
                )
            if rows:
                context["resources"] = pd.DataFrame(rows)

        for key, filename in [
            ("waste", "waste_findings_latest.json"),
            ("anomalies", "anomalies_latest.json"),
            ("summary", "summary_latest.json"),
        ]:
            path = processed / filename
            if path.exists():
                context[key] = json.loads(path.read_text(encoding="utf-8"))

        if "summary" not in context:
            for subscription_id in self.subscription_ids:
                metadata = self.storage.processing_metadata.list_latest(
                    self.tenant_id, subscription_id
                )
                processing = next(
                    (
                        item
                        for item in metadata
                        if item.get("metadataType") == "processingRun"
                        and item.get("summary")
                    ),
                    None,
                )
                if processing:
                    context["summary"] = processing["summary"]
                    break

        recommendations = []
        for subscription_id in self.subscription_ids:
            recommendations.extend(
                item.model_dump(mode="json")
                for item in self.storage.recommendations.list_latest(
                    self.tenant_id, subscription_id
                )
            )
        if recommendations:
            context["recommendations"] = recommendations

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
            "Deployed Resources",
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
        return self._with_debug(
            "\n".join(lines),
            [
                f"Source: {result['source_system']} (LIVE)",
                f"Timestamp: {result['timestamp']}",
                f"Subscription scope: {', '.join(result['subscription_scope'])}",
                f"Result count: {result['result_count']}",
                f"Collection run: {result['collection_run_id']}",
            ],
        )

    def _load_repository_context(self) -> dict[str, list[dict[str, Any]]]:
        context: dict[str, list[dict[str, Any]]] = {
            "costFacts": [],
            "resources": [],
            "recommendations": [],
            "advisorFindings": [],
        }
        for subscription_id in self.subscription_ids:
            context["costFacts"].extend(
                item.model_dump(mode="json")
                for item in self.storage.cost_facts.list_latest(
                    self.tenant_id, subscription_id
                )
            )
            context["resources"].extend(
                item.model_dump(mode="json")
                for item in self.storage.resources.list_latest(
                    self.tenant_id, subscription_id
                )
            )
            context["recommendations"].extend(
                item.model_dump(mode="json")
                for item in self.storage.recommendations.list_latest(
                    self.tenant_id, subscription_id
                )
            )
            advisor_payload = self.storage.raw_payloads.load_latest(
                self.tenant_id, subscription_id, "advisor"
            )
            if advisor_payload:
                context["advisorFindings"].extend(
                    advisor_payload.get("recommendations", [])
                )
        return context

    def _structured_facts_for_question(
        self, question: str, context: dict[str, list[dict[str, Any]]]
    ) -> str:
        q = question.lower()
        costs_by_id = self._cost_totals_by_resource(context["costFacts"])
        resources_by_id = self._resources_by_id(context["resources"])
        top_costs = self._top_cost_resources(costs_by_id, resources_by_id, limit=8)

        focus_terms = {
            term
            for term in ("aks", "kubernetes", "network", "networking", "public ip", "vm", "virtual machine")
            if term in q
        }
        if focus_terms:
            focused = []
            for item in top_costs:
                haystack = f"{item.get('resource_name', '')} {item.get('resource_type', '')}".lower()
                if any(term in haystack for term in focus_terms):
                    focused.append(item)
            if focused:
                top_costs = focused + [item for item in top_costs if item not in focused]

        recommendations_by_id: dict[str, list[dict[str, Any]]] = {}
        for recommendation in context["recommendations"]:
            resource_id = self._normalize_resource_id(
                recommendation.get("resource_id") or recommendation.get("resourceId")
            )
            if resource_id:
                recommendations_by_id.setdefault(resource_id, []).append(recommendation)

        lines = [
            f"Tenant: {self.tenant_id}",
            f"Subscription: {self.subscription_ids[0] if self.subscription_ids else ''}",
            "",
            "Top cost resources from costFacts:",
        ]
        for item in top_costs[:8]:
            recs = recommendations_by_id.get(item["resource_id"], [])
            rec_text = ""
            if recs:
                rec = recs[0]
                rec_text = (
                    f"; recommendation: {rec.get('content') or rec.get('title')}; "
                    f"estimated savings {format_money(float(rec.get('estimated_savings') or rec.get('estimatedSavings') or 0), rec.get('currency') or item.get('currency') or '')}/month"
                )
            lines.append(
                f"- {item['resource_name']} ({item['resource_type']}), "
                f"resource group {item.get('resource_group') or 'unknown'}, "
                f"observed cost {format_money(item['cost'], item.get('currency') or '')}"
                f"{rec_text}"
            )

        idle_or_savings = []
        for resource in context["resources"]:
            recommendation = str(
                resource.get("recommendation")
                or (resource.get("attributes") or {}).get("recommendation")
                or ""
            )
            waste_level = str(resource.get("waste_level") or resource.get("wasteLevel") or "")
            savings = float(resource.get("estimated_savings") or resource.get("estimatedSavings") or 0)
            if recommendation or waste_level.upper() not in {"", "NONE"} or savings > 0:
                idle_or_savings.append((savings, resource, recommendation, waste_level))

        if idle_or_savings:
            lines.extend(["", "Optimization and waste signals from resourceFacts:"])
            for savings, resource, recommendation, waste_level in sorted(
                idle_or_savings, key=lambda item: item[0], reverse=True
            )[:8]:
                lines.append(
                    f"- {resource.get('resource_name') or resource.get('resourceName')} "
                    f"({resource.get('resource_type') or resource.get('resourceType')}): "
                    f"waste level {waste_level or 'unknown'}, "
                    f"recommendation {recommendation or 'review'}, "
                    f"estimated savings {format_money(savings, resource.get('savings_currency') or resource.get('savingsCurrency') or '')}/month"
                )

        if context.get("advisorFindings"):
            lines.extend(["", "Azure Advisor findings:"])
            for finding in context["advisorFindings"][:6]:
                lines.append(
                    f"- {finding.get('resourceName') or finding.get('impactedValue') or 'resource'}: "
                    f"{finding.get('problem') or finding.get('solution') or finding.get('recommendationId')}"
                )

        return "\n".join(lines)

    def _structured_advisory_fallback(
        self, question: str, context: dict[str, list[dict[str, Any]]]
    ) -> str:
        facts = self._structured_facts_for_question(question, context)
        if not facts.strip():
            return (
                "I do not have enough collected subscription facts to answer this advisory question yet. "
                "Run collection and processing, then retry."
            )
        return (
            "I can answer from the collected subscription facts, but the Azure AI Search knowledge layer "
            "is not available right now.\n\n"
            "Current grounded facts:\n"
            f"{facts}"
        )

    def _answer_cost_analysis(self, question: str, classification: Any) -> str:
        context = self._load_repository_context()
        facts = context["costFacts"]
        resources = context["resources"]
        recommendations = context["recommendations"]

        if not facts:
            return self._with_debug(
                "Cost analysis could not run because no costFacts are available for "
                "the selected subscription.",
                [
                    f"Detected intent: {classification.intent}",
                    "Route selected: cost_analysis",
                    "Retrieval source: costFacts repository",
                ],
            )

        resources_by_id = {
            self._normalize_resource_id(item.get("resource_id") or item.get("resourceId")): item
            for item in resources
            if item.get("resource_id") or item.get("resourceId")
        }
        recommendations_by_id: dict[str, list[dict[str, Any]]] = {}
        for item in recommendations:
            resource_id = self._normalize_resource_id(
                item.get("resource_id") or item.get("resourceId")
            )
            if resource_id:
                recommendations_by_id.setdefault(resource_id, []).append(item)

        totals: dict[tuple[str, str], dict[str, Any]] = {}
        for fact in facts:
            resource_id = self._normalize_resource_id(
                fact.get("resource_id") or fact.get("resourceId")
            )
            currency = str(fact.get("currency") or "").upper()
            key = (resource_id or "(unallocated)", currency)
            current = totals.setdefault(
                key,
                {
                    "resource_id": resource_id or "(unallocated)",
                    "currency": currency,
                    "cost": 0.0,
                    "records": 0,
                    "services": set(),
                    "resource_group": fact.get("resource_group")
                    or fact.get("resourceGroup")
                    or "",
                },
            )
            current["cost"] += float(fact.get("cost_amount") or fact.get("costAmount") or 0)
            current["records"] += 1
            service = fact.get("service_name") or fact.get("serviceName")
            if service:
                current["services"].add(service)

        ranked = sorted(totals.values(), key=lambda item: item["cost"], reverse=True)
        top_n = self._requested_top_n(question)
        q = question.lower()

        lines = [
            "Top Cost Drivers",
            "",
        ]

        if "node pool" in q or "nodepool" in q:
            node_pool_rows = [
                item
                for item in ranked
                if "nodepool" in item["resource_id"]
                or "node pool" in " ".join(item["services"]).lower()
                or "nodepool" in " ".join(item["services"]).lower()
            ]
            if node_pool_rows:
                ranked = node_pool_rows
            else:
                lines.extend(
                    [
                        "I do not see node-pool-level costFacts in the collected data. "
                        "Azure Cost Management usually reports AKS at cluster/resource levels unless node pool tags or allocation dimensions are collected.",
                        "",
                        "Closest available AKS/resource-level costs:",
                    ]
                )

        if top_n == 1 and ranked:
            top = ranked[0]
            lines.append(
                f"The highest-cost resource is {self._cost_resource_label(top, resources_by_id)} "
                f"at {format_money(top['cost'], top['currency'])}."
            )
            lines.append("")
            lines.append("Cost Breakdown:")
        else:
            lines.append(f"Top {min(top_n, len(ranked))} resources by spend:")

        for index, item in enumerate(ranked[:top_n], 1):
            resource = resources_by_id.get(item["resource_id"], {})
            recs = recommendations_by_id.get(item["resource_id"], [])
            recommendation = ""
            if recs:
                action = recs[0].get("content") or "optimization opportunity identified"
                recommendation = f" | recommended action: {action}"
            services = ", ".join(sorted(item["services"])) or "unknown service"
            lines.append(
                f"{index}. {self._cost_resource_label(item, resources_by_id)} - "
                f"{format_money(item['cost'], item['currency'])} "
                f"({services}; resource group: {resource.get('resource_group') or item.get('resource_group') or 'unknown'})"
                f"{recommendation}"
            )

        return self._with_debug(
            "\n".join(lines),
            [
                f"Detected intent: {classification.intent}",
                "Route selected: cost_analysis",
                "Retrieval source: costFacts + resource inventory + recommendations repositories",
                f"Cost records analyzed: {len(facts)}",
                f"Resources correlated: {sum(1 for item in ranked if item['resource_id'] in resources_by_id)}",
            ],
        )

    def _answer_recommendation_query(self, question: str, classification: Any) -> str:
        context = self._load_repository_context()
        ctx = self._load_context()
        resources = pd.DataFrame(context["resources"])
        if resources.empty:
            resources = ctx.get("resources", pd.DataFrame())
        analysis = self._build_recommendation_analysis(context, resources)

        if analysis["opportunities"]:
            llm_answer = self._try_generate_recommendation_narrative(
                question, classification, analysis
            )
            if llm_answer:
                return llm_answer
            return self._format_recommendation_analysis(classification, analysis)

        if not resources.empty:
            return self._answer_savings_opportunities(resources, ctx.get("waste", {}))

        return self._with_debug(
            "Optimization analysis could not run because no recommendation, "
            "resource, or waste finding data is available yet.",
            [
                f"Detected intent: {classification.intent}",
                "Route selected: recommendation",
                "Retrieval source: recommendations + resource inventory + costFacts repositories",
            ],
        )

    def _build_recommendation_analysis(
        self, context: dict[str, list[dict[str, Any]]], resources: pd.DataFrame
    ) -> dict[str, Any]:
        facts = context["costFacts"]
        recommendations = context["recommendations"]
        advisor_findings = context.get("advisorFindings", [])
        resources_list = context["resources"]
        resources_by_id = self._resources_by_id(resources_list)
        costs_by_id = self._cost_totals_by_resource(facts)

        top_spend_categories = self._top_spend_categories(facts)
        top_cost_resources = self._top_cost_resources(costs_by_id, resources_by_id)
        opportunities = sorted(
            self._correlate_recommendations(
                recommendations, resources_by_id, costs_by_id
            ),
            key=lambda item: (item["savings"], item["cost"]),
            reverse=True,
        )
        for opportunity in opportunities:
            opportunity["priority"] = self._priority_for_opportunity(opportunity)
            opportunity["root_cause"] = self._root_cause_for_opportunity(opportunity)
            opportunity["advisor_evidence"] = self._advisor_evidence_for_resource(
                opportunity["resource_id"], advisor_findings
            )
            opportunity["utilization"] = self._utilization_summary(
                resources_by_id.get(opportunity["resource_id"], {})
            )

        savings_totals: dict[str, float] = {}
        for opportunity in opportunities:
            currency = opportunity["savings_currency"] or "UNKNOWN"
            savings_totals[currency] = round(
                savings_totals.get(currency, 0.0) + opportunity["savings"], 2
            )

        return {
            "source": "costFacts + resource inventory + recommendations + Azure Advisor",
            "record_counts": {
                "costFacts": len(facts),
                "resources": len(resources_list) or int(len(resources)),
                "recommendations": len(recommendations),
                "advisorFindings": len(advisor_findings),
            },
            "top_spend_categories": top_spend_categories,
            "top_cost_resources": top_cost_resources,
            "opportunities": opportunities[:10],
            "estimated_savings_totals": savings_totals,
            "root_causes": self._summarize_root_causes(opportunities),
        }

    def _try_generate_recommendation_narrative(
        self, question: str, classification: Any, analysis: dict[str, Any]
    ) -> str | None:
        if not (self.settings.openai_configured or getattr(self.rag, "_llm", None) is not None):
            return None
        try:
            messages = FINOPS_RECOMMENDATION_ANALYSIS_PROMPT.format_messages(
                input=question,
                analysis=json.dumps(analysis, indent=2, default=str),
            )
            response = self.rag._get_llm().invoke(messages)
            answer = str(getattr(response, "content", response)).strip()
            if not answer:
                return None
            return self._with_debug(
                answer,
                [
                    f"Detected intent: {classification.intent}",
                    "Route selected: recommendation",
                    f"Retrieval source: {analysis['source']}",
                ],
            )
        except Exception as exc:
            logger.warning("Recommendation narrative generation failed: %s", exc)
            return None

    def _format_recommendation_analysis(
        self, classification: Any, analysis: dict[str, Any]
    ) -> str:
        lines = [
            "Executive Summary",
            "Your best savings opportunities are concentrated in the resources with explicit waste findings and quantified recommendations.",
            "",
            "Top Cost Drivers",
        ]
        for item in analysis["top_spend_categories"][:5]:
            lines.append(
                f"- {item['service_name']}: {format_money(item['cost'], item['currency'])}"
            )

        lines.extend(["", "Root Causes"])
        for cause in analysis["root_causes"][:5]:
            lines.append(f"- {cause['cause']}: {cause['count']} finding(s)")

        lines.extend(["", "Recommended Actions"])
        for item in analysis["opportunities"][:5]:
            cost_note = (
                f"; observed spend {format_money(item['cost'], item['currency'])}"
                if item["currency"]
                else ""
            )
            util_note = f"; utilization {item['utilization']}" if item["utilization"] else ""
            advisor_note = (
                f"; Advisor: {item['advisor_evidence']}"
                if item["advisor_evidence"]
                else ""
            )
            waste_note = f"; waste level {item['waste_level']}" if item["waste_level"] else ""
            lines.append(
                f"- Priority {item['priority']}: {item['resource_name']} "
                f"({item['resource_type']}) — {item['action']} — "
                f"estimated savings {format_money(item['savings'], item['savings_currency'])}/month"
                f"{cost_note}{util_note}{waste_note}{advisor_note}. Root cause: {item['root_cause']}."
            )

        lines.extend(["", "Estimated Monthly Savings"])
        if analysis["estimated_savings_totals"]:
            for currency, amount in analysis["estimated_savings_totals"].items():
                lines.append(f"- {format_money(amount, currency)}/month")
        else:
            lines.append("- Savings not quantified")
        return self._with_debug(
            "\n".join(lines),
            [
                f"Detected intent: {classification.intent}",
                "Route selected: recommendation",
                f"Retrieval source: {analysis['source']}",
                f"Records analyzed: {analysis['record_counts']}",
            ],
        )

    def _answer_utilization_query(self, question: str, classification: Any) -> str:
        context = self._load_repository_context()
        resources = context["resources"]
        if not resources:
            return self._with_debug(
                "Utilization analysis could not run because no resource inventory facts are available.",
                [
                    f"Detected intent: {classification.intent}",
                    "Route selected: utilization",
                    "Retrieval source: resource inventory/utilization attributes",
                ],
            )

        rows = []
        for item in resources:
            if not self._is_utilization_resource(item):
                continue
            attrs = item.get("attributes") or {}
            cpu = self._first_number(
                item,
                attrs,
                "cpu_avg_percent",
                "cpuAvgPercent",
                "cpu_average_percent",
                "averageCpuPercentage",
            )
            memory = self._first_number(
                item,
                attrs,
                "memory_avg_percent",
                "memoryAvgPercent",
                "averageMemoryPercentage",
            )
            savings = float(item.get("estimated_savings") or item.get("estimatedSavings") or 0)
            waste_level = str(item.get("waste_level") or item.get("wasteLevel") or "NONE")
            utilization_rule = str(attrs.get("rule_id") or item.get("rule_id") or "")
            compute_waste = utilization_rule in {"oversized_vm", "aks_waste"}
            if cpu is not None or memory is not None or compute_waste:
                rows.append((item, cpu, memory, savings, waste_level))

        rows.sort(key=lambda row: (row[3], -(row[1] or 101)), reverse=True)
        lines = [
            "Underutilized Compute Resources",
            "",
        ]

        if not rows:
            lines.append(
                "No utilization metrics are present in the collected resource facts yet. "
                "Collect compute utilization metrics before ranking underutilized resources."
            )
            return self._with_debug(
                "\n".join(lines),
                [
                    f"Detected intent: {classification.intent}",
                    "Route selected: utilization",
                    "Retrieval source: resource inventory utilization attributes + recommendations",
                    f"Resources analyzed: {len(resources)}",
                    f"Compute resources with utilization signals: {len(rows)}",
                ],
            )

        for index, (item, cpu, memory, savings, waste_level) in enumerate(rows[:5], 1):
            metrics = []
            if cpu is not None:
                metrics.append(f"CPU {cpu:.1f}%")
            if memory is not None:
                metrics.append(f"memory {memory:.1f}%")
            if not metrics:
                metrics.append(f"waste level {waste_level}")
            lines.append(
                f"{index}. {item.get('resource_name') or item.get('resourceName')} "
                f"({item.get('resource_type') or item.get('resourceType')}) - "
                f"{', '.join(metrics)} - estimated savings "
                f"{format_money(savings, item.get('savings_currency') or item.get('savingsCurrency') or '')}/month"
            )
        return self._with_debug(
            "\n".join(lines),
            [
                f"Detected intent: {classification.intent}",
                "Route selected: utilization",
                "Retrieval source: resource inventory utilization attributes + recommendations",
                f"Resources analyzed: {len(resources)}",
                f"Compute resources with utilization signals: {len(rows)}",
            ],
        )

    def _answer_idle_resources_query(self, question: str, classification: Any) -> str:
        context = self._load_repository_context()
        resources = context["resources"]
        recommendations = context["recommendations"]
        advisor_findings = context.get("advisorFindings", [])
        resources_by_id = self._resources_by_id(resources)
        costs_by_id = self._cost_totals_by_resource(context["costFacts"])

        candidates: dict[str, dict[str, Any]] = {}

        def merge(candidate: dict[str, Any]) -> None:
            key = (
                self._normalize_resource_id(candidate.get("resource_id"))
                or str(candidate.get("resource_name") or "").lower()
            )
            if not key:
                return
            existing = candidates.get(key)
            if not existing:
                candidates[key] = candidate
                return
            if self._confidence_rank(candidate["confidence"]) > self._confidence_rank(existing["confidence"]):
                existing["confidence"] = candidate["confidence"]
                existing["reason"] = candidate["reason"]
            existing["savings"] = max(float(existing.get("savings") or 0), float(candidate.get("savings") or 0))
            existing["cost"] = max(float(existing.get("cost") or 0), float(candidate.get("cost") or 0))
            if candidate.get("action") and candidate["action"] not in existing["action"]:
                existing["action"] = f"{existing['action']}; {candidate['action']}"
            existing["sources"] = sorted(set(existing.get("sources", [])) | set(candidate.get("sources", [])))

        for recommendation in recommendations:
            resource_id = self._normalize_resource_id(
                recommendation.get("resource_id") or recommendation.get("resourceId")
            )
            resource = resources_by_id.get(resource_id, {})
            action = str(
                recommendation.get("content")
                or recommendation.get("title")
                or recommendation.get("recommendation")
                or "Review optimization recommendation"
            )
            confidence, reason = self._idle_confidence_and_reason(
                action=action,
                resource=resource,
                recommendation=recommendation,
            )
            if not confidence:
                continue
            cost = costs_by_id.get(resource_id, {})
            merge(
                {
                    "resource_id": resource_id,
                    "resource_name": resource.get("resource_name")
                    or resource.get("resourceName")
                    or self._resource_name_from_id(resource_id),
                    "resource_type": resource.get("resource_type")
                    or resource.get("resourceType")
                    or "resource",
                    "resource_group": resource.get("resource_group")
                    or resource.get("resourceGroup")
                    or "",
                    "confidence": confidence,
                    "reason": reason,
                    "action": self._idle_action(action, resource),
                    "savings": float(
                        recommendation.get("estimated_savings")
                        or recommendation.get("estimatedSavings")
                        or resource.get("estimated_savings")
                        or resource.get("estimatedSavings")
                        or 0
                    ),
                    "savings_currency": recommendation.get("currency")
                    or resource.get("savings_currency")
                    or resource.get("savingsCurrency")
                    or cost.get("currency")
                    or "",
                    "cost": float(cost.get("cost") or 0),
                    "currency": cost.get("currency") or "",
                    "sources": ["recommendations"],
                }
            )

        for resource in resources:
            attrs = resource.get("attributes") or {}
            action = str(
                resource.get("recommendation")
                or attrs.get("recommendation")
                or resource.get("rule_id")
                or attrs.get("rule_id")
                or ""
            )
            confidence, reason = self._idle_confidence_and_reason(
                action=action,
                resource=resource,
                recommendation={},
            )
            if not confidence:
                continue
            resource_id = self._normalize_resource_id(
                resource.get("resource_id") or resource.get("resourceId")
            )
            cost = costs_by_id.get(resource_id, {})
            merge(
                {
                    "resource_id": resource_id,
                    "resource_name": resource.get("resource_name")
                    or resource.get("resourceName")
                    or self._resource_name_from_id(resource_id),
                    "resource_type": resource.get("resource_type")
                    or resource.get("resourceType")
                    or "resource",
                    "resource_group": resource.get("resource_group")
                    or resource.get("resourceGroup")
                    or "",
                    "confidence": confidence,
                    "reason": reason,
                    "action": self._idle_action(action, resource),
                    "savings": float(
                        resource.get("estimated_savings")
                        or resource.get("estimatedSavings")
                        or 0
                    ),
                    "savings_currency": resource.get("savings_currency")
                    or resource.get("savingsCurrency")
                    or cost.get("currency")
                    or "",
                    "cost": float(cost.get("cost") or 0),
                    "currency": cost.get("currency") or "",
                    "sources": ["processed facts"],
                }
            )

        for finding in advisor_findings:
            action = str(
                finding.get("solution")
                or finding.get("problem")
                or finding.get("recommendation")
                or finding.get("shortDescription")
                or ""
            )
            resource_id = self._normalize_resource_id(
                finding.get("resourceId")
                or finding.get("resource_id")
                or finding.get("impactedValue")
                or finding.get("id")
            )
            resource = resources_by_id.get(resource_id, {})
            confidence, reason = self._idle_confidence_and_reason(
                action=action,
                resource=resource,
                recommendation=finding,
            )
            if not confidence:
                continue
            cost = costs_by_id.get(resource_id, {})
            merge(
                {
                    "resource_id": resource_id,
                    "resource_name": resource.get("resource_name")
                    or resource.get("resourceName")
                    or self._resource_name_from_id(resource_id),
                    "resource_type": resource.get("resource_type")
                    or resource.get("resourceType")
                    or "resource",
                    "resource_group": resource.get("resource_group")
                    or resource.get("resourceGroup")
                    or "",
                    "confidence": confidence,
                    "reason": reason,
                    "action": self._idle_action(action, resource),
                    "savings": 0.0,
                    "savings_currency": cost.get("currency") or "",
                    "cost": float(cost.get("cost") or 0),
                    "currency": cost.get("currency") or "",
                    "sources": ["advisor findings"],
                }
            )

        ranked = sorted(
            candidates.values(),
            key=lambda item: (
                self._confidence_rank(item["confidence"]),
                float(item.get("savings") or 0),
                float(item.get("cost") or 0),
            ),
            reverse=True,
        )

        if not ranked:
            return self._with_debug(
                "I do not see confirmed idle or unused resources in the current dataset. "
                "No unattached public IPs, orphaned disks, unused NICs, or underutilized compute findings were available.",
                [
                    f"Detected intent: {classification.intent}",
                    "Route selected: idle_resources",
                    "Retrieval source: recommendations + advisor findings + processed facts + utilization facts",
                    f"Recommendations analyzed: {len(recommendations)}",
                    f"Resources analyzed: {len(resources)}",
                    f"Advisor findings analyzed: {len(advisor_findings)}",
                ],
            )

        sections = [
            ("High Confidence Idle Resources", "High"),
            ("Medium Confidence Underutilized Resources", "Medium"),
            ("Low Confidence Suspected Waste", "Low"),
        ]
        lines = [
            "Idle and Unused Resources",
            "",
            "I found resources that appear unused, orphaned, or underutilized. Confirm ownership before deleting production resources.",
        ]
        any_section = False
        for title, confidence in sections:
            rows = [item for item in ranked if item["confidence"] == confidence]
            if not rows:
                continue
            any_section = True
            lines.extend(["", title])
            for index, item in enumerate(rows[:8], 1):
                savings = ""
                if float(item.get("savings") or 0) > 0:
                    savings = (
                        f" Estimated savings: "
                        f"{format_money(item['savings'], item.get('savings_currency') or item.get('currency') or '')}/month."
                    )
                cost = ""
                if float(item.get("cost") or 0) > 0:
                    cost = f" Observed spend: {format_money(item['cost'], item.get('currency') or '')}."
                resource_group = (
                    f" Resource group: {item['resource_group']}."
                    if item.get("resource_group")
                    else ""
                )
                lines.append(
                    f"{index}. {item['resource_name']} ({item['resource_type']}) - "
                    f"{item['reason']} Recommended action: {item['action']}."
                    f"{savings}{cost}{resource_group}"
                )

        if not any_section:
            lines.append("")
            lines.append("No actionable idle resources were found after correlation.")

        total_savings: dict[str, float] = {}
        for item in ranked:
            currency = item.get("savings_currency") or item.get("currency") or ""
            amount = float(item.get("savings") or 0)
            if amount > 0:
                total_savings[currency] = total_savings.get(currency, 0.0) + amount
        if total_savings:
            lines.extend(["", "Estimated Monthly Savings"])
            for currency, amount in total_savings.items():
                lines.append(f"- {format_money(amount, currency)}/month")

        return self._with_debug(
            "\n".join(lines),
            [
                f"Detected intent: {classification.intent}",
                "Route selected: idle_resources",
                "Retrieval source: recommendations + advisor findings + processed facts + utilization facts",
                f"Idle candidates returned: {len(ranked)}",
            ],
        )

    def _top_spend_categories(
        self, facts: list[dict[str, Any]], limit: int = 8
    ) -> list[dict[str, Any]]:
        totals: dict[tuple[str, str], float] = {}
        for fact in facts:
            service = str(
                fact.get("service_name") or fact.get("serviceName") or "Unknown"
            )
            currency = str(fact.get("currency") or "").upper()
            amount = float(fact.get("cost_amount") or fact.get("costAmount") or 0)
            totals[(service, currency)] = totals.get((service, currency), 0.0) + amount
        return [
            {
                "service_name": service,
                "currency": currency,
                "cost": round(cost, 2),
            }
            for (service, currency), cost in sorted(
                totals.items(), key=lambda item: item[1], reverse=True
            )[:limit]
        ]

    def _top_cost_resources(
        self,
        costs_by_id: dict[str, dict[str, Any]],
        resources_by_id: dict[str, dict[str, Any]],
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        rows = []
        for resource_id, cost in costs_by_id.items():
            resource = resources_by_id.get(resource_id, {})
            rows.append(
                {
                    "resource_id": resource_id,
                    "resource_name": resource.get("resource_name")
                    or resource.get("resourceName")
                    or self._resource_name_from_id(resource_id),
                    "resource_type": resource.get("resource_type")
                    or resource.get("resourceType")
                    or "resource",
                    "resource_group": resource.get("resource_group")
                    or resource.get("resourceGroup")
                    or "",
                    "cost": round(float(cost.get("cost") or 0), 2),
                    "currency": cost.get("currency") or "",
                }
            )
        return sorted(rows, key=lambda item: item["cost"], reverse=True)[:limit]

    @staticmethod
    def _confidence_rank(confidence: str) -> int:
        return {"High": 3, "Medium": 2, "Low": 1}.get(confidence, 0)

    def _idle_confidence_and_reason(
        self,
        *,
        action: str,
        resource: dict[str, Any],
        recommendation: dict[str, Any],
    ) -> tuple[str, str]:
        attrs = resource.get("attributes") or {}
        evidence = recommendation.get("evidence") or {}
        resource_type = str(
            resource.get("resource_type") or resource.get("resourceType") or ""
        ).lower()
        combined = " ".join(
            str(value or "")
            for value in (
                action,
                resource.get("recommendation"),
                resource.get("rule_id"),
                resource.get("ruleId"),
                attrs.get("recommendation"),
                attrs.get("rule_id"),
                attrs.get("ruleId"),
                resource.get("waste_level"),
                resource.get("wasteLevel"),
                evidence.get("wasteLevel"),
                recommendation.get("category"),
                recommendation.get("impact"),
            )
        ).lower()

        high_patterns = (
            "idle_public_ip",
            "delete public ip",
            "unused public ip",
            "unattached public ip",
            "public ip is not associated",
            "unattached disk",
            "orphaned disk",
            "delete disk",
            "unused nic",
            "orphaned nic",
            "not associated",
            "not attached",
            "not been associated",
            "delete if it is no longer required",
        )
        if any(pattern in combined for pattern in high_patterns):
            if "public" in combined or "publicip" in resource_type or "publicipaddresses" in resource_type:
                return "High", "Public IP appears unattached or not associated with an active workload."
            if "disk" in combined or "microsoft.compute/disks" in resource_type:
                return "High", "Managed disk appears unattached and can likely be removed after validation."
            if "nic" in combined or "networkinterfaces" in resource_type:
                return "High", "Network interface appears unused or orphaned."
            return "High", "Resource appears completely unused or orphaned."

        medium_patterns = (
            "aks_waste",
            "enable autoscaler",
            "underutilized",
            "under utilized",
            "low utilization",
            "average utilization is low",
            "node utilization",
            "oversized_vm",
            "rightsize",
            "resize",
        )
        if any(pattern in combined for pattern in medium_patterns):
            if "aks" in combined or "containerservice/managedclusters" in resource_type:
                return "Medium", "AKS capacity is underutilized relative to provisioned compute."
            return "Medium", "Compute resource shows low utilization compared with allocated capacity."

        waste_level = str(
            evidence.get("wasteLevel")
            or resource.get("waste_level")
            or resource.get("wasteLevel")
            or ""
        ).upper()
        savings = float(
            recommendation.get("estimated_savings")
            or recommendation.get("estimatedSavings")
            or resource.get("estimated_savings")
            or resource.get("estimatedSavings")
            or 0
        )
        if waste_level and waste_level != "NONE":
            return "Low", f"Resource has a {waste_level.lower()} waste signal."
        if savings > 0 and any(term in combined for term in ("waste", "optimize", "saving")):
            return "Low", "Resource has a savings or waste recommendation that should be reviewed."

        return "", ""

    @staticmethod
    def _idle_action(action: str, resource: dict[str, Any]) -> str:
        text = action.strip()
        resource_type = str(
            resource.get("resource_type") or resource.get("resourceType") or ""
        ).lower()
        lowered = text.lower()
        if "public ip" in lowered or "publicipaddresses" in resource_type:
            return "Delete the public IP if it is no longer required, or associate it with an active workload"
        if "disk" in lowered or "microsoft.compute/disks" in resource_type:
            return "Detach validation is complete; delete the orphaned disk or snapshot it before removal"
        if "nic" in lowered or "networkinterfaces" in resource_type:
            return "Confirm no VM or private endpoint depends on it, then remove the unused NIC"
        if "autoscaler" in lowered or "aks" in lowered or "containerservice/managedclusters" in resource_type:
            return "Enable cluster autoscaler and review node pool sizing"
        if "resize" in lowered or "rightsize" in lowered:
            return "Rightsize or deallocate after validating workload requirements"
        return text or "Review ownership and remove or rightsize if no active workload depends on it"

    @staticmethod
    def _priority_for_opportunity(opportunity: dict[str, Any]) -> str:
        savings = float(opportunity.get("savings") or 0)
        waste = str(opportunity.get("waste_level") or "").upper()
        if savings >= 250 or waste == "HIGH":
            return "High"
        if savings >= 50 or waste == "MEDIUM":
            return "Medium"
        return "Low"

    @staticmethod
    def _root_cause_for_opportunity(opportunity: dict[str, Any]) -> str:
        action = str(opportunity.get("action") or "").lower()
        resource_type = str(opportunity.get("resource_type") or "").lower()
        if "autoscaler" in action or "aks" in resource_type:
            return "AKS capacity is underutilized relative to provisioned compute."
        if "public ip" in action or "public ip" in resource_type:
            return "Public IP is not associated with an active workload."
        if "disk" in action or "disk" in resource_type:
            return "Managed disk is unattached and still incurring storage cost."
        if "rightsize" in action or "resize" in action:
            return "Compute utilization is low compared with allocated capacity."
        return str(opportunity.get("reason") or "Optimization recommendation")

    def _advisor_evidence_for_resource(
        self, resource_id: str, advisor_findings: list[dict[str, Any]]
    ) -> str:
        if not resource_id:
            return ""
        normalized = self._normalize_resource_id(resource_id)
        for finding in advisor_findings:
            candidate = self._normalize_resource_id(
                finding.get("resourceId")
                or finding.get("resource_id")
                or finding.get("impactedValue")
                or finding.get("id")
            )
            if candidate and (
                candidate == normalized
                or candidate in normalized
                or normalized in candidate
            ):
                return str(
                    finding.get("solution")
                    or finding.get("problem")
                    or finding.get("shortDescription")
                    or finding.get("recommendationId")
                    or ""
                )
        return ""

    def _utilization_summary(self, resource: dict[str, Any]) -> str:
        if not resource or not self._is_utilization_resource(resource):
            return ""
        attrs = resource.get("attributes") or {}
        cpu = self._first_number(
            resource,
            attrs,
            "cpu_avg_percent",
            "cpuAvgPercent",
            "averageCpuPercentage",
            "node_utilization",
            "nodeUtilization",
        )
        memory = self._first_number(
            resource,
            attrs,
            "memory_avg_percent",
            "memoryAvgPercent",
            "averageMemoryPercentage",
        )
        metrics = []
        if cpu is not None:
            metrics.append(f"CPU {cpu:.1f}%")
        if memory is not None:
            metrics.append(f"memory {memory:.1f}%")
        return ", ".join(metrics)

    @staticmethod
    def _summarize_root_causes(
        opportunities: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        counts: dict[str, int] = {}
        for opportunity in opportunities:
            cause = str(opportunity.get("root_cause") or "Recommendation")
            counts[cause] = counts.get(cause, 0) + 1
        return [
            {"cause": cause, "count": count}
            for cause, count in sorted(
                counts.items(), key=lambda item: item[1], reverse=True
            )
        ]

    def _resources_by_id(
        self, resources: list[dict[str, Any]]
    ) -> dict[str, dict[str, Any]]:
        return {
            self._normalize_resource_id(item.get("resource_id") or item.get("resourceId")): item
            for item in resources
            if item.get("resource_id") or item.get("resourceId")
        }

    def _cost_totals_by_resource(
        self, facts: list[dict[str, Any]]
    ) -> dict[str, dict[str, Any]]:
        totals: dict[str, dict[str, Any]] = {}
        for fact in facts:
            resource_id = self._normalize_resource_id(
                fact.get("resource_id") or fact.get("resourceId")
            )
            if not resource_id:
                continue
            current = totals.setdefault(
                resource_id,
                {
                    "cost": 0.0,
                    "currency": str(fact.get("currency") or "").upper(),
                    "records": 0,
                },
            )
            current["cost"] += float(fact.get("cost_amount") or fact.get("costAmount") or 0)
            current["records"] += 1
        return totals

    def _correlate_recommendations(
        self,
        recommendations: list[dict[str, Any]],
        resources_by_id: dict[str, dict[str, Any]],
        costs_by_id: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        correlated = []
        for recommendation in recommendations:
            resource_id = self._normalize_resource_id(
                recommendation.get("resource_id") or recommendation.get("resourceId")
            )
            resource = resources_by_id.get(resource_id, {})
            cost = costs_by_id.get(resource_id, {})
            resource_name = (
                resource.get("resource_name")
                or resource.get("resourceName")
                or self._resource_name_from_id(resource_id)
            )
            resource_type = (
                resource.get("resource_type")
                or resource.get("resourceType")
                or "resource"
            )
            action = (
                recommendation.get("content")
                or recommendation.get("title")
                or "Review optimization recommendation"
            ).strip()
            correlated.append(
                {
                    "resource_id": resource_id,
                    "resource_name": resource_name,
                    "resource_type": resource_type,
                    "action": action,
                    "reason": self._recommendation_reason(recommendation, resource),
                    "waste_level": (
                        (recommendation.get("evidence") or {}).get("wasteLevel")
                        or resource.get("waste_level")
                        or resource.get("wasteLevel")
                        or ""
                    ),
                    "savings": float(
                        recommendation.get("estimated_savings")
                        or recommendation.get("estimatedSavings")
                        or 0
                    ),
                    "savings_currency": recommendation.get("currency") or "",
                    "cost": float(cost.get("cost") or 0),
                    "currency": cost.get("currency") or "",
                }
            )
        return correlated

    def _recommendation_reason(
        self, recommendation: dict[str, Any], resource: dict[str, Any]
    ) -> str:
        evidence = recommendation.get("evidence") or {}
        waste_level = evidence.get("wasteLevel") or resource.get("waste_level") or resource.get("wasteLevel")
        basis = evidence.get("costBasis") or resource.get("cost_basis") or resource.get("costBasis")
        parts = []
        if waste_level and waste_level != "NONE":
            parts.append(f"waste level {waste_level}")
        if basis:
            parts.append(f"cost basis {basis}")
        return "; ".join(parts) if parts else "recommendation record"

    @staticmethod
    def _is_utilization_resource(item: dict[str, Any]) -> bool:
        resource_type = str(
            item.get("resource_type") or item.get("resourceType") or ""
        ).lower()
        return any(
            term in resource_type
            for term in (
                "virtual machine",
                "microsoft.compute/virtualmachines",
                "microsoft.compute/virtualmachinescalesets",
                "aks cluster",
                "microsoft.containerservice/managedclusters",
            )
        )

    @staticmethod
    def _normalize_resource_id(value: Any) -> str:
        return str(value or "").strip().rstrip("/").lower()

    @staticmethod
    def _requested_top_n(question: str) -> int:
        import re

        match = re.search(r"\btop\s+(\d+)\b", question.lower())
        if match:
            return max(1, min(int(match.group(1)), 25))
        if "highest" in question.lower():
            return 1
        return 5

    @staticmethod
    def _resource_name_from_id(resource_id: str) -> str:
        if not resource_id or resource_id == "(unallocated)":
            return "Unallocated subscription/service cost"
        return resource_id.rstrip("/").split("/")[-1] or resource_id

    def _cost_resource_label(
        self, item: dict[str, Any], resources_by_id: dict[str, dict[str, Any]]
    ) -> str:
        resource = resources_by_id.get(item["resource_id"], {})
        name = resource.get("resource_name") or resource.get("resourceName")
        resource_type = resource.get("resource_type") or resource.get("resourceType")
        if not name:
            name = self._resource_name_from_id(item["resource_id"])
        if resource_type:
            return f"{name} ({resource_type})"
        return name

    @staticmethod
    def _first_number(
        item: dict[str, Any], attrs: dict[str, Any], *keys: str
    ) -> float | None:
        for key in keys:
            value = item.get(key)
            if value is None:
                value = attrs.get(key)
            if value is None:
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return None

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

        if "cost" in q or "summary" in q or "recommendation" in q:
            return self._answer_cost_and_recommendation_summary(ctx, resources)

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

    def _answer_cost_and_recommendation_summary(
        self, ctx: dict[str, Any], resources: pd.DataFrame
    ) -> str:
        summary = ctx.get("summary", {})
        recommendations = ctx.get("recommendations", [])
        total_cost = summary.get("total_cost", {})
        if not total_cost and "total_cost_usd" in summary:
            total_cost = {"USD": summary["total_cost_usd"]}
        savings = summary.get("total_estimated_savings", {})
        if not savings and "total_estimated_savings_usd" in summary:
            savings = {"USD": summary["total_estimated_savings_usd"]}
        flagged = (
            resources[resources["waste_level"] != "NONE"].sort_values(
                "estimated_savings", ascending=False
            )
            if "waste_level" in resources
            else pd.DataFrame()
        )

        lines = [
            "Executive Summary",
            "",
            f"- Total Azure spend: {format_money_totals(total_cost) or 'N/A'}",
            f"- Resources reviewed: {len(resources)}",
            f"- Optimization opportunities: {summary.get('waste_resource_count', len(flagged))}",
            f"- Estimated monthly savings: {format_money_totals(savings) or 'N/A'}",
        ]
        if not flagged.empty:
            lines.extend(["", "Recommended Actions"])
            for i, (_, row) in enumerate(flagged.head(5).iterrows(), 1):
                lines.append(
                    f"{i}. {row.get('resource_name', 'unknown')} "
                    f"({row.get('resource_type', 'resource')}) - "
                    f"{row.get('recommendation', 'Review resource')} - "
                    f"{format_money(row.get('estimated_savings', 0), row.get('savings_currency', ''))}/month"
                )
        return "\n".join(lines)

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
