"""Storage provider composition."""

from src.storage.factory import create_storage_provider
from src.storage.provider import StorageProvider

__all__ = ["StorageProvider", "create_storage_provider"]
