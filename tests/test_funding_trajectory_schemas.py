"""Schema integrity tests for FundingTrajectoryData."""
from __future__ import annotations

from datetime import UTC, date, datetime

from rrxray.schemas._shared import SourceCitation
from rrxray.schemas.funding_trajectory import FundingRound, FundingTrajectoryData


def _source() -> SourceCitation:
    return SourceCitation(url="https://example.com", timestamp=datetime(2026, 5, 15, tzinfo=UTC))


def test_funding_round_minimal():
    r = FundingRound(series="series_b", source_url="https://crunchbase.com/x", source_type="crunchbase")
    assert r.series == "series_b"
    assert r.amount_usd_millions is None
    assert r.announced_date is None
    assert r.lead_investor is None


def test_funding_round_full():
    r = FundingRound(
        series="series_b",
        amount_usd_millions=25.0,
        announced_date=date(2024, 3, 15),
        lead_investor="Sequoia Capital",
        source_url="https://crunchbase.com/x",
        source_title="Acme raises $25M Series B",
        source_type="crunchbase",
    )
    assert r.amount_usd_millions == 25.0
    assert r.lead_investor == "Sequoia Capital"
    assert r.source_type == "crunchbase"


def test_funding_trajectory_data_defaults():
    d = FundingTrajectoryData()
    assert d.rounds == []
    assert d.total_raised_usd_millions is None
    assert d.last_round_months_ago is None
    assert d.implied_stage == "signal_not_recovered"
    assert d.crunchbase_url is None
    assert d.crunchbase_recovered is False
    assert d.findings == []
    assert d.gaps == []
    assert d.discovery_questions == []
    assert d.sources == []


def test_funding_trajectory_data_with_rounds():
    d = FundingTrajectoryData(
        rounds=[
            FundingRound(series="series_b", amount_usd_millions=25.0, source_url="https://x", source_type="crunchbase"),
            FundingRound(series="series_a", amount_usd_millions=8.0, source_url="https://y", source_type="press"),
        ],
        total_raised_usd_millions=33.0,
        last_round_months_ago=14,
        implied_stage="early_growth",
        crunchbase_url="https://crunchbase.com/organization/acme",
        crunchbase_recovered=True,
    )
    assert len(d.rounds) == 2
    assert d.implied_stage == "early_growth"
    assert d.total_raised_usd_millions == 33.0


def test_implied_stage_literals():
    valid_stages = [
        "bootstrapped", "seed", "early_growth", "growth",
        "late_growth", "public", "acquired", "signal_not_recovered",
    ]
    for s in valid_stages:
        d = FundingTrajectoryData(implied_stage=s)
        assert d.implied_stage == s


def test_funding_round_source_type_literal():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        FundingRound(series="seed", source_url="https://x", source_type="invalid")
