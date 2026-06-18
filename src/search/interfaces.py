"""Search provider protocol."""

from __future__ import annotations

from typing import Protocol, Sequence

from src.search.models import KnowledgeDocument, SearchResult


class SearchProvider(Protocol):
    def ensure_index(self) -> None: ...
    def index_documents(
        self, tenant_id: str, documents: Sequence[KnowledgeDocument]
    ) -> int: ...
    def search(
        self,
        tenant_id: str,
        subscription_id: str,
        query: str,
        *,
        top: int = 6,
    ) -> list[SearchResult]: ...
