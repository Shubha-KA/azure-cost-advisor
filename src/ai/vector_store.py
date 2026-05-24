"""Local FAISS vector store with document chunking."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_openai import AzureOpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.config import Settings, get_settings

logger = logging.getLogger(__name__)

FAISS_INDEX_DIR = "faiss_index"
CHUNK_SIZE = 800
CHUNK_OVERLAP = 120


class VectorStoreError(Exception):
    """Raised when vector store operations fail."""


class FinOpsVectorStore:
    """Builds, persists, and loads a local FAISS index under data/embeddings/faiss_index/."""

    def __init__(
        self,
        embeddings: AzureOpenAIEmbeddings,
        settings: Settings | None = None,
    ) -> None:
        self.embeddings = embeddings
        self.settings = settings or get_settings()
        self.index_dir = self.settings.embeddings_path / FAISS_INDEX_DIR
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

    @property
    def index_exists(self) -> bool:
        return (self.index_dir / "index.faiss").exists()

    def build_from_processed_data(self, rebuild: bool = False) -> FAISS:
        """Load processed outputs, chunk documents, embed, and persist FAISS index."""
        documents = self._load_documents_from_processed()
        if not documents:
            raise VectorStoreError(
                "No documents to index. Run collectors and processor first."
            )

        chunks = self.splitter.split_documents(documents)
        logger.info(
            "Split %d documents into %d chunks (size=%d, overlap=%d)",
            len(documents),
            len(chunks),
            CHUNK_SIZE,
            CHUNK_OVERLAP,
        )

        if rebuild or not self.index_exists:
            store = FAISS.from_documents(chunks, self.embeddings)
        else:
            store = self.load()
            store.add_documents(chunks)

        store.save_local(str(self.index_dir))
        self._write_manifest(len(documents), len(chunks))
        logger.info("FAISS index saved to %s", self.index_dir)
        return store

    def load(self) -> FAISS:
        if not self.index_exists:
            raise VectorStoreError(
                f"FAISS index not found at {self.index_dir}. "
                "Run `python -m src.ai.run` to build the index."
            )
        return FAISS.load_local(
            str(self.index_dir),
            self.embeddings,
            allow_dangerous_deserialization=True,
        )

    def similarity_search(self, query: str, k: int = 6) -> list[Document]:
        store = self.load()
        return store.similarity_search(query, k=k)

    def _load_documents_from_processed(self) -> list[Document]:
        docs: list[Document] = []
        processed = self.settings.processed_path

        resources_path = processed / "resources_latest.csv"
        if resources_path.exists():
            docs.extend(self._documents_from_resources(pd.read_csv(resources_path)))

        for name, doc_type in [
            ("waste_findings_latest.json", "waste"),
            ("anomalies_latest.json", "anomaly"),
            ("summary_latest.json", "summary"),
            ("processing_report_latest.json", "report"),
        ]:
            path = processed / name
            if path.exists():
                payload = json.loads(path.read_text(encoding="utf-8"))
                docs.extend(self._documents_from_json(payload, doc_type))

        advisor_path = self.settings.raw_path / "advisor_latest.json"
        if advisor_path.exists():
            payload = json.loads(advisor_path.read_text(encoding="utf-8"))
            docs.extend(self._documents_from_advisor(payload))

        docs.extend(self._finops_knowledge_documents())
        return docs

    def _documents_from_resources(self, df: pd.DataFrame) -> list[Document]:
        documents: list[Document] = []
        for _, row in df.iterrows():
            text = (
                f"Resource: {row.get('resource_name', 'unknown')}\n"
                f"Type: {row.get('resource_type', 'unknown')}\n"
                f"Monthly Cost: ${float(row.get('monthly_cost', 0)):.2f}\n"
                f"CPU Average: {float(row.get('cpu_avg_percent', 0)):.1f}%\n"
                f"Memory Average: {float(row.get('memory_avg_percent', 0)):.1f}%\n"
                f"Waste Level: {row.get('waste_level', 'NONE')}\n"
                f"Recommendation: {row.get('recommendation', '')}\n"
                f"Estimated Savings: ${float(row.get('estimated_savings', 0)):.2f}/month"
            )
            documents.append(
                Document(
                    page_content=text,
                    metadata={
                        "type": "resource",
                        "resource_name": str(row.get("resource_name", "")),
                        "resource_type": str(row.get("resource_type", "")),
                        "monthly_cost": float(row.get("monthly_cost", 0)),
                        "estimated_savings": float(row.get("estimated_savings", 0)),
                    },
                )
            )
        return documents

    def _documents_from_json(self, payload: dict | list, doc_type: str) -> list[Document]:
        documents: list[Document] = []

        if doc_type == "waste":
            for finding in payload.get("findings", []):
                text = (
                    f"Waste Finding [{finding.get('severity', 'unknown').upper()}]\n"
                    f"Resource: {finding.get('resource_name')} in {finding.get('resource_group')}\n"
                    f"Service: {finding.get('service_name')}\n"
                    f"Category: {finding.get('category_label')}\n"
                    f"Monthly Cost: ${finding.get('monthly_cost_usd', 0)}\n"
                    f"CPU: {finding.get('avg_cpu_percent', 0)}%\n"
                    f"Recommendation: {finding.get('recommendation')}\n"
                    f"Estimated Savings: ${finding.get('estimated_monthly_savings_usd', 0)}/month"
                )
                documents.append(
                    Document(page_content=text, metadata={"type": "waste", **finding})
                )

        elif doc_type == "anomaly":
            for anomaly in payload.get("anomalies", []):
                text = (
                    f"Cost Anomaly [{anomaly.get('severity', 'unknown')}]\n"
                    f"Date: {anomaly.get('date')}\n"
                    f"Cost: ${anomaly.get('cost_usd', 0)}\n"
                    f"Expected: ${anomaly.get('expected_cost_usd', 0)}\n"
                    f"Description: {anomaly.get('description')}"
                )
                documents.append(
                    Document(page_content=text, metadata={"type": "anomaly", **anomaly})
                )

        elif doc_type == "summary":
            text = (
                f"Cost Summary\n"
                f"Total Spend: ${payload.get('total_cost_usd', 0)}\n"
                f"Period: {payload.get('period_start')} to {payload.get('period_end')}\n"
                f"Est. Savings: ${payload.get('total_estimated_savings_usd', 0)}\n"
                f"Anomalies: {payload.get('anomaly_count', 0)}\n"
                f"Top Services: {json.dumps(payload.get('top_services', [])[:5])}"
            )
            documents.append(Document(page_content=text, metadata={"type": "summary"}))

        elif doc_type == "report":
            text = json.dumps(payload, indent=2, default=str)[:4000]
            documents.append(Document(page_content=text, metadata={"type": "report"}))

        return documents

    def _documents_from_advisor(self, payload: dict[str, Any]) -> list[Document]:
        documents: list[Document] = []
        for rec in payload.get("recommendations", []):
            text = (
                f"Azure Advisor Recommendation\n"
                f"Resource: {rec.get('resourceName')}\n"
                f"Impact: {rec.get('impact')}\n"
                f"Problem: {rec.get('problem')}\n"
                f"Solution: {rec.get('solution')}\n"
                f"Monthly Savings: ${rec.get('monthlySavingsUsd', 0)}"
            )
            documents.append(
                Document(page_content=text, metadata={"type": "advisor", **rec})
            )
        return documents

    @staticmethod
    def _finops_knowledge_documents() -> list[Document]:
        knowledge = [
            (
                "Idle VMs with CPU below 10% for sustained periods are prime rightsizing "
                "candidates. Deallocate dev/test VMs off-hours or switch to B-series burstable SKUs."
            ),
            (
                "Unattached managed disks incur full storage charges. Delete or snapshot "
                "disks unattached for more than 7 days."
            ),
            (
                "Unassociated public IPs cost ~$3.65/month each in most regions. "
                "Delete or associate with active resources."
            ),
            (
                "AKS clusters below 20% node utilization should enable the cluster autoscaler "
                "or reduce node pool VM sizes."
            ),
            (
                "Cost spikes where today_cost exceeds 1.5x the 7-day average often indicate "
                "Databricks job runs, scaling events, or forgotten dev resources left running."
            ),
            (
                "Application Gateway WAF_v2 charges include fixed and capacity unit costs. "
                "Review listener count and enable autoscaling."
            ),
        ]
        return [
            Document(page_content=text, metadata={"type": "finops_kb"})
            for text in knowledge
        ]

    def _write_manifest(self, doc_count: int, chunk_count: int) -> None:
        manifest = {
            "index_dir": str(self.index_dir),
            "built_at": datetime.now(timezone.utc).isoformat(),
            "document_count": doc_count,
            "chunk_count": chunk_count,
            "chunk_size": CHUNK_SIZE,
            "chunk_overlap": CHUNK_OVERLAP,
        }
        manifest_path = self.settings.embeddings_path / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
