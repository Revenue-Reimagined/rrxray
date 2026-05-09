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


def test_extract_current_incumbents_keeps_only_top_match_per_role():
    """Per spec, only the first relevant extraction for a role becomes the
    incumbent. Subsequent same-role results with different names are dropped
    even though the (role, name) dedup key is different."""
    from rrxray.collectors.leadership_stability import _extract_current_incumbents
    from rrxray.services.extraction import ExtractedLinkedInIncumbent
    from rrxray.services.firecrawl_client import SearchResult

    results_by_role = {
        "cro": [
            SearchResult(url="https://www.linkedin.com/in/first-cro", title="First CRO", description="..."),
            SearchResult(url="https://www.linkedin.com/in/second-cro", title="Second CRO", description="..."),
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
        ExtractedLinkedInIncumbent(name="First Person", role_canonical="cro", role_raw="CRO", is_relevant=True),
        ExtractedLinkedInIncumbent(name="Second Person", role_canonical="cro", role_raw="CRO", is_relevant=True),
    ])

    incumbents = asyncio.run(_extract_current_incumbents(results_by_role, extractor))

    assert len(incumbents) == 1
    assert incumbents[0].name == "First Person"


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


# ----------------------------------------------------------------------------
# T10 — Name registrations
# ----------------------------------------------------------------------------


def test_build_name_registrations_press_whitelisted():
    from rrxray.collectors.leadership_stability import _build_name_registrations
    from rrxray.schemas.leadership_stability import ExecAction, ExecChange

    exec_changes = [
        ExecChange(
            name="Jane Doe", role_canonical="cro", role_raw="CRO",
            action=ExecAction.HIRE,
            press_url="https://example.com/p/1",
            press_title="Acme Names Jane Doe as CRO",
        ),
    ]
    registrations = _build_name_registrations(exec_changes, [], company="Acme")

    assert len(registrations) == 1
    assert registrations[0].name == "Jane Doe"
    assert registrations[0].whitelist is True
    assert "CRO" in registrations[0].role_descriptor
    assert "Acme" in registrations[0].role_descriptor


def test_build_name_registrations_linkedin_not_whitelisted():
    from rrxray.collectors.leadership_stability import _build_name_registrations
    from rrxray.schemas.leadership_stability import CurrentIncumbent

    incumbents = [
        CurrentIncumbent(name="Bob Smith", role_canonical="cmo", role_raw="CMO"),
    ]
    registrations = _build_name_registrations([], incumbents, company="Acme")

    assert len(registrations) == 1
    assert registrations[0].name == "Bob Smith"
    assert registrations[0].whitelist is False


def test_build_name_registrations_dedupes():
    """Same name in press + LinkedIn → single registration; press takes precedence."""
    from rrxray.collectors.leadership_stability import _build_name_registrations
    from rrxray.schemas.leadership_stability import (
        CurrentIncumbent,
        ExecAction,
        ExecChange,
    )

    exec_changes = [
        ExecChange(
            name="Jane Doe", role_canonical="cro", role_raw="CRO",
            action=ExecAction.HIRE,
            press_url="x", press_title="y",
        ),
    ]
    incumbents = [
        CurrentIncumbent(name="Jane Doe", role_canonical="cro", role_raw="CRO"),
    ]
    registrations = _build_name_registrations(exec_changes, incumbents, company="Acme")

    assert len(registrations) == 1
    assert registrations[0].whitelist is True  # press wins


def test_build_name_registrations_role_descriptor_format():
    from rrxray.collectors.leadership_stability import _build_name_registrations
    from rrxray.schemas.leadership_stability import CurrentIncumbent

    incumbents = [
        CurrentIncumbent(name="Bob Smith", role_canonical="vp_sales", role_raw="VP of Sales"),
    ]
    registrations = _build_name_registrations([], incumbents, company="Acme")

    # Format: "Acme's VP Sales"
    assert registrations[0].role_descriptor == "Acme's VP Sales"


# ----------------------------------------------------------------------------
# T10 — Findings emission
# ----------------------------------------------------------------------------


