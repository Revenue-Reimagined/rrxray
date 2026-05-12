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


def _make_failing_firecrawl():
    """Build a fake firecrawl whose scrape_url always raises FirecrawlError.

    Existing tests expect snippet-only extraction (no body forwarded). The
    iteration #3 collector now tries to scrape each press URL; simulating a
    fetch failure preserves the prior behavior while still routing through
    the new code path.
    """
    from rrxray.services.firecrawl_client import FirecrawlError
    f = MagicMock()
    f.scrape_url = AsyncMock(side_effect=FirecrawlError("simulated"))
    return f


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

    changes = asyncio.run(_extract_exec_changes(
        results, extractor, "Acme", "example.com", _make_failing_firecrawl(),
    ))

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

    changes = asyncio.run(_extract_exec_changes(
        results, extractor, "Acme", "example.com", _make_failing_firecrawl(),
    ))
    assert changes == []


def test_extract_exec_changes_passes_domain_to_extractor():
    """Iteration #2: extractor receives target_domain so it can disambiguate
    common-name companies (e.g., Linear vs Linear Retail).
    """
    from rrxray.collectors.leadership_stability import _extract_exec_changes
    from rrxray.services.firecrawl_client import SearchResult

    results = [SearchResult(url="u1", title="x", description="y")]
    extractor = MagicMock()
    extractor.extract_exec_change = AsyncMock(return_value=None)

    asyncio.run(_extract_exec_changes(
        results, extractor, "Linear", "linear.app", _make_failing_firecrawl(),
    ))

    # Confirm extractor.extract_exec_change was called with target_domain
    call = extractor.extract_exec_change.call_args
    # Accept either positional or keyword
    assert "linear.app" in str(call)


def test_extract_exec_changes_fetches_press_body_and_forwards_to_extractor():
    """Iteration #3: press URL is scraped and full body is passed to extractor."""
    from rrxray.collectors.leadership_stability import _extract_exec_changes
    from rrxray.services.extraction import ExecAction, ExtractedExecChange
    from rrxray.services.firecrawl_client import ScrapedPage, SearchResult

    fake_firecrawl = MagicMock()
    fake_firecrawl.scrape_url = AsyncMock(return_value=ScrapedPage(
        url="https://example.com/p",
        html="...",
        markdown="Acme appoints Jane Doe as CRO effective March 1, 2026.",
    ))

    extractor = MagicMock()
    extractor.extract_exec_change = AsyncMock(return_value=ExtractedExecChange(
        name="Jane Doe", role_canonical="cro", role_raw="CRO",
        action=ExecAction.HIRE, is_relevant=True, occurred_at="2026-03-01",
    ))

    results = [SearchResult(url="https://example.com/p", title="t", description="s")]
    changes = asyncio.run(_extract_exec_changes(
        results, extractor, "Acme", "acme.com", fake_firecrawl,
    ))

    # Body was fetched and forwarded
    assert fake_firecrawl.scrape_url.called
    call = extractor.extract_exec_change.call_args
    assert "March 1, 2026" in str(call) or "appoints" in str(call)

    # occurred_at parsed to date object
    from datetime import date
    assert len(changes) == 1
    assert changes[0].occurred_at == date(2026, 3, 1)


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


def _make_fake_enrichment_orch(incumbents=None, *, spend=0.0, aborted_reason="completed",
                               press_passthrough=True, press_enriched=None):
    """Helper: build a MagicMock LeadershipEnrichment orchestrator with the
    incumbent return value, optional press-enrichment mutation, and a metadata
    property that reflects the final spend/aborted state.
    """
    from rrxray.schemas.leadership_stability import LeadershipEnrichmentMetadata
    from rrxray.services.leadership_enrichment import EnrichedLeadership

    orch = MagicMock()
    orch.find_and_enrich_incumbents = AsyncMock(return_value=EnrichedLeadership(
        incumbents=incumbents or [],
        spend_dollars=spend,
        aborted_reason=aborted_reason,
    ))
    if press_enriched is not None:
        orch.enrich_press_change_names = AsyncMock(return_value=press_enriched)
    elif press_passthrough:
        orch.enrich_press_change_names = AsyncMock(
            side_effect=lambda exec_changes, company_domain: exec_changes
        )
    orch.metadata = LeadershipEnrichmentMetadata(
        spend_dollars=spend, aborted_reason=aborted_reason,
    )
    return orch


