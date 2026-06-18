"""Tenant-aware knowledge search providers."""

from src.search.factory import create_search_provider
from src.search.models import KnowledgeDocument, SearchResult

__all__ = ["KnowledgeDocument", "SearchResult", "create_search_provider"]
