"""Execution context shared by collectors, processing, and persistence."""

from __future__ import annotations

from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class OperationContext(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    tenant_id: str = Field(alias="tenantId", min_length=1)
    subscription_id: str = Field(alias="subscriptionId", min_length=1)
    collection_run_id: str = Field(alias="collectionRunId", min_length=1)
    processing_run_id: str = Field(alias="processingRunId", min_length=1)
    correlation_id: str = Field(alias="correlationId", min_length=1)
    schema_version: int = Field(default=1, alias="schemaVersion", ge=1, le=1)

    @classmethod
    def create(cls, tenant_id: str, subscription_id: str) -> "OperationContext":
        return cls(
            tenantId=tenant_id,
            subscriptionId=subscription_id,
            collectionRunId=str(uuid4()),
            processingRunId=str(uuid4()),
            correlationId=str(uuid4()),
            schemaVersion=1,
        )

    def document_fields(self) -> dict[str, str | int]:
        return self.model_dump(by_alias=True)