def test_collect_writes_evidence(tmp_path):
    """All four evidence files written under evidence/leadership_stability/."""
    from rrxray.collectors.leadership_stability import collect
    from rrxray.config import Config
    from rrxray.context import CollectorContext
    from rrxray.schemas.leadership_stability import CurrentIncumbent
    from rrxray.services.extraction import ExecAction, ExtractedExecChange
    from rrxray.services.firecrawl_client import ScrapedPage, SearchResult

    fake_firecrawl = MagicMock()
    fake_firecrawl.search = AsyncMock(side_effect=[
        # press hires/departures/promotions
        [SearchResult(url="u1", title="Acme Names Jane Doe as CRO", description="...")],
        [],
        [],
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

    fake_orch = _make_fake_enrichment_orch(incumbents=[
        CurrentIncumbent(
            name="Jane Doe", role_canonical="cro", role_raw="CRO",
            linkedin_url="https://www.linkedin.com/in/jane-doe",
        ),
    ])

    config = Config(domain="example.com")
    ctx = CollectorContext(
        domain="example.com",
        company_name="Acme",
        firecrawl=fake_firecrawl,
        wayback=fake_wayback,
        evidence_dir=tmp_path,
        config=config,
        extractor=fake_extractor,
        leadership_enrichment=fake_orch,
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
    from rrxray.schemas.leadership_stability import CurrentIncumbent
    from rrxray.services.extraction import ExecAction, ExtractedExecChange
    from rrxray.services.firecrawl_client import ScrapedPage, SearchResult

    fake_firecrawl = MagicMock()
    fake_firecrawl.search = AsyncMock(side_effect=[
        [SearchResult(url="https://example.com/p/1", title="Acme Names Jane Doe as CRO", description="...")],
        [],
        [],
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

    fake_orch = _make_fake_enrichment_orch(incumbents=[
        CurrentIncumbent(
            name="Jane Doe", role_canonical="cro", role_raw="CRO",
            linkedin_url="https://www.linkedin.com/in/jane-doe",
        ),
    ])

    ctx = CollectorContext(
        domain="example.com", company_name="Acme",
        firecrawl=fake_firecrawl, wayback=fake_wayback,
        evidence_dir=tmp_path, config=Config(domain="example.com"),
        extractor=fake_extractor,
        leadership_enrichment=fake_orch,
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

    # No enrichment orchestrator wired → incumbents remain empty.
    ctx = CollectorContext(
        domain="example.com", company_name="Acme",
        firecrawl=fake_firecrawl, wayback=fake_wayback,
        evidence_dir=tmp_path, config=Config(domain="example.com"),
        extractor=fake_extractor,
        leadership_enrichment=None,
    )
    data = asyncio.run(collect(ctx))

    # Graceful: no exception, finding emitted
    assert data.exec_changes == []
    assert data.current_incumbents == []
    assert data.founder_tenure.source == "unknown"
    finding_texts = [f.text for f in data.findings]
    assert any("not recovered" in t.lower() for t in finding_texts)


def test_collect_handles_press_search_failure_only(tmp_path):
    """Press search fails entirely; PDL incumbent + founder still work."""
    from rrxray.collectors.leadership_stability import collect
    from rrxray.config import Config
    from rrxray.context import CollectorContext
    from rrxray.schemas.leadership_stability import CurrentIncumbent
    from rrxray.services.firecrawl_client import FirecrawlError, ScrapedPage

    fake_firecrawl = MagicMock()
    # All 3 press searches fail. No LinkedIn search anymore (PDL replaces it).
    fake_firecrawl.search = AsyncMock(side_effect=[
        FirecrawlError("simulated press failure"),
        FirecrawlError("simulated press failure"),
        FirecrawlError("simulated press failure"),
    ])
    fake_firecrawl.scrape_url = AsyncMock(return_value=ScrapedPage(
        url="https://example.com/about", html="<p>Founded in 2018</p>", markdown="Founded in 2018",
    ))
    fake_wayback = MagicMock()
    fake_wayback.snapshots = AsyncMock(return_value=[])

    fake_extractor = MagicMock()
    fake_extractor.extract_exec_change = AsyncMock(return_value=None)

    fake_orch = _make_fake_enrichment_orch(incumbents=[
        CurrentIncumbent(
            name="Jane", role_canonical="cro", role_raw="CRO",
            linkedin_url="https://www.linkedin.com/in/jane",
        ),
    ])

    ctx = CollectorContext(
        domain="example.com", company_name="Acme",
        firecrawl=fake_firecrawl, wayback=fake_wayback,
        evidence_dir=tmp_path, config=Config(domain="example.com"),
        extractor=fake_extractor,
        leadership_enrichment=fake_orch,
    )
    data = asyncio.run(collect(ctx))

    # Press path silent; PDL incumbent + founder populated
    assert data.exec_changes == []
    assert len(data.current_incumbents) == 1
    assert data.founder_tenure.inferred_year == 2018


def test_collect_excludes_names_from_synthesizer_visible_data(tmp_path):
    """Defense-in-depth: confirm collector output keeps names confined to expected fields."""
    from rrxray.collectors.leadership_stability import collect
    from rrxray.config import Config
    from rrxray.context import CollectorContext
    from rrxray.schemas.leadership_stability import CurrentIncumbent
    from rrxray.services.extraction import ExecAction, ExtractedExecChange
    from rrxray.services.firecrawl_client import ScrapedPage, SearchResult

    fake_firecrawl = MagicMock()
    fake_firecrawl.search = AsyncMock(side_effect=[
        [SearchResult(url="u1", title="Acme Names Jane Doe as CRO", description="...")],
        [],
        [],
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

    fake_orch = _make_fake_enrichment_orch(incumbents=[
        CurrentIncumbent(
            name="Jane Doe", role_canonical="cro", role_raw="CRO",
            linkedin_url="https://www.linkedin.com/in/jane",
        ),
    ])

    ctx = CollectorContext(
        domain="example.com", company_name="Acme",
        firecrawl=fake_firecrawl, wayback=fake_wayback,
        evidence_dir=tmp_path, config=Config(domain="example.com"),
        extractor=fake_extractor,
        leadership_enrichment=fake_orch,
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


# ----------------------------------------------------------------------------
# T6 (Phase 2.2-deep) — PDL leadership enrichment path
# ----------------------------------------------------------------------------


def test_collect_calls_leadership_enrichment_when_available(tmp_path):
    """When ctx.leadership_enrichment is set, collect() uses it to populate current_incumbents."""
    from unittest.mock import AsyncMock, MagicMock

    from rrxray.collectors.leadership_stability import collect
    from rrxray.config import Config
    from rrxray.context import CollectorContext
    from rrxray.schemas.leadership_stability import (
        CurrentIncumbent,
        LeadershipEnrichmentMetadata,
    )
    from rrxray.services.firecrawl_client import FirecrawlError
    from rrxray.services.leadership_enrichment import EnrichedLeadership

    # Fake firecrawl returns empty press searches + no /about page
    fake_firecrawl = MagicMock()
    fake_firecrawl.search = AsyncMock(return_value=[])
    fake_firecrawl.scrape_url = AsyncMock(side_effect=FirecrawlError("no /about"))
    fake_wayback = MagicMock()
    fake_wayback.snapshots = AsyncMock(return_value=[])

    fake_enrichment_meta = LeadershipEnrichmentMetadata(spend_dollars=0.40, aborted_reason="completed")
    fake_orch = MagicMock()
    fake_orch.find_and_enrich_incumbents = AsyncMock(return_value=EnrichedLeadership(
        incumbents=[
            CurrentIncumbent(
                name="Jane Doe", role_canonical="cro", role_raw="Chief Revenue Officer",
                linkedin_url="https://www.linkedin.com/in/jane-doe-cro",
                tenure_months=14, years_at_company=14,
                prior_employer="Salesforce", prior_role="VP of Enterprise Sales",
            ),
        ],
        spend_dollars=0.40, aborted_reason="completed",
    ))
    fake_orch.enrich_press_change_names = AsyncMock(side_effect=lambda exec_changes, company_domain: exec_changes)
    fake_orch.metadata = fake_enrichment_meta

    ctx = CollectorContext(
        domain="acme.com", company_name="Acme",
        firecrawl=fake_firecrawl, wayback=fake_wayback,
        evidence_dir=tmp_path, config=Config(domain="acme.com"),
        extractor=None,
        leadership_enrichment=fake_orch,
    )
    data = asyncio.run(collect(ctx))

    assert len(data.current_incumbents) == 1
    assert data.current_incumbents[0].tenure_months == 14
    assert data.current_incumbents[0].prior_employer == "Salesforce"
    assert data.enrichment_metadata.spend_dollars == 0.40
    fake_orch.find_and_enrich_incumbents.assert_awaited_once()


def test_collect_skips_enrichment_when_ctx_leadership_enrichment_is_none(tmp_path):
    """When ctx.leadership_enrichment is None, no incumbents are populated; metadata is 'disabled'."""
    from unittest.mock import AsyncMock, MagicMock

    from rrxray.collectors.leadership_stability import collect
    from rrxray.config import Config
    from rrxray.context import CollectorContext
    from rrxray.services.firecrawl_client import FirecrawlError

    fake_firecrawl = MagicMock()
    fake_firecrawl.search = AsyncMock(return_value=[])
    fake_firecrawl.scrape_url = AsyncMock(side_effect=FirecrawlError("no /about"))
    fake_wayback = MagicMock()
    fake_wayback.snapshots = AsyncMock(return_value=[])

    ctx = CollectorContext(
        domain="acme.com", company_name="Acme",
        firecrawl=fake_firecrawl, wayback=fake_wayback,
        evidence_dir=tmp_path, config=Config(domain="acme.com"),
        extractor=None,
        leadership_enrichment=None,
    )
    data = asyncio.run(collect(ctx))

    assert data.current_incumbents == []
    assert data.enrichment_metadata.aborted_reason == "disabled"


def test_collect_enriches_press_change_names_when_orchestrator_available(tmp_path):
    """Press change names get prior_employer / prior_role / years_at_company filled in."""
    from unittest.mock import AsyncMock, MagicMock

    from rrxray.collectors.leadership_stability import collect
    from rrxray.config import Config
    from rrxray.context import CollectorContext
    from rrxray.schemas.leadership_stability import (
        ExecAction,
        LeadershipEnrichmentMetadata,
    )
    from rrxray.services.extraction import ExtractedExecChange
    from rrxray.services.firecrawl_client import (
        FirecrawlError,
        SearchResult,
    )
    from rrxray.services.leadership_enrichment import EnrichedLeadership

    fake_firecrawl = MagicMock()
    # Press search returns one result that the extractor will turn into an ExecChange
    fake_firecrawl.search = AsyncMock(side_effect=[
        [SearchResult(url="https://example.com/p/1", title="Acme Names Jane Doe as CRO", description="...")],
        [], [],
    ])
    fake_firecrawl.scrape_url = AsyncMock(side_effect=FirecrawlError("no /about"))
    fake_wayback = MagicMock()
    fake_wayback.snapshots = AsyncMock(return_value=[])

    fake_extractor = MagicMock()
    fake_extractor.extract_exec_change = AsyncMock(return_value=ExtractedExecChange(
        name="Jane Doe", role_canonical="cro", role_raw="CRO",
        action=ExecAction.HIRE, is_relevant=True, occurred_at="2024-03-01",
    ))

    fake_orch = MagicMock()
    fake_orch.find_and_enrich_incumbents = AsyncMock(return_value=EnrichedLeadership(
        incumbents=[], spend_dollars=1.40, aborted_reason="completed",
    ))
    # enrich_press_change_names returns mutated copies with prior_employer set
    def _enrich(exec_changes, company_domain):
        return [c.model_copy(update={
            "prior_employer": "Salesforce",
            "prior_role": "VP of Enterprise Sales",
            "years_at_company": 1,
        }) for c in exec_changes]
    fake_orch.enrich_press_change_names = AsyncMock(side_effect=_enrich)
    fake_orch.metadata = LeadershipEnrichmentMetadata(spend_dollars=1.60, aborted_reason="completed")

    ctx = CollectorContext(
        domain="acme.com", company_name="Acme",
        firecrawl=fake_firecrawl, wayback=fake_wayback,
        evidence_dir=tmp_path, config=Config(domain="acme.com"),
        extractor=fake_extractor,
        leadership_enrichment=fake_orch,
    )
    data = asyncio.run(collect(ctx))

    assert len(data.exec_changes) == 1
    assert data.exec_changes[0].prior_employer == "Salesforce"
    assert data.exec_changes[0].prior_role == "VP of Enterprise Sales"
    fake_orch.enrich_press_change_names.assert_awaited_once()


def test_collect_returns_partial_data_when_cost_cap_hit(tmp_path):
    """Orchestrator returns aborted_reason='cost_cap'; collector still returns LeadershipStabilityData."""
    from unittest.mock import AsyncMock, MagicMock

    from rrxray.collectors.leadership_stability import collect
    from rrxray.config import Config
    from rrxray.context import CollectorContext
    from rrxray.schemas.leadership_stability import (
        CurrentIncumbent,
        LeadershipEnrichmentMetadata,
    )
    from rrxray.services.firecrawl_client import FirecrawlError
    from rrxray.services.leadership_enrichment import EnrichedLeadership

    fake_firecrawl = MagicMock()
    fake_firecrawl.search = AsyncMock(return_value=[])
    fake_firecrawl.scrape_url = AsyncMock(side_effect=FirecrawlError("no /about"))
    fake_wayback = MagicMock()
    fake_wayback.snapshots = AsyncMock(return_value=[])

    fake_orch = MagicMock()
    fake_orch.find_and_enrich_incumbents = AsyncMock(return_value=EnrichedLeadership(
        incumbents=[
            CurrentIncumbent(name="A", role_canonical="cro", role_raw="CRO"),
        ],
        spend_dollars=5.0, aborted_reason="cost_cap",
    ))
    fake_orch.enrich_press_change_names = AsyncMock(side_effect=lambda exec_changes, company_domain: exec_changes)
    fake_orch.metadata = LeadershipEnrichmentMetadata(spend_dollars=5.0, aborted_reason="cost_cap")

    ctx = CollectorContext(
        domain="acme.com", company_name="Acme",
        firecrawl=fake_firecrawl, wayback=fake_wayback,
        evidence_dir=tmp_path, config=Config(domain="acme.com"),
        extractor=None,
        leadership_enrichment=fake_orch,
    )
    data = asyncio.run(collect(ctx))

    # Partial data preserved; metadata explains why
    assert len(data.current_incumbents) == 1
    assert data.enrichment_metadata.aborted_reason == "cost_cap"
