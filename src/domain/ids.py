"""Deterministic identifiers for idempotent repository writes."""

from __future__ import annotations

import hashlib


def deterministic_id(*parts: object) -> str:
    value = "|".join(str(part or "").strip().lower() for part in parts)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
