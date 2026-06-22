"""Search document and result contracts."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeDocument(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    document_id: str = Field(alias="id")
    tenant_id: str = Field(alias="tenantId")
    subscription_id: str = Field(alias="subscriptionId")
    collection_run_id: str = Field(alias="collectionRunId")
    processing_run_id: str = Field(alias="processingRunId")
    source_system: str = Field(alias="sourceSystem")
    schema_version: int = Field(default=1, alias="schemaVersion")
    document_type: str = Field(alias="documentType")
    title: str
    content: str
    content_vector: list[float] = Field(
        default_factory=list, alias="contentVector"
    )
    metadata_json: str = Field(default="{}", alias="metadataJson")


class SearchResult(BaseModel):
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    score: float = 0
