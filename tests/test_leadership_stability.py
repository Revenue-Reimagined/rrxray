"""Tests for leadership_stability collector — press release path."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from rrxray.collectors import leadership_stability
from rrxray.collectors.leadership_stability import (
    _extract_exec_changes,
    _search_press_releases,
)
from rrxray.schemas.leadership_stability import ExecAction

FIXTURES = Path(__file__).parent / "fixtures" / "synthetic" / "leadership_stability"


def _load_search_response(name: str):
    """Load a search-response fixture as a list of dicts."""
    return json.loads((FIXTURES / name).read_text())


def _make_search_results(payload):
    from rrxray.services.firecrawl_client import SearchResult
    return [SearchResult(**r) for r in payload]


@pytest.fixture
def fake_firecrawl():
    f = MagicMock()
    f.search = AsyncMock()
    return f


def test_collector_module_has_NAME():
    assert leadership_stability.NAME == "leadership_stability"


def test_search_press_releases_runs_three_action_queries(fake_firecrawl):
    fake_firecrawl.search.side_effect = [
        _make_search_results(_load_search_response("press_search_hires_response.json")),
        _make_search_results(_load_search_response("press_search_departures_response.json")),
        _make_search_results(_load_search_response("press_search_promotions_response.json")),
    ]

    asyncio.run(_search_press_releases(fake_firecrawl, company="Acme"))

    assert fake_firecrawl.search.call_count == 3
    # Verify the three action keywords appear in the queries
    queries = [call.args[0] for call in fake_firecrawl.search.call_args_list]
    assert any("appoints" in q.lower() for q in queries)
    assert any("departs" in q.lower() for q in queries)
    assert any("promoted" in q.lower() for q in queries)


def test_search_press_releases_dedupes_by_url(fake_firecrawl):
    """Same URL across two action queries appears once in the result list."""
    fake_firecrawl.search.side_effect = [
        _make_search_results([
            {"url": "https://example.com/press/1", "title": "A", "description": "B"},
        ]),
        _make_search_results([
            {"url": "https://example.com/press/1", "title": "A", "description": "B"},  # duplicate
            {"url": "https://example.com/press/2", "title": "C", "description": "D"},
        ]),
        _make_search_results([]),
    ]

    results = asyncio.run(_search_press_releases(fake_firecrawl, company="Acme"))

    urls = [r.url for r in results]
    assert urls == ["https://example.com/press/1", "https://example.com/press/2"]


def test_search_press_releases_handles_failure_gracefully(fake_firecrawl):
    """One action-query failure does not abort other action queries."""
    from rrxray.services.firecrawl_client import FirecrawlError

    fake_firecrawl.search.side_effect = [
        _make_search_results(_load_search_response("press_search_hires_response.json")),
        FirecrawlError("simulated departures failure"),
        _make_search_results(_load_search_response("press_search_promotions_response.json")),
    ]

    results = asyncio.run(_search_press_releases(fake_firecrawl, company="Acme"))
    # Got hires + promotions but not departures
    assert len(results) >= 1
    assert fake_firecrawl.search.call_count == 3


def test_extract_exec_changes_filters_irrelevant():
    """Extractor returning is_relevant=False results are dropped."""
    from rrxray.services.extraction import ExtractedExecChange
    from rrxray.services.firecrawl_client import SearchResult

    results = [
        SearchResult(url="u1", title="Acme Names Jane Doe as CRO", description="..."),
        SearchResult(url="u2", title="Acme Q3 Earnings Call", description="..."),
    ]

    extractor = MagicMock()
    extractor.extract_exec_change = AsyncMock(side_effect=[
        ExtractedExecChange(name="Jane Doe", role_canonical="cro", role_raw="CRO", action=ExecAction.HIRE, is_relevant=True),
        None,  # irrelevant
    ])

    changes = asyncio.run(_extract_exec_changes(results, extractor))

    assert len(changes) == 1
    assert changes[0].name == "Jane Doe"
    assert changes[0].press_url == "u1"


def test_extract_exec_changes_handles_extractor_none():
    """Extractor returning None for a result skips it without error."""
    from rrxray.services.firecrawl_client import SearchResult

    results = [
        SearchResult(url="u1", title="x", description="y"),
        SearchResult(url="u2", title="x", description="y"),
    ]

    extractor = MagicMock()
    extractor.extract_exec_change = AsyncMock(side_effect=[None, None])

    changes = asyncio.run(_extract_exec_changes(results, extractor))
    assert changes == []


def test_search_linkedin_incumbents_runs_seven_role_queries(fake_firecrawl):
    from rrxray.collectors.leadership_stability import _search_linkedin_incumbents

    # LEADERSHIP_ROLES order: ceo, cro, vp_sales, vp_revenue, cmo, vp_marketing, founder
    fake_firecrawl.search.side_effect = [
        _make_search_results(_load_search_response("linkedin_empty_response.json")),  # ceo
        _make_search_results(_load_search_response("linkedin_cro_response.json")),    # cro
        _make_search_results(_load_search_response("linkedin_empty_response.json")),  # vp_sales
        _make_search_results(_load_search_response("linkedin_empty_response.json")),  # vp_revenue
        _make_search_results(_load_search_response("linkedin_cmo_response.json")),    # cmo
        _make_search_results(_load_search_response("linkedin_empty_response.json")),  # vp_marketing
        _make_search_results(_load_search_response("linkedin_empty_response.json")),  # founder
    ]

    results_by_role = asyncio.run(_search_linkedin_incumbents(fake_firecrawl, company="Acme"))

    assert fake_firecrawl.search.call_count == 7
    assert set(results_by_role.keys()) == {"ceo", "cro", "vp_sales", "vp_revenue", "cmo", "vp_marketing", "founder"}
    assert len(results_by_role["cro"]) == 2  # CRO fixture had 2 results
    assert len(results_by_role["cmo"]) == 1


def test_search_linkedin_incumbents_handles_per_role_failure(fake_firecrawl):
    from rrxray.collectors.leadership_stability import _search_linkedin_incumbents
    from rrxray.services.firecrawl_client import FirecrawlError

    # First role (ceo) fails; rest return empty
    fake_firecrawl.search.side_effect = [
        FirecrawlError("simulated"),
    ] + [_make_search_results([])] * 6

    results_by_role = asyncio.run(_search_linkedin_incumbents(fake_firecrawl, company="Acme"))

    # Failed role gets empty list, not missing key
    assert results_by_role["ceo"] == []
    assert fake_firecrawl.search.call_count == 7


def test_extract_current_incumbents_dedupes_by_role_name():
    """Same (role, name) returned by LinkedIn search across queries: one record."""
    from rrxray.collectors.leadership_stability import _extract_current_incumbents
    from rrxray.services.extraction import ExtractedLinkedInIncumbent
    from rrxray.services.firecrawl_client import SearchResult

    results_by_role = {
        "cro": [
            SearchResult(url="https://www.linkedin.com/in/jane-doe-1", title="Jane Doe CRO", description="..."),
            SearchResult(url="https://www.linkedin.com/in/jane-doe-2", title="Jane Doe CRO", description="..."),
        ],
        "cmo": [],
        "ceo": [],
        "vp_sales": [],
        "vp_revenue": [],
        "vp_marketing": [],
        "founder": [],
    }

    extractor = MagicMock()
    extractor.extract_linkedin_role = AsyncMock(side_effect=[
        ExtractedLinkedInIncumbent(name="Jane Doe", role_canonical="cro", role_raw="CRO", is_relevant=True),
        ExtractedLinkedInIncumbent(name="Jane Doe", role_canonical="cro", role_raw="CRO", is_relevant=True),
    ])

    incumbents = asyncio.run(_extract_current_incumbents(results_by_role, extractor))

    assert len(incumbents) == 1
    assert incumbents[0].name == "Jane Doe"
    assert incumbents[0].role_canonical == "cro"


def test_extract_current_incumbents_marks_post_url_low_confidence():
    """LinkedIn /posts/ URL gets confidence='low'; /in/ URL gets confidence='high'."""
    from rrxray.collectors.leadership_stability import _extract_current_incumbents
    from rrxray.services.extraction import ExtractedLinkedInIncumbent
    from rrxray.services.firecrawl_client import SearchResult

    results_by_role = {
        "cmo": [
            SearchResult(url="https://www.linkedin.com/posts/sara-lee_cmo-acme-activity-12345", title="Sara Lee CMO", description="..."),
        ],
        "cro": [
            SearchResult(url="https://www.linkedin.com/in/bob-cro", title="Bob CRO", description="..."),
        ],
        "ceo": [],
        "vp_sales": [],
        "vp_revenue": [],
        "vp_marketing": [],
        "founder": [],
    }

    extractor = MagicMock()
    extractor.extract_linkedin_role = AsyncMock(side_effect=[
        ExtractedLinkedInIncumbent(name="Sara Lee", role_canonical="cmo", role_raw="CMO", is_relevant=True),
        ExtractedLinkedInIncumbent(name="Bob", role_canonical="cro", role_raw="CRO", is_relevant=True),
    ])

    incumbents = asyncio.run(_extract_current_incumbents(results_by_role, extractor))

    by_name = {i.name: i for i in incumbents}
    assert by_name["Sara Lee"].confidence == "low"
    assert by_name["Bob"].confidence == "high"


def test_extract_current_incumbents_drops_irrelevant():
    from rrxray.collectors.leadership_stability import _extract_current_incumbents
    from rrxray.services.firecrawl_client import SearchResult

    results_by_role = {
        "cro": [SearchResult(url="https://www.linkedin.com/in/x", title="x", description="y")],
        "ceo": [], "cmo": [], "vp_sales": [], "vp_revenue": [], "vp_marketing": [], "founder": [],
    }
    extractor = MagicMock()
    extractor.extract_linkedin_role = AsyncMock(return_value=None)

    incumbents = asyncio.run(_extract_current_incumbents(results_by_role, extractor))
    assert incumbents == []


def test_infer_founder_tenure_about_page_path(fake_firecrawl):
    """F1 path: /about page with 'Founded in YYYY' -> FounderTenure(source='about_page')."""
    from rrxray.collectors.leadership_stability import _infer_founder_tenure
    from rrxray.services.firecrawl_client import ScrapedPage

    about_html = (FIXTURES / "about_page_with_founding_year.html").read_text()
    fake_firecrawl.scrape_url = AsyncMock(return_value=ScrapedPage(
        url="https://acme.com/about", html=about_html, markdown=about_html,
    ))

    fake_wayback = MagicMock()
    fake_wayback.snapshots = AsyncMock()  # should not be called

    tenure = asyncio.run(_infer_founder_tenure(fake_firecrawl, fake_wayback, "acme.com"))

    assert tenure.inferred_year == 2018
    assert tenure.source == "about_page"
    assert tenure.raw_evidence is not None
    fake_wayback.snapshots.assert_not_called()


def test_infer_founder_tenure_wayback_fallback(fake_firecrawl):
    """F1 yields no year -> F2 (Wayback oldest snapshot) provides year."""
    from datetime import UTC, datetime

    from rrxray.collectors.leadership_stability import _infer_founder_tenure
    from rrxray.services.firecrawl_client import ScrapedPage
    from rrxray.services.wayback_client import Snapshot

    about_html = (FIXTURES / "about_page_no_founding_year.html").read_text()
    fake_firecrawl.scrape_url = AsyncMock(return_value=ScrapedPage(
        url="https://acme.com/about", html=about_html, markdown=about_html,
    ))

    fake_wayback = MagicMock()
    fake_wayback.snapshots = AsyncMock(return_value=[
        Snapshot(
            timestamp=datetime(2020, 6, 1, tzinfo=UTC),
            archive_url="https://web.archive.org/web/20200601000000/https://acme.com",
            html="<html>...</html>",
            markdown="...",
        ),
        Snapshot(
            timestamp=datetime(2014, 6, 1, tzinfo=UTC),
            archive_url="https://web.archive.org/web/20140601000000/https://acme.com",
            html="<html>...</html>",
            markdown="...",
        ),
    ])

    tenure = asyncio.run(_infer_founder_tenure(fake_firecrawl, fake_wayback, "acme.com"))

    assert tenure.inferred_year == 2014
    assert tenure.source == "wayback_homepage"


def test_infer_founder_tenure_unknown(fake_firecrawl):
    """Both F1 and F2 fail -> source='unknown'."""
    from rrxray.collectors.leadership_stability import _infer_founder_tenure
    from rrxray.services.firecrawl_client import FirecrawlError

    fake_firecrawl.scrape_url = AsyncMock(side_effect=FirecrawlError("about page unreachable"))

    fake_wayback = MagicMock()
    fake_wayback.snapshots = AsyncMock(return_value=[])

    tenure = asyncio.run(_infer_founder_tenure(fake_firecrawl, fake_wayback, "acme.com"))

    assert tenure.inferred_year is None
    assert tenure.source == "unknown"


def test_infer_founder_tenure_about_page_failure_falls_through(fake_firecrawl):
    """Firecrawl error on /about -> still tries Wayback fallback."""
    from datetime import UTC, datetime

    from rrxray.collectors.leadership_stability import _infer_founder_tenure
    from rrxray.services.firecrawl_client import FirecrawlError
    from rrxray.services.wayback_client import Snapshot

    fake_firecrawl.scrape_url = AsyncMock(side_effect=FirecrawlError("about unreachable"))

    fake_wayback = MagicMock()
    fake_wayback.snapshots = AsyncMock(return_value=[
        Snapshot(
            timestamp=datetime(2016, 1, 1, tzinfo=UTC),
            archive_url="https://web.archive.org/web/20160101000000/https://acme.com",
            html="x", markdown="y",
        ),
    ])

    tenure = asyncio.run(_infer_founder_tenure(fake_firecrawl, fake_wayback, "acme.com"))

    assert tenure.source == "wayback_homepage"
    assert tenure.inferred_year == 2016
