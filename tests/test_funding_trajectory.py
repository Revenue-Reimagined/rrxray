"""Tests for the funding_trajectory collector."""
from __future__ import annotations

import asyncio
import json
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from rrxray.collectors.funding_trajectory import (
    NAME,
    _dedupe_rounds,
    _discover_crunchbase_url,
    _extract_press_rounds,
    _is_crunchbase_blocked,
    _scrape_crunchbase,
    _search_funding_press,
)
from rrxray.schemas.funding_trajectory import FundingRound
from rrxray.services.extraction import ExtractedFundingEvent

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "synthetic" / "funding_trajectory"


def _load_fixture(name: str) -> str:
    return (FIXTURE_DIR / name).read_text()


def _load_json_fixture(name: str):
    return json.loads((FIXTURE_DIR / name).read_text())


@pytest.fixture
def fake_firecrawl():
    fc = MagicMock()
    fc.search = AsyncMock()
    fc.scrape_url = AsyncMock()
    return fc


# --- Module identity ---

def test_name():
    assert NAME == "funding_trajectory"


# --- _is_crunchbase_blocked ---

def test_is_crunchbase_blocked_on_cloudflare():
    html = _load_fixture("crunchbase_blocked.html")
    assert _is_crunchbase_blocked(html)


def test_is_crunchbase_blocked_on_real_page():
    html = _load_fixture("crunchbase_org_page.html")
    assert not _is_crunchbase_blocked(html)


# --- _discover_crunchbase_url ---

def test_discover_crunchbase_url_finds_from_search(fake_firecrawl):
    fake_firecrawl.search.return_value = [
        {"url": "https://www.crunchbase.com/organization/acme", "title": "Acme - Crunchbase", "snippet": "Acme Corp..."},
    ]
    url = asyncio.run(
        _discover_crunchbase_url(fake_firecrawl, "Acme", "acme.com")
    )
    assert url == "https://www.crunchbase.com/organization/acme"


def test_discover_crunchbase_url_returns_none_on_no_results(fake_firecrawl):
    fake_firecrawl.search.return_value = []
    url = asyncio.run(
        _discover_crunchbase_url(fake_firecrawl, "Obscure Corp", "obscure.io")
    )
    assert url is None


def test_discover_crunchbase_url_ignores_non_org_results(fake_firecrawl):
    fake_firecrawl.search.return_value = [
        {"url": "https://www.crunchbase.com/person/john-doe", "title": "John Doe - Crunchbase", "snippet": "..."},
    ]
    url = asyncio.run(
        _discover_crunchbase_url(fake_firecrawl, "Acme", "acme.com")
    )
    assert url is None


def test_discover_crunchbase_url_returns_none_on_exception(fake_firecrawl):
    fake_firecrawl.search.side_effect = Exception("network error")
    url = asyncio.run(
        _discover_crunchbase_url(fake_firecrawl, "Acme", "acme.com")
    )
    assert url is None


# --- _scrape_crunchbase ---

def test_scrape_crunchbase_returns_rounds(fake_firecrawl):
    fake_firecrawl.scrape_url.return_value = {"html": _load_fixture("crunchbase_org_page.html"), "markdown": ""}
    rounds = asyncio.run(
        _scrape_crunchbase(fake_firecrawl, "https://www.crunchbase.com/organization/acme")
    )
    assert len(rounds) >= 2
    series_list = [r.series for r in rounds]
    assert "series_b" in series_list
    assert "series_a" in series_list


def test_scrape_crunchbase_returns_empty_on_no_funding(fake_firecrawl):
    fake_firecrawl.scrape_url.return_value = {"html": _load_fixture("crunchbase_org_page_no_funding.html"), "markdown": ""}
    rounds = asyncio.run(
        _scrape_crunchbase(fake_firecrawl, "https://www.crunchbase.com/organization/bootstrapped-co")
    )
    assert rounds == []


def test_scrape_crunchbase_returns_empty_on_blocked_page(fake_firecrawl):
    fake_firecrawl.scrape_url.return_value = {"html": _load_fixture("crunchbase_blocked.html"), "markdown": ""}
    rounds = asyncio.run(
        _scrape_crunchbase(fake_firecrawl, "https://www.crunchbase.com/organization/acme")
    )
    assert rounds == []


def test_scrape_crunchbase_round_has_expected_fields(fake_firecrawl):
    fake_firecrawl.scrape_url.return_value = {"html": _load_fixture("crunchbase_org_page.html"), "markdown": ""}
    rounds = asyncio.run(
        _scrape_crunchbase(fake_firecrawl, "https://www.crunchbase.com/organization/acme")
    )
    series_b = next((r for r in rounds if r.series == "series_b"), None)
    assert series_b is not None
    assert series_b.amount_usd_millions == 25.0
    assert series_b.lead_investor == "Sequoia Capital"
    assert series_b.source_type == "crunchbase"
    assert series_b.announced_date is not None