def test_emit_findings_seat_turnover():
    """≥2 changes in same seat in past 18 months → seat-turnover finding."""
    from datetime import date, timedelta

    from rrxray.collectors.leadership_stability import _emit_findings
    from rrxray.schemas.leadership_stability import ExecAction, ExecChange, FounderTenure

    today = date.today()
    exec_changes = [
        ExecChange(
            name="Person A", role_canonical="cro", role_raw="CRO",
            action=ExecAction.HIRE,
            occurred_at=today - timedelta(days=400),
            press_url="x", press_title="y",
        ),
        ExecChange(
            name="Person B", role_canonical="cro", role_raw="CRO",
            action=ExecAction.HIRE,
            occurred_at=today - timedelta(days=120),
            press_url="x", press_title="y",
        ),
    ]
    findings, _gaps, _questions = _emit_findings(
        exec_changes, current_incumbents=[], founder_tenure=FounderTenure(),
    )

    finding_texts = [f.text for f in findings]
    assert any("turned over" in t.lower() and "cro" in t.lower() for t in finding_texts)


def test_emit_findings_seat_turnover_anchors_to_most_recent():
    """Rule 1 (≥2 changes in same seat) must anchor to the change with the
    most recent occurred_at, not list-order. Otherwise the source URL on the
    finding can point to the older event when the collector receives results
    in arbitrary order."""
    from datetime import date, timedelta

    from rrxray.collectors.leadership_stability import _emit_findings
    from rrxray.schemas.leadership_stability import ExecAction, ExecChange, FounderTenure

    today = date.today()
    older = ExecChange(
        name="Old Person", role_canonical="cro", role_raw="CRO",
        action=ExecAction.HIRE,
        occurred_at=today - timedelta(days=200),
        press_url="https://example.com/older",
        press_title="older",
    )
    newer = ExecChange(
        name="New Person", role_canonical="cro", role_raw="CRO",
        action=ExecAction.HIRE,
        occurred_at=today - timedelta(days=60),
        press_url="https://example.com/newer",
        press_title="newer",
    )
    # Older first, newer second — list-order would pick the older URL.
    findings, _gaps, _questions = _emit_findings(
        [older, newer], current_incumbents=[], founder_tenure=FounderTenure(),
    )

    seat_findings = [
        f for f in findings if "turned over" in f.text.lower()
    ]
    assert len(seat_findings) == 1
    assert seat_findings[0].source.url == "https://example.com/newer"


def test_emit_findings_recent_change():
    """1 change in seat within 270 days → in-transition finding."""
    from datetime import date, timedelta

    from rrxray.collectors.leadership_stability import _emit_findings
    from rrxray.schemas.leadership_stability import (
        CurrentIncumbent,
        ExecAction,
        ExecChange,
        FounderTenure,
    )

    today = date.today()
    exec_changes = [
        ExecChange(
            name="Jane", role_canonical="cro", role_raw="CRO",
            action=ExecAction.HIRE,
            occurred_at=today - timedelta(days=120),
            press_url="x", press_title="y",
        ),
    ]
    incumbents = [CurrentIncumbent(name="Jane", role_canonical="cro", role_raw="CRO")]
    findings, _gaps, _questions = _emit_findings(
        exec_changes, incumbents, FounderTenure(),
    )

    finding_texts = [f.text for f in findings]
    assert any("transition" in t.lower() for t in finding_texts)


def test_emit_findings_concurrent_revenue_marketing():
    """Recent CRO/VP Sales hire AND recent VP Marketing/CMO hire → cross-function finding."""
    from datetime import date, timedelta

    from rrxray.collectors.leadership_stability import _emit_findings
    from rrxray.schemas.leadership_stability import ExecAction, ExecChange, FounderTenure

    today = date.today()
    exec_changes = [
        ExecChange(
            name="A", role_canonical="cro", role_raw="CRO",
            action=ExecAction.HIRE,
            occurred_at=today - timedelta(days=100),
            press_url="x", press_title="y",
        ),
        ExecChange(
            name="B", role_canonical="cmo", role_raw="CMO",
            action=ExecAction.HIRE,
            occurred_at=today - timedelta(days=150),
            press_url="x", press_title="y",
        ),
    ]
    findings, _gaps, _questions = _emit_findings(exec_changes, [], FounderTenure())

    finding_texts = [f.text for f in findings]
    assert any("revenue and marketing" in t.lower() or "redesigned" in t.lower() for t in finding_texts)


