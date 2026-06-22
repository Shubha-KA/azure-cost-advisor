"""Deterministic FinOps intent classification and query routing."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


PRECEDENCE = [
    "cost_analysis",
    "idle_resources",
    "recommendation",
    "utilization",
    "knowledge_advisory",
    "live_inventory",
    "general_rag",
    "fallback_llm",
]


@dataclass(frozen=True)
class IntentClassification:
    """Scored intent decision for a user question."""

    intent: str
    route: str
    scores: dict[str, int]
    matched_terms: dict[str, list[str]] = field(default_factory=dict)


INTENT_LABELS = {
    "cost_analysis": "Cost Analysis",
    "idle_resources": "Idle / Unused Resources",
    "recommendation": "Recommendation / Optimization",
    "utilization": "Utilization / Performance",
    "knowledge_advisory": "Knowledge / Advisory Copilot",
    "live_inventory": "Inventory",
    "general_rag": "General RAG",
    "fallback_llm": "Fallback LLM",
}


PHRASES = {
    "cost_analysis": {
        "highest cost": 5,
        "top cost": 5,
        "top spend": 5,
        "cost by resource": 5,
        "cost per resource": 5,
        "costing me": 5,
        "costs most": 5,
        "most expensive": 5,
        "expensive resources": 5,
        "spend by": 4,
        "spending by": 4,
        "more cost": 4,
        "cost more": 4,
        "cost trend": 4,
        "last month": 2,
        "over time": 2,
    },
    "recommendation": {
        "wastes the most money": 5,
        "save money": 5,
        "reduce spend": 5,
        "reduce my spend": 6,
        "reduce cost": 5,
        "reduce my cost": 6,
        "how can i save": 5,
        "how can i reduce": 5,
        "should i optimize": 5,
        "what should i optimize": 5,
        "show recommendations": 4,
        "advisor recommendations": 4,
        "savings opportunities": 4,
        "right size": 4,
    },
    "idle_resources": {
        "which resources are idle": 8,
        "show unused resources": 8,
        "show orphaned resources": 8,
        "resources can be deleted": 8,
        "can be deleted": 6,
        "not being used": 8,
        "not in use": 7,
        "unused resources": 8,
        "idle resources": 8,
        "orphaned resources": 8,
        "unattached public ip": 8,
        "unused public ip": 8,
        "orphaned disks": 8,
        "unattached disks": 8,
        "unused nics": 8,
    },
    "utilization": {
        "under utilized": 5,
        "underutilized": 5,
        "low utilization": 5,
        "cpu usage": 4,
        "memory usage": 4,
        "node pool": 3,
        "nodepool": 3,
        "performance issue": 3,
    },
    "knowledge_advisory": {
        "explain my azure environment": 8,
        "why is aks expensive": 9,
        "why is my aks cluster expensive": 10,
        "why is aks costing": 9,
        "why are aks costs": 9,
        "best way to reduce": 8,
        "reduce networking costs": 9,
        "explain azure advisor": 9,
        "advisor findings": 7,
        "cost optimization roadmap": 9,
        "optimization roadmap": 8,
        "reserved instances vs savings plans": 10,
        "reserved instance vs savings plan": 10,
        "compare reserved instances": 8,
        "compare savings plans": 8,
    },
    "live_inventory": {
        "list all resources": 5,
        "what resources exist": 5,
        "what is deployed": 5,
        "currently deployed": 4,
        "current state": 4,
        "live status": 4,
        "show storage accounts": 4,
        "show key vaults": 4,
    },
    "general_rag": {
        "explain": 2,
        "why": 2,
        "summarize": 2,
        "tell me about": 2,
    },
}

WORDS = {
    "cost_analysis": {
        "cost": 3,
        "costs": 3,
        "costing": 4,
        "spend": 3,
        "spending": 3,
        "expensive": 4,
        "bill": 3,
        "billing": 3,
        "charge": 3,
        "charges": 3,
        "price": 2,
        "prices": 2,
    },
    "recommendation": {
        "recommend": 4,
        "recommendation": 4,
        "recommendations": 4,
        "save": 4,
        "saving": 4,
        "savings": 4,
        "optimize": 4,
        "optimization": 4,
        "rightsize": 4,
        "waste": 4,
        "wastes": 4,
        "money": 2,
        "delete": 2,
        "reduce": 3,
    },
    "idle_resources": {
        "idle": 6,
        "unused": 6,
        "orphaned": 6,
        "unattached": 6,
        "delete": 4,
        "deleted": 4,
        "deletable": 5,
        "waste": 3,
        "wasted": 3,
    },
    "utilization": {
        "utilization": 4,
        "utilisation": 4,
        "underutilized": 5,
        "cpu": 3,
        "memory": 3,
        "performance": 3,
        "nodepool": 3,
    },
    "knowledge_advisory": {
        "explain": 5,
        "why": 5,
        "roadmap": 5,
        "compare": 5,
        "advisor": 4,
        "best": 3,
        "strategy": 4,
        "plan": 3,
    },
    "live_inventory": {
        "list": 4,
        "inventory": 4,
        "deployed": 3,
        "exist": 3,
        "exists": 3,
        "resources": 2,
        "resource": 1,
        "vms": 2,
        "vm": 2,
        "aks": 1,
        "eastus": 2,
        "westus": 2,
    },
    "general_rag": {
        "explain": 2,
        "why": 2,
        "summarize": 2,
        "summary": 2,
        "overview": 2,
    },
}


def classify_intent(question: str) -> IntentClassification:
    """Score every supported FinOps intent, then apply explicit precedence.

    This intentionally does not stop after seeing inventory terms like
    "resource". Cost, optimization, and utilization questions often mention
    resources, so all intents must be evaluated before routing.
    """

    query = question.lower().strip()
    scores = {intent: 0 for intent in PRECEDENCE}
    matched: dict[str, list[str]] = {intent: [] for intent in PRECEDENCE}

    for intent, phrases in PHRASES.items():
        for phrase, score in phrases.items():
            if phrase in query:
                scores[intent] += score
                matched[intent].append(phrase)

    tokens = set(re.findall(r"[a-z0-9]+", query))
    for intent, words in WORDS.items():
        for word, score in words.items():
            if word in tokens:
                scores[intent] += score
                matched[intent].append(word)

    if (
        scores["knowledge_advisory"] >= 5
        and any(term in tokens for term in {"why", "explain", "compare", "roadmap", "advisor"})
        and any(term in tokens for term in {"cost", "costs", "expensive", "spend", "aks", "networking", "azure"})
    ):
        scores["knowledge_advisory"] += 4

    if "?" in question and not any(scores.values()):
        scores["general_rag"] = 1

    if not any(scores.values()):
        scores["fallback_llm"] = 1

    route = max(PRECEDENCE, key=lambda intent: (scores[intent], -PRECEDENCE.index(intent)))
    return IntentClassification(
        intent=INTENT_LABELS[route],
        route=route,
        scores=scores,
        matched_terms={key: value for key, value in matched.items() if value},
    )


def route_query(question: str) -> str:
    """Return the selected route for backwards-compatible callers."""

    return classify_intent(question).route
