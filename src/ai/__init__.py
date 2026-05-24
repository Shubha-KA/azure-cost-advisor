"""AI layer: embeddings, FAISS vector store, RAG, and FinOps advisor."""

from src.ai.advisor import FinOpsAdvisor
from src.ai.embeddings import EmbeddingsError, build_embeddings
from src.ai.rag import RAGError, RAGPipeline
from src.ai.vector_store import FinOpsVectorStore, VectorStoreError

__all__ = [
    "EmbeddingsError",
    "FinOpsAdvisor",
    "FinOpsVectorStore",
    "RAGError",
    "RAGPipeline",
    "VectorStoreError",
    "build_embeddings",
]
