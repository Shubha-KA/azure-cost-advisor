"""Retrieval-Augmented Generation pipeline using LangChain + FAISS."""

from __future__ import annotations

import logging
from typing import Any

from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain.chains.retrieval import create_retrieval_chain
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import AzureChatOpenAI

from src.ai.embeddings import EmbeddingsError, build_embeddings
from src.ai.prompts import RAG_PROMPT, RECOMMENDATIONS_PROMPT
from src.ai.vector_store import FinOpsVectorStore, VectorStoreError
from src.config import Settings, get_settings

logger = logging.getLogger(__name__)


class RAGError(Exception):
    """Raised when RAG pipeline execution fails."""


class RAGPipeline:
    """Semantic retrieval + Azure OpenAI generation."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._llm: AzureChatOpenAI | None = None
        self._vector_store: FinOpsVectorStore | None = None

    def _get_llm(self) -> AzureChatOpenAI:
        if self._llm is not None:
            return self._llm
        if not self.settings.openai_configured:
            raise RAGError(
                "Azure OpenAI not configured. Set AZURE_OPENAI_ENDPOINT and "
                "AZURE_OPENAI_API_KEY in .env"
            )
        self._llm = AzureChatOpenAI(
            azure_endpoint=self.settings.azure_openai_endpoint.rstrip("/"),
            api_key=self.settings.azure_openai_api_key,
            api_version=self.settings.azure_openai_api_version,
            azure_deployment=self.settings.azure_openai_deployment_name,
            temperature=0.2,
        )
        return self._llm

    def _get_vector_store(self) -> FinOpsVectorStore:
        if self._vector_store is not None:
            return self._vector_store
        try:
            embeddings = build_embeddings(self.settings)
        except EmbeddingsError as exc:
            raise RAGError(str(exc)) from exc
        self._vector_store = FinOpsVectorStore(embeddings, self.settings)
        return self._vector_store

    def build_index(self, rebuild: bool = False) -> int:
        """Build or update the FAISS index from processed data."""
        store = self._get_vector_store()
        faiss = store.build_from_processed_data(rebuild=rebuild)
        logger.info("Index built with %d vectors", faiss.index.ntotal)
        return faiss.index.ntotal

    def retrieve(self, query: str, k: int = 6) -> list[dict[str, Any]]:
        """Return top-k semantically similar chunks."""
        try:
            vs = self._get_vector_store()
            if not vs.index_exists:
                raise VectorStoreError("Index not built")
            docs = vs.similarity_search(query, k=k)
            return [
                {"content": doc.page_content, "metadata": doc.metadata}
                for doc in docs
            ]
        except (VectorStoreError, EmbeddingsError) as exc:
            logger.warning("Retrieval failed: %s", exc)
            return []

    def invoke(
        self,
        query: str,
        chat_history: str = "",
        prompt: ChatPromptTemplate | None = None,
        k: int = 6,
    ) -> dict[str, Any]:
        """Run full RAG: retrieve context → generate answer."""
        prompt = prompt or RAG_PROMPT
        vs = self._get_vector_store()

        if not vs.index_exists:
            raise RAGError(
                "FAISS index not found. Run `python -m src.ai.run --build-index` first."
            )

        retriever = vs.load().as_retriever(search_kwargs={"k": k})
        llm = self._get_llm()
        document_chain = create_stuff_documents_chain(llm, prompt)
        rag_chain = create_retrieval_chain(retriever, document_chain)

        logger.info("RAG query: %s", query[:80])
        result = rag_chain.invoke(
            {
                "input": query,
                "chat_history": chat_history or "None",
            }
        )
        return {
            "answer": result.get("answer", ""),
            "context": result.get("context", []),
            "source": "azure_openai_rag",
        }

    def generate_recommendations(self, k: int = 10) -> dict[str, Any]:
        """Produce a prioritized FinOps recommendations report via RAG."""
        query = (
            "What are the biggest savings opportunities, waste findings, "
            "cost anomalies, and rightsizing actions for this Azure subscription?"
        )
        return self.invoke(query, prompt=RECOMMENDATIONS_PROMPT, k=k)
