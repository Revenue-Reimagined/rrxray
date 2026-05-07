"""Schemas specific to the tech_stack collector."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from rrxray.schemas._shared import Finding, SourceCitation

Category = Literal[
    "analytics",
    "tag_manager",
    "marketing_automation",
    "chat",
    "product_analytics",
    "crm",
    "cdp",
    "ab_testing",
    "attribution",
]


class DetectedTool(BaseModel):
    name: str
    category: Category
    confidence: Literal["high", "low"]
    signature_id: str
    matched_text: str


class TechStackData(BaseModel):
    detected_tools: list[DetectedTool] = []
    categories_observed: list[Category] = []
    categories_absent: list[Category] = []
    findings: list[Finding] = []
    gaps: list[str] = []
    discovery_questions: list[str] = []
    sources: list[SourceCitation] = []
