"""Tests for the funding_trajectory collector."""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from rrxray.collectors.funding_trajectory import (
    NAME,
    _discover_crunchbase_url,
    _is_crunchbase_blocked,
    _scrape_crunchbase,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "synthetic" / "funding_trajectory"


def _load_fixture(name: str) -> str:
    return (FIXTURE_DIR / name).read_text()


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