def test_emit_findings_founder_led_long_tenure():
    """Founder ≥7 years AND current CEO incumbent matches founder → stability finding."""
    from datetime import date

    from rrxray.collectors.leadership_stability import _emit_findings
    from rrxray.schemas.leadership_stability import CurrentIncumbent, FounderTenure

    incumbents = [
        CurrentIncumbent(name="Jane Doe", role_canonical="ceo", role_raw="CEO"),
        CurrentIncumbent(name="Jane Doe", role_canonical="founder", role_raw="Founder"),
    ]
    tenure = FounderTenure(inferred_year=date.today().year - 8, source="about_page")

    findings, _gaps, _questions = _emit_findings([], incumbents, tenure)

    finding_texts = [f.text for f in findings]
    assert any("founder-led" in t.lower() for t in finding_texts)


def test_emit_findings_no_press_signal():
    """LinkedIn returned ≥1 incumbent AND zero exec changes → stability inferred."""
    from rrxray.collectors.leadership_stability import _emit_findings
    from rrxray.schemas.leadership_stability import CurrentIncumbent, FounderTenure

    incumbents = [
        CurrentIncumbent(name="x", role_canonical="cro", role_raw="CRO"),
    ]
    findings, _gaps, _questions = _emit_findings([], incumbents, FounderTenure())

    finding_texts = [f.text for f in findings]
    assert any("stability inferred" in t.lower() or "no public exec announcements" in t.lower() for t in finding_texts)


def test_emit_findings_total_signal_loss():
    """All paths empty → 'signal not recovered' finding."""
    from rrxray.collectors.leadership_stability import _emit_findings
    from rrxray.schemas.leadership_stability import FounderTenure

    findings, _gaps, _questions = _emit_findings([], [], FounderTenure(source="unknown"))

    finding_texts = [f.text for f in findings]
    assert any("not recovered" in t.lower() or "discovery" in t.lower() for t in finding_texts)


def test_collect_writes_evidence(tmp_path):
    """All four evidence files written under evidence/leadership_stability/."""
    from rrxray.collectors.leadership_stability import collect
    from rrxray.config import Config
    from rrxray.context import CollectorContext
    from rrxray.services.extraction import ExecAction, ExtractedExecChange
    from rrxray.services.firecrawl_client import ScrapedPage, SearchResult

    fake_firecrawl = MagicMock()
    fake_firecrawl.search = AsyncMock(side_effect=[
        # press hires/departures/promotions
        [SearchResult(url="u1", title="Acme Names Jane Doe as CRO", description="...")],
        [],
        [],
        # 7 LinkedIn role queries
        [SearchResult(url="https://www.linkedin.com/in/jane-doe", title="Jane CRO", description="...")],
        [], [], [], [], [], [],
    ])
    fake_firecrawl.scrape_url = AsyncMock(return_value=ScrapedPage(
        url="https://example.com/about",
        html="<html>Founded in 2018</html>",
        markdown="Founded in 2018",
    ))

    fake_wayback = MagicMock()
    fake_wayback.snapshots = AsyncMock(return_value=[])

    fake_extractor = MagicMock()
    fake_extractor.extract_exec_change = AsyncMock(return_value=ExtractedExecChange(
        name="Jane Doe", role_canonical="cro", role_raw="CRO",
        action=ExecAction.HIRE, is_relevant=True,
    ))
    from rrxray.services.extraction import ExtractedLinkedInIncumbent
    fake_extractor.extract_linkedin_role = AsyncMock(return_value=ExtractedLinkedInIncumbent(
        name="Jane Doe", role_canonical="cro", role_raw="CRO", is_relevant=True,
    ))

    config = Config(domain="example.com")
    ctx = CollectorContext(
        domain="example.com",
        company_name="Acme",
        firecrawl=fake_firecrawl,
        wayback=fake_wayback,
        evidence_dir=tmp_path,
        config=config,
        extractor=fake_extractor,
    )

    asyncio.run(collect(ctx))

    evidence_dir = tmp_path / "leadership_stability"
    assert evidence_dir.exists()
    assert (evidence_dir / "press_search.json").exists()
    assert (evidence_dir / "linkedin_search.json").exists()
    assert (evidence_dir / "exec_changes.json").exists()
    assert (evidence_dir / "current_incumbents.json").exists()


