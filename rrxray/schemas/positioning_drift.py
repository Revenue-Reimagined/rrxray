"""Schemas for the positioning_drift collector."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from rrxray.schemas._shared import Finding, SourceCitation


class HomepageSnapshot(BaseModel):
    timestamp: date
    archive_url: str
    hero_headline: str | None = None
    sub_headline: str | None = None
    primary_nav: list[str] = []


class PositioningDriftData(BaseModel):
    snapshots: list[HomepageSnapshot] = []
    oldest_snapshot: HomepageSnapshot | None = None
    newest_snapshot: HomepageSnapshot | None = None
    changed_fields: list[str] = []
    diff_summary: str | None = None
    findings: list[Finding] = []
    gaps: list[str] = []
    discovery_questions: list[str] = []
    sources: list[SourceCitation] = []
