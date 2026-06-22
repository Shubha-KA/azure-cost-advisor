"""Development-only tenant-aware FAISS search provider."""

from __future__ import annotations

import time

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document

from src.ai.embeddings import build_embeddings
from src.repositories.errors import TenantScopeError
from src.search.models import SearchResult


class FaissSearchProvider:
    def __init__(self, settings) -> None:
        self.settings = settings
        self.embeddings = build_embeddings(settings)
        self.index_dir = settings.embeddings_path / "faiss_search_provider"
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.last_search_latency_ms = 0.0

    @property
    def index_exists(self) -> bool:
        return (self.index_dir / "index.faiss").exists()

    def ensure_index(self) -> None:
        return None

    def index_documents(self, tenant_id, documents) -> int:
        if any(document.tenant_id != tenant_id for document in documents):
            raise TenantScopeError(
                "All FAISS documents must match the indexing tenantId"
            )
        if not documents:
            return 0
        langchain_documents = [
            Document(
                page_content=document.content,
                metadata=document.model_dump(
                    by_alias=True, exclude={"contentVector", "content"}
                ),
            )
            for document in documents
        ]
        if self.index_exists:
            store = self._load()
            store.add_documents(langchain_documents)
        else:
            store = FAISS.from_documents(
                langchain_documents, self.embeddings
            )
        store.save_local(str(self.index_dir))
        return len(documents)

    def search(
        self,
        tenant_id: str,
        subscription_id: str,
        query: str,
        *,
        top: int = 6,
    ) -> list[SearchResult]:
        if not self.index_exists:
            return []
        started = time.perf_counter()
        documents = self._load().similarity_search(
            query, k=max(top * 5, 20)
        )
        self.last_search_latency_ms = (
            time.perf_counter() - started
        ) * 1000
        scoped = [
            item
            for item in documents
            if item.metadata.get("tenantId") == tenant_id
            and item.metadata.get("subscriptionId") == subscription_id
        ][:top]
        return [
            SearchResult(
                content=item.page_content, metadata=item.metadata
            )
            for item in scoped
        ]

    def delete_tenant(self, tenant_id: str) -> int:
        if not self.index_exists:
            return 0
        store = self._load()
        ids = [
            key
            for key, document in store.docstore._dict.items()
            if document.metadata.get("tenantId") == tenant_id
        ]
        if ids:
            store.delete(ids)
            store.save_local(str(self.index_dir))
        return len(ids)

    def _load(self):
        return FAISS.load_local(
            str(self.index_dir),
            self.embeddings,
            allow_dangerous_deserialization=True,
        )
