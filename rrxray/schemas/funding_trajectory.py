"""Schemas for the funding_trajectory collector."""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel

from rrxray.schemas._shared import Finding, SourceCitation

FundingSeries = Literal[
    "pre_seed", "seed", "series_a", "series_b", "series_c",
    "series_d", "series_e_plus", "growth", "private_equity",
    "ipo", "acquisition", "debt", "grant", "unknown",
]

ImpliedStage = Literal[
    "bootstrapped",
    "seed",
    "early_growth",
    "growth",
    "late_growth",
    "public",
    "acquired",
    "signal_not_recovered",
]


class FundingRound(BaseModel):
    series: FundingSeries
    amount_usd_millions: float | None = None
    announced_date: date | None = None
    lead_investor: str | None = None
    source_url: str
    source_title: str | None = None
    source_type: Literal["crunchbase", "press"]


class FundingTrajectoryData(BaseModel):
    rounds: list[FundingRound] = []
    total_raised_usd_millions: float | None = None
    last_round_months_ago: int | None = None
    implied_stage: ImpliedStage = "signal_not_recovered"
    crunchbase_url: str | None = None
    crunchbase_recovered: bool = False
    findings: list[Finding] = []
    gaps: list[str] = []
    discovery_questions: list[str] = []
    sources: list[SourceCitation] = []
