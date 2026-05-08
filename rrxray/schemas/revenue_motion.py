"""Schemas specific to the revenue_motion collector."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from rrxray.schemas._shared import Finding, SourceCitation

RoleCategory = Literal[
    "ae",
    "sdr",
    "revops",
    "csm",
    "sales_leadership",
    "marketing_leadership",
    "marketing_ops",
    "other",
]


class JobPosting(BaseModel):
    title: str
    category: RoleCategory
    url: str | None = None
    source: Literal["company_careers", "ats", "linkedin"]
    location: str | None = None
    matched_keyword: str | None = None


class RevenueMotionData(BaseModel):
    careers_page_url: str | None = None
    ats_platform: str | None = None
    open_roles: list[JobPosting] = []
    role_counts: dict[str, int] = {}
    ae_to_sdr_ratio: float | None = None
    linkedin_employee_count: int | None = None
    linkedin_job_count: int | None = None
    findings: list[Finding] = []
    gaps: list[str] = []
    discovery_questions: list[str] = []
    sources: list[SourceCitation] = []
