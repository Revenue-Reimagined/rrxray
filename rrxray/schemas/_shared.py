"""Shared base types used by both data.py and collector schemas.

Kept in a separate module to avoid circular imports when collector schemas
(e.g. pricing_packaging) need Finding/SourceCitation but data.py also imports
those same collector schemas (for forward-ref resolution via model_rebuild).
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class SourceCitation(BaseModel):
    url: str
    timestamp: datetime
    evidence_path: str | None = None


class Finding(BaseModel):
    text: str
    source: SourceCitation
