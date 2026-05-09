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