def test_collect_returns_full_happy_path(tmp_path):
    """All paths populated → fully populated LeadershipStabilityData."""
    from rrxray.collectors.leadership_stability import collect
    from rrxray.config import Config
    from rrxray.context import CollectorContext
    from rrxray.services.extraction import (
        ExecAction,
        ExtractedExecChange,
        ExtractedLinkedInIncumbent,
    )
    from rrxray.services.firecrawl_client import ScrapedPage, SearchResult

    fake_firecrawl = MagicMock()
    fake_firecrawl.search = AsyncMock(side_effect=[
        [SearchResult(url="https://example.com/p/1", title="Acme Names Jane Doe as CRO", description="...")],
        [],
        [],
        [SearchResult(url="https://www.linkedin.com/in/jane-doe", title="Jane CRO", description="...")],
        [], [], [], [], [], [],
    ])
    fake_firecrawl.scrape_url = AsyncMock(return_value=ScrapedPage(
        url="https://example.com/about", html="<p>Founded in 2018</p>", markdown="Founded in 2018",
    ))
    fake_wayback = MagicMock()
    fake_wayback.snapshots = AsyncMock(return_value=[])

    fake_extractor = MagicMock()
    fake_extractor.extract_exec_change = AsyncMock(return_value=ExtractedExecChange(
        name="Jane Doe", role_canonical="cro", role_raw="CRO",
        action=ExecAction.HIRE, is_relevant=True,
    ))
    fake_extractor.extract_linkedin_role = AsyncMock(return_value=ExtractedLinkedInIncumbent(
        name="Jane Doe", role_canonical="cro", role_raw="CRO", is_relevant=True,
    ))

    ctx = CollectorContext(
        domain="example.com", company_name="Acme",
        firecrawl=fake_firecrawl, wayback=fake_wayback,
        evidence_dir=tmp_path, config=Config(domain="example.com"),
        extractor=fake_extractor,
    )
    data = asyncio.run(collect(ctx))

    assert len(data.exec_changes) == 1
    assert data.exec_changes[0].name == "Jane Doe"
    assert len(data.current_incumbents) == 1
    assert data.founder_tenure.inferred_year == 2018
    assert len(data.name_registrations) == 1
    assert data.name_registrations[0].whitelist is True  # press takes precedence


def test_collect_handles_total_failure(tmp_path):
    """All Firecrawl calls fail; collector returns LeadershipStabilityData with signal-loss finding."""
    from rrxray.collectors.leadership_stability import collect
    from rrxray.config import Config
    from rrxray.context import CollectorContext
    from rrxray.services.firecrawl_client import FirecrawlError

    fake_firecrawl = MagicMock()
    fake_firecrawl.search = AsyncMock(side_effect=FirecrawlError("simulated"))
    fake_firecrawl.scrape_url = AsyncMock(side_effect=FirecrawlError("simulated"))

    fake_wayback = MagicMock()
    fake_wayback.snapshots = AsyncMock(return_value=[])

    fake_extractor = MagicMock()
    # Should never be called since search returned no results, but provide stubs
    fake_extractor.extract_exec_change = AsyncMock(return_value=None)
    fake_extractor.extract_linkedin_role = AsyncMock(return_value=None)

    ctx = CollectorContext(
        domain="example.com", company_name="Acme",
        firecrawl=fake_firecrawl, wayback=fake_wayback,
        evidence_dir=tmp_path, config=Config(domain="example.com"),
        extractor=fake_extractor,
    )
    data = asyncio.run(collect(ctx))

    # Graceful: no exception, finding emitted
    assert data.exec_changes == []
    assert data.current_incumbents == []
    assert data.founder_tenure.source == "unknown"
    finding_texts = [f.text for f in data.findings]
    assert any("not recovered" in t.lower() for t in finding_texts)


