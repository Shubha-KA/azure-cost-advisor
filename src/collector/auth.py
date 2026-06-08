"""Authentication factory for Azure SDK clients."""

import os
import logging
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential

logger = logging.getLogger(__name__)

_credential = None


def get_azure_credential() -> DefaultAzureCredential:
    """Returns a singleton instance of DefaultAzureCredential.
    
    IMPORTANT: We call load_dotenv() here to ensure AZURE_CLIENT_ID,
    AZURE_CLIENT_SECRET, and AZURE_TENANT_ID are in os.environ.
    Pydantic-settings reads .env into its own fields but does NOT
    export them to os.environ, which DefaultAzureCredential needs.
    """
    global _credential
    if _credential is None:
        # Load .env into os.environ so EnvironmentCredential can find them
        load_dotenv()
        
        client_id = os.environ.get("AZURE_CLIENT_ID", "")
        tenant_id = os.environ.get("AZURE_TENANT_ID", "")
        has_secret = bool(os.environ.get("AZURE_CLIENT_SECRET", ""))
        
        logger.info(
            "Initializing DefaultAzureCredential "
            "(AZURE_CLIENT_ID=%s, AZURE_TENANT_ID=%s, SECRET_SET=%s)",
            client_id[:8] + "..." if client_id else "MISSING",
            tenant_id[:8] + "..." if tenant_id else "MISSING",
            has_secret,
        )
        
        _credential = DefaultAzureCredential()
    return _credential
