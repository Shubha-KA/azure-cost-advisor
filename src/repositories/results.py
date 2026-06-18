"""Repository operation result models."""

from pydantic import BaseModel


class WriteResult(BaseModel):
    inserted: int = 0
    updated: int = 0
    path: str = ""
