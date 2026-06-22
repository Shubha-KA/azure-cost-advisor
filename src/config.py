"""Application configuration loaded from environment variables."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    azure_subscription_id: str = Field(default="", alias="AZURE_SUBSCRIPTION_ID")
    azure_tenant_id: str = Field(default="", alias="AZURE_TENANT_ID")
    azure_client_id: str = Field(default="", alias="AZURE_CLIENT_ID")
    azure_client_secret: str = Field(default="", alias="AZURE_CLIENT_SECRET")

    storage_provider: str = Field(default="file", alias="STORAGE_PROVIDER")
    storage_data_dir: str = Field(default="data", alias="STORAGE_DATA_DIR")
    default_tenant_id: str = Field(default="", alias="DEFAULT_TENANT_ID")
    default_subscription_id: str = Field(
        default="", alias="DEFAULT_SUBSCRIPTION_ID"
    )
    cosmos_endpoint: str = Field(default="", alias="COSMOS_ENDPOINT")
    cosmos_database: str = Field(
        default="azure-cost-advisor", alias="COSMOS_DATABASE"
    )
    cosmos_key: str = Field(default="", alias="COSMOS_KEY")
    azure_storage_connection_string: str = Field(
        default="", alias="AZURE_STORAGE_CONNECTION_STRING"
    )
    azure_storage_account_url: str = Field(
        default="", alias="AZURE_STORAGE_ACCOUNT_URL"
    )
    azure_storage_container: str = Field(
        default="finops-raw", alias="AZURE_STORAGE_CONTAINER"
    )
    auth_mode: str = Field(default="legacy", alias="AUTH_MODE")
    entra_client_id: str = Field(default="", alias="ENTRA_CLIENT_ID")
    entra_client_secret: str = Field(default="", alias="ENTRA_CLIENT_SECRET")
    collection_entra_client_id: str = Field(
        default="", alias="COLLECTION_ENTRA_CLIENT_ID"
    )
    azure_federated_token_file: str = Field(
        default="", alias="AZURE_FEDERATED_TOKEN_FILE"
    )
    entra_authority: str = Field(
        default="https://login.microsoftonline.com/common",
        alias="ENTRA_AUTHORITY",
    )
    entra_redirect_uri: str = Field(
        default="http://localhost:8501", alias="ENTRA_REDIRECT_URI"
    )
    entra_post_logout_redirect_uri: str = Field(
        default="http://localhost:8501",
        alias="ENTRA_POST_LOGOUT_REDIRECT_URI",
    )
    api_host: str = Field(default="127.0.0.1", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    api_session_secret: str = Field(
        default="local-development-session-secret-change-me",
        alias="API_SESSION_SECRET",
    )
    api_cors_origins: str = Field(
        default="http://localhost:3000", alias="API_CORS_ORIGINS"
    )
    frontend_url: str = Field(
        default="http://localhost:3000", alias="FRONTEND_URL"
    )
    api_session_cookie_secure: bool = Field(
        default=False, alias="API_SESSION_COOKIE_SECURE"
    )
    service_bus_namespace: str = Field(
        default="", alias="SERVICE_BUS_NAMESPACE"
    )
    service_bus_topic: str = Field(
        default="finops-events", alias="SERVICE_BUS_TOPIC"
    )
    event_provider: str = Field(default="memory", alias="EVENT_PROVIDER")
    service_name: str = Field(default="monolith", alias="SERVICE_NAME")
    applicationinsights_connection_string: str = Field(
        default="", alias="APPLICATIONINSIGHTS_CONNECTION_STRING"
    )
    key_vault_url: str = Field(default="", alias="KEY_VAULT_URL")
    use_managed_identity: bool = Field(
        default=False, alias="USE_MANAGED_IDENTITY"
    )
    internal_api_audience: str = Field(
        default="api://azure-cost-advisor-services",
        alias="INTERNAL_API_AUDIENCE",
    )
    auth_service_url: str = Field(
        default="http://auth-service:8000", alias="AUTH_SERVICE_URL"
    )
    collection_service_url: str = Field(
        default="http://collection-service:8000",
        alias="COLLECTION_SERVICE_URL",
    )
    processing_service_url: str = Field(
        default="http://processing-service:8000",
        alias="PROCESSING_SERVICE_URL",
    )
    ai_service_url: str = Field(
        default="http://ai-service:8000", alias="AI_SERVICE_URL"
    )
    notification_service_url: str = Field(
        default="http://notification-service:8000",
        alias="NOTIFICATION_SERVICE_URL",
    )
    api_rate_limit_per_minute: int = Field(
        default=120, alias="API_RATE_LIMIT_PER_MINUTE", ge=1
    )
    email_connection_string: str = Field(
        default="", alias="AZURE_COMMUNICATION_EMAIL_CONNECTION_STRING"
    )
    email_sender: str = Field(default="", alias="NOTIFICATION_EMAIL_SENDER")
    retention_days: int = Field(default=365, alias="DATA_RETENTION_DAYS", ge=1)

    azure_openai_endpoint: str = Field(default="", alias="AZURE_OPENAI_ENDPOINT")
    azure_openai_api_key: str = Field(default="", alias="AZURE_OPENAI_API_KEY")
    azure_openai_api_version: str = Field(
        default="2024-08-01-preview", alias="AZURE_OPENAI_API_VERSION"
    )
    azure_openai_deployment_name: str = Field(
        default="gpt-4o", alias="AZURE_OPENAI_DEPLOYMENT_NAME"
    )
    azure_openai_embedding_deployment: str = Field(
        default="text-embedding-3-small", alias="AZURE_OPENAI_EMBEDDING_DEPLOYMENT"
    )
    ai_debug_mode: bool = Field(default=False, alias="AI_DEBUG_MODE")
    search_provider: str = Field(
        default="azure_ai_search", alias="SEARCH_PROVIDER"
    )
    azure_search_endpoint: str = Field(default="", alias="AZURE_SEARCH_ENDPOINT")
    azure_search_api_key: str = Field(default="", alias="AZURE_SEARCH_API_KEY")
    azure_search_index_name: str = Field(
        default="finops-knowledge", alias="AZURE_SEARCH_INDEX_NAME"
    )
    azure_search_semantic_config: str = Field(
        default="finops-semantic", alias="AZURE_SEARCH_SEMANTIC_CONFIG"
    )
    azure_search_vector_dimensions: int = Field(
        default=1536, alias="AZURE_SEARCH_VECTOR_DIMENSIONS", ge=1
    )

    data_raw_dir: str = Field(default="data/raw", alias="DATA_RAW_DIR")
    data_processed_dir: str = Field(default="data/processed", alias="DATA_PROCESSED_DIR")
    data_embeddings_dir: str = Field(
        default="data/embeddings", alias="DATA_EMBEDDINGS_DIR"
    )

    cost_lookback_days: int = Field(default=30, alias="COST_LOOKBACK_DAYS")
    anomaly_zscore_threshold: float = Field(
        default=2.5, alias="ANOMALY_ZSCORE_THRESHOLD"
    )
    waste_idle_cpu_threshold: float = Field(
        default=5.0, alias="WASTE_IDLE_CPU_THRESHOLD"
    )
    waste_min_monthly_cost: float = Field(
        default=10.0, alias="WASTE_MIN_MONTHLY_COST"
    )
    collection_interval_minutes: int = Field(
        default=1440, alias="COLLECTION_INTERVAL_MINUTES", ge=1
    )
    collection_mode: str = Field(default="auto", alias="COLLECTION_MODE")
    collection_scheduler_enabled: bool = Field(
        default=False, alias="COLLECTION_SCHEDULER_ENABLED"
    )

    streamlit_server_port: int = Field(default=8501, alias="STREAMLIT_SERVER_PORT")

    @property
    def project_root(self) -> Path:
        return _project_root()

    @property
    def raw_path(self) -> Path:
        return self.project_root / self.data_raw_dir

    @property
    def storage_path(self) -> Path:
        path = Path(self.storage_data_dir)
        raw = Path(self.data_raw_dir)
        if self.storage_data_dir == "data" and raw.is_absolute():
            return raw.parent
        return path if path.is_absolute() else self.project_root / path

    @property
    def processed_path(self) -> Path:
        return self.project_root / self.data_processed_dir

    @property
    def embeddings_path(self) -> Path:
        return self.project_root / self.data_embeddings_dir

    @property
    def faiss_index_path(self) -> Path:
        return self.embeddings_path / "faiss_index"

    @property
    def effective_tenant_id(self) -> str:
        return (
            self.default_tenant_id
            or self.azure_tenant_id
            or "local-default-tenant"
        )

    @property
    def effective_subscription_id(self) -> str:
        return (
            self.default_subscription_id
            or self.azure_subscription_id
            or "local-default-subscription"
        )

    @property
    def azure_credentials_configured(self) -> bool:
        return all(
            [
                self.azure_subscription_id,
                self.azure_tenant_id,
                self.azure_client_id,
                self.azure_client_secret,
            ]
        )

    @property
    def openai_configured(self) -> bool:
        return bool(
            self.azure_openai_endpoint
            and (self.azure_openai_api_key or self.use_managed_identity)
        )

    @property
    def entra_auth_enabled(self) -> bool:
        return self.auth_mode.lower() == "entra"

    @property
    def entra_auth_configured(self) -> bool:
        return bool(self.entra_client_id and self.entra_client_secret)

    @property
    def azure_search_configured(self) -> bool:
        return bool(
            self.azure_search_endpoint
            and (
                self.azure_search_api_key
                or self.use_managed_identity
                or self.azure_credentials_configured
            )
        )

    @property
    def cors_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.api_cors_origins.split(",")
            if origin.strip()
        ]

    def ensure_data_dirs(self) -> None:
        for path in (self.raw_path, self.processed_path, self.embeddings_path):
            path.mkdir(parents=True, exist_ok=True)


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
        _settings.ensure_data_dirs()
    return _settings