def test_collect_handles_press_search_failure_only(tmp_path):
    """Press search fails entirely; LinkedIn + founder still work."""
    from rrxray.collectors.leadership_stability import collect
    from rrxray.config import Config
    from rrxray.context import CollectorContext
    from rrxray.services.extraction import ExtractedLinkedInIncumbent
    from rrxray.services.firecrawl_client import FirecrawlError, ScrapedPage, SearchResult

    fake_firecrawl = MagicMock()
    # First 3 calls (press hires/departures/promotions) all fail
    # Next 7 (LinkedIn) return one CRO result
    fake_firecrawl.search = AsyncMock(side_effect=[
        FirecrawlError("simulated press failure"),
        FirecrawlError("simulated press failure"),
        FirecrawlError("simulated press failure"),
        [SearchResult(url="https://www.linkedin.com/in/jane", title="Jane CRO", description="...")],
        [], [], [], [], [], [],
    ])
    fake_firecrawl.scrape_url = AsyncMock(return_value=ScrapedPage(
        url="https://example.com/about", html="<p>Founded in 2018</p>", markdown="Founded in 2018",
    ))
    fake_wayback = MagicMock()
    fake_wayback.snapshots = AsyncMock(return_value=[])

    fake_extractor = MagicMock()
    fake_extractor.extract_exec_change = AsyncMock(return_value=None)
    fake_extractor.extract_linkedin_role = AsyncMock(return_value=ExtractedLinkedInIncumbent(
        name="Jane", role_canonical="cro", role_raw="CRO", is_relevant=True,
    ))

    ctx = CollectorContext(
        domain="example.com", company_name="Acme",
        firecrawl=fake_firecrawl, wayback=fake_wayback,
        evidence_dir=tmp_path, config=Config(domain="example.com"),
        extractor=fake_extractor,
    )
    data = asyncio.run(collect(ctx))

    # Press path silent; LinkedIn + founder populated
    assert data.exec_changes == []
    assert len(data.current_incumbents) == 1
    assert data.founder_tenure.inferred_year == 2018


def test_collect_excludes_names_from_synthesizer_visible_data(tmp_path):
    """Defense-in-depth: confirm collector output keeps names confined to expected fields."""
    from rrxray.collectors.leadership_stability import collect
    from rrxray.config import Config
    from rrxray.context import CollectorContext
    from rrxray.services.extraction import (
        ExecAction,
        ExtractedExecChange,
        ExtractedLinkedInIncumbent,
    )
    from rrxray.services.firecrawl_client import ScrapedPage, SearchResult

    fake_firecrawl = MagicMock()
    fake_firecrawl.search = AsyncMock(side_effect=[
        [SearchResult(url="u1", title="Acme Names Jane Doe as CRO", description="...")],
        [],
        [],
        [SearchResult(url="https://www.linkedin.com/in/jane", title="Jane CRO", description="...")],
        [], [], [], [], [], [],
    ])
    fake_firecrawl.scrape_url = AsyncMock(return_value=ScrapedPage(
        url="https://example.com/about", html="<p>Founded in 2018</p>", markdown="...",
    ))
    fake_wayback = MagicMock()
    fake_wayback.snapshots = AsyncMock(return_value=[])

    fake_extractor = MagicMock()
    fake_extractor.extract_exec_change = AsyncMock(return_value=ExtractedExecChange(
        name="Jane Doe", role_canonical="cro", role_raw="CRO",
        action=ExecAction.HIRE, is_relevant=True,
    ))
    fake_extractor.extract_linkedin_role = AsyncMock(return_value=ExtractedLinkedInIncumbent(
        name="Jane Doe", role_canonical="cro", role_raw="CRO", is_relevant=True,
    ))

    ctx = CollectorContext(
        domain="example.com", company_name="Acme",
        firecrawl=fake_firecrawl, wayback=fake_wayback,
        evidence_dir=tmp_path, config=Config(domain="example.com"),
        extractor=fake_extractor,
    )
    data = asyncio.run(collect(ctx))

    # Names appear in expected fields only
    assert data.exec_changes[0].name == "Jane Doe"
    assert data.current_incumbents[0].name == "Jane Doe"
    assert data.name_registrations[0].name == "Jane Doe"

    # Names should NOT leak into findings text (those are collector-emitted strings)
    for finding in data.findings:
        assert "Jane Doe" not in finding.text, f"Name leaked into finding: {finding.text!r}"
    for q in data.discovery_questions:
        assert "Jane Doe" not in q
