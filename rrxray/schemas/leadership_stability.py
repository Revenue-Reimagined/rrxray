"""Schemas specific to the leadership_stability collector."""
from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel

from rrxray.schemas._shared import Finding, SourceCitation

RoleCanonical = Literal[
    "ceo", "cro", "vp_sales", "vp_revenue",
    "cmo", "vp_marketing", "founder",
]


class ExecAction(StrEnum):
    HIRE = "hire"
    DEPARTURE = "departure"
    PROMOTION = "promotion"


class ExecChange(BaseModel):
    name: str
    role_canonical: RoleCanonical
    role_raw: str
    action: ExecAction
    occurred_at: date | None = None
    press_url: str
    press_title: str


class CurrentIncumbent(BaseModel):
    name: str
    role_canonical: RoleCanonical
    role_raw: str
    linkedin_url: str | None = None
    confidence: Literal["high", "low"] = "high"


class FounderTenure(BaseModel):
    inferred_year: int | None = None
    source: Literal["about_page", "wayback_homepage", "unknown"] = "unknown"
    raw_evidence: str | None = None


class NameRegistration(BaseModel):
    name: str
    role_descriptor: str
    whitelist: bool = False


class LeadershipStabilityData(BaseModel):
    exec_changes: list[ExecChange] = []
    current_incumbents: list[CurrentIncumbent] = []
    founder_tenure: FounderTenure | None = None
    name_registrations: list[NameRegistration] = []
    findings: list[Finding] = []
    gaps: list[str] = []
    discovery_questions: list[str] = []
    sources: list[SourceCitation] = []
