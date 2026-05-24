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

    streamlit_server_port: int = Field(default=8501, alias="STREAMLIT_SERVER_PORT")

    @property
    def project_root(self) -> Path:
        return _project_root()

    @property
    def raw_path(self) -> Path:
        return self.project_root / self.data_raw_dir

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
        return bool(self.azure_openai_endpoint and self.azure_openai_api_key)

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