def test_scrape_crunchbase_returns_empty_on_scrape_exception(fake_firecrawl):
    fake_firecrawl.scrape_url.side_effect = Exception("timeout")
    rounds = asyncio.run(
        _scrape_crunchbase(fake_firecrawl, "https://www.crunchbase.com/organization/acme")
    )
    assert rounds == []


# --- _search_funding_press ---

def test_search_funding_press_returns_results(fake_firecrawl):
    fake_firecrawl.search.return_value = _load_json_fixture("press_search_has_results.json")
    results = asyncio.run(
        _search_funding_press(fake_firecrawl, "Acme")
    )
    assert len(results) == 2
    assert any("25M" in r.get("snippet", "") for r in results)


def test_search_funding_press_returns_empty_on_no_results(fake_firecrawl):
    fake_firecrawl.search.return_value = []
    results = asyncio.run(
        _search_funding_press(fake_firecrawl, "Obscure Corp")
    )
    assert results == []


def test_search_funding_press_returns_empty_on_exception(fake_firecrawl):
    fake_firecrawl.search.side_effect = Exception("timeout")
    results = asyncio.run(
        _search_funding_press(fake_firecrawl, "Acme")
    )
    assert results == []


# --- _extract_press_rounds ---

def test_extract_press_rounds_calls_extractor_per_result(fake_firecrawl):
    fake_extractor = MagicMock()
    fake_extractor.extract_funding_event = AsyncMock(return_value=ExtractedFundingEvent(
        series="series_b", amount_usd_millions=25.0, is_relevant=True,
        announced_date="2024-03-15", lead_investor="Sequoia Capital",
    ))
    fake_firecrawl.scrape_url.return_value = {"html": _load_fixture("press_body_series_b.html"), "markdown": ""}
    results_in = _load_json_fixture("press_search_has_results.json")
    rounds = asyncio.run(
        _extract_press_rounds(results_in, fake_extractor, "Acme", "acme.com", fake_firecrawl)
    )
    assert len(rounds) >= 1
    assert rounds[0].series == "series_b"
    assert rounds[0].source_type == "press"
    assert rounds[0].amount_usd_millions == 25.0


def test_extract_press_rounds_skips_irrelevant(fake_firecrawl):
    fake_extractor = MagicMock()
    fake_extractor.extract_funding_event = AsyncMock(return_value=None)
    fake_firecrawl.scrape_url.return_value = {"html": "", "markdown": ""}
    rounds = asyncio.run(
        _extract_press_rounds(
            [{"url": "https://x.com", "title": "Other Co raises $10M", "snippet": "Other Co raised."}],
            fake_extractor, "Acme", "acme.com", fake_firecrawl
        )
    )
    assert rounds == []


# --- _dedupe_rounds ---

def test_dedupe_rounds_crunchbase_wins_on_same_series():
    cb_round = FundingRound(
        series="series_b", amount_usd_millions=25.0,
        announced_date=date(2024, 3, 15), source_url="https://crunchbase.com/x",
        source_type="crunchbase",
    )
    press_round = FundingRound(
        series="series_b", amount_usd_millions=25.0,
        announced_date=date(2024, 3, 15), source_url="https://techcrunch.com/x",
        source_type="press",
    )
    result = _dedupe_rounds([cb_round], [press_round])
    assert len(result) == 1
    assert result[0].source_type == "crunchbase"


def test_dedupe_rounds_keeps_distinct_series():
    cb_round = FundingRound(
        series="series_b", announced_date=date(2024, 3, 15),
        source_url="https://crunchbase.com/x", source_type="crunchbase",
    )
    press_round = FundingRound(
        series="series_a", announced_date=date(2022, 6, 1),
        source_url="https://press.com/x", source_type="press",
    )
    result = _dedupe_rounds([cb_round], [press_round])
    assert len(result) == 2


def test_dedupe_rounds_deduplicates_by_series_when_no_dates():
    cb = FundingRound(series="seed", source_url="https://crunchbase.com/x", source_type="crunchbase")
    press = FundingRound(series="seed", source_url="https://press.com/x", source_type="press")
    result = _dedupe_rounds([cb], [press])
    assert len(result) == 1
    assert result[0].source_type == "crunchbase"


def test_dedupe_rounds_returns_reverse_chrono():
    rounds = [
        FundingRound(series="series_a", announced_date=date(2022, 6, 1),
                     source_url="https://x", source_type="crunchbase"),
        FundingRound(series="series_b", announced_date=date(2024, 3, 15),
                     source_url="https://y", source_type="crunchbase"),
    ]
    result = _dedupe_rounds(rounds, [])
    assert result[0].series == "series_b"  # most recent first
    assert result[1].series == "series_a"
