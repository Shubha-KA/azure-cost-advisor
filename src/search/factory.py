"""Create the configured search provider."""

from src.repositories.errors import StorageConfigurationError


def create_search_provider(settings):
    provider = settings.search_provider.lower()
    if provider == "azure_ai_search":
        if not settings.azure_search_configured:
            raise StorageConfigurationError(
                "AZURE_SEARCH_ENDPOINT plus managed identity or an API key "
                "are required for SEARCH_PROVIDER=azure_ai_search"
            )
        from src.search.azure_ai_search import AzureAISearchProvider

        return AzureAISearchProvider(settings)
    if provider == "faiss":
        from src.search.faiss_provider import FaissSearchProvider

        return FaissSearchProvider(settings)
    raise StorageConfigurationError(
        f"Unsupported SEARCH_PROVIDER={settings.search_provider!r}"
    )
