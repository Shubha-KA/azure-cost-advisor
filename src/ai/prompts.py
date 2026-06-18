"""Prompt templates for FinOps RAG and conversational advisor."""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate, PromptTemplate

# Response format enforced for all assistant answers
RESPONSE_FORMAT_INSTRUCTIONS = """
Format every answer using this structure when applicable (omit sections with no data):

[One-sentence diagnosis]

[Supporting metric or evidence — e.g. CPU %, cost, anomaly detail]

Recommendation:
[Concrete action]

Estimated savings:
[currency code] [amount]/month.

Be specific. Use resource names, currency codes, amounts, and percentages from the context only.
Do not invent resources or costs not present in the context.
If context is insufficient, state what data is missing.
"""

FINOPS_SYSTEM_PROMPT = f"""You are the Azure Cost Optimization Advisor — an expert FinOps assistant.

You help engineers and finance teams reduce Azure spend by analyzing:
- Virtual Machines, disks, public IPs, AKS clusters, Application Gateway, VNets
- Cost anomalies and daily spend spikes
- Waste findings and savings opportunities

{RESPONSE_FORMAT_INSTRUCTIONS}

Focus on actionable, subscription-specific advice from the retrieved context.
Never recommend Key Vault, Managed Identities, Azure Blob Storage, or AKS migrations unless AKS data is in context.
"""

RAG_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", FINOPS_SYSTEM_PROMPT),
        (
            "human",
            "Retrieved context:\n{context}\n\n"
            "Conversation history:\n{chat_history}\n\n"
            "User question: {input}\n\n"
            "Answer using the required format.",
        ),
    ]
)

RECOMMENDATIONS_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", FINOPS_SYSTEM_PROMPT),
        (
            "human",
            "Retrieved context:\n{context}\n\n"
            "Generate a prioritized FinOps action plan covering:\n"
            "1. Highest savings opportunities\n"
            "2. Cost anomalies to investigate\n"
            "3. Quick wins (delete unattached disks, unused public IPs)\n"
            "4. Rightsizing and autoscaling recommendations\n\n"
            "Use bullet points with estimated monthly savings per item.\n"
            "Only recommend deleting, resizing, or autoscaling a named resource when "
            "the context contains an explicit waste finding or live Azure Advisor "
            "recommendation for that same resource. Never recommend a resource whose "
            "waste level is NONE. Do not invent savings ranges or convert currencies. "
            "If an exact savings amount is absent, say 'Savings not quantified'.",
        ),
    ]
)

DOCUMENT_TEMPLATE = PromptTemplate.from_template(
    "Resource: {resource_name}\n"
    "Type: {resource_type}\n"
    "Resource Group: {resource_group}\n"
    "Monthly Cost: ${monthly_cost}\n"
    "CPU Avg: {cpu_avg_percent}%\n"
    "Memory Avg: {memory_avg_percent}%\n"
    "Waste Level: {waste_level}\n"
    "Recommendation: {recommendation}\n"
    "Estimated Savings: ${estimated_savings}/month\n"
    "Rule: {rule_id}\n"
    "Anomaly Flag: {anomaly}"
)

EXAMPLE_QUESTIONS = [
    "Which VM wastes the most money?",
    "Why did costs spike?",
    "What are my biggest savings opportunities?",
]
