"""Schemas specific to the pricing_packaging collector."""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

from rrxray.schemas.data import Finding, SourceCitation


class PricingTier(BaseModel):
    name: str
    price: str
    cadence: str
    notes: str = ""


class PricingChange(BaseModel):
    date_observed: date
    kind: Literal[
        "tier_added",
        "tier_removed",
        "price_increased",
        "price_decreased",
        "gating_added",
        "gating_removed",
        "cta_changed",
    ]
    before: str
    after: str


class HistoricalSnapshot(BaseModel):
    timestamp: datetime
    archive_url: str
    tiers: list[PricingTier] = []


class PricingPackagingData(BaseModel):
    has_public_pricing: bool
    is_contact_us_gated: bool
    current_pricing_url: str | None = None
    current_tiers: list[PricingTier] = []
    historical_snapshots: list[HistoricalSnapshot] = []
    detected_changes: list[PricingChange] = []
    findings: list[Finding] = []
    gaps: list[str] = []
    discovery_questions: list[str] = []
    sources: list[SourceCitation] = []
