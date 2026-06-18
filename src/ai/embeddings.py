"""Azure OpenAI embedding model factory."""

from __future__ import annotations

import logging

from langchain_openai import AzureOpenAIEmbeddings

from src.config import Settings, get_settings

logger = logging.getLogger(__name__)


class EmbeddingsError(Exception):
    """Raised when Azure OpenAI embeddings cannot be initialized."""


def build_embeddings(settings: Settings | None = None) -> AzureOpenAIEmbeddings:
    """
    Create Azure OpenAI embeddings client using credentials from .env.

    Required environment variables:
        AZURE_OPENAI_ENDPOINT
        AZURE_OPENAI_API_KEY
        AZURE_OPENAI_EMBEDDING_DEPLOYMENT (optional, default text-embedding-3-small)
        AZURE_OPENAI_API_VERSION (optional)
    """
    settings = settings or get_settings()

    if not settings.openai_configured:
        raise EmbeddingsError(
            "Azure OpenAI is not configured. Set AZURE_OPENAI_ENDPOINT and "
            "AZURE_OPENAI_API_KEY in your .env file."
        )

    logger.info(
        "Initializing Azure OpenAI embeddings: deployment=%s",
        settings.azure_openai_embedding_deployment,
    )

    kwargs = {}
    if settings.use_managed_identity and not settings.azure_openai_api_key:
        from azure.identity import DefaultAzureCredential, get_bearer_token_provider

        kwargs["azure_ad_token_provider"] = get_bearer_token_provider(
            DefaultAzureCredential(),
            "https://cognitiveservices.azure.com/.default",
        )
    else:
        kwargs["api_key"] = settings.azure_openai_api_key
    return AzureOpenAIEmbeddings(
        azure_endpoint=settings.azure_openai_endpoint.rstrip("/"),
        api_version=settings.azure_openai_api_version,
        azure_deployment=settings.azure_openai_embedding_deployment,
        **kwargs,
    )
