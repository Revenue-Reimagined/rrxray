"""revenue_motion collector tests."""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from rrxray.collectors import revenue_motion
from rrxray.context import CollectorContext
from rrxray.schemas.revenue_motion import JobPosting

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "synthetic" / "revenue_motion"


def _load(name: str) -> str:
    return (FIXTURE_DIR / name).read_text()


def _make_ctx(
    tmp_path: Path,
    scrape_responses: dict[str, dict] | None = None,
    search_responses: dict[str, list[dict]] | None = None,
) -> CollectorContext:
    """Build a CollectorContext with mocked Firecrawl scrape + search."""
    fc = MagicMock()

    async def fake_scrape(url, only_main_content=True):
        scraped = scrape_responses.get(url) if scrape_responses else None
        if scraped is None:
            from rrxray.services.firecrawl_client import FirecrawlError
            raise FirecrawlError(f"no fixture for {url}")
        return MagicMock(
            url=url,
            markdown=scraped.get("markdown", ""),
            html=scraped.get("html", ""),
            metadata=scraped.get("metadata", {}),
        )

    async def fake_search(query, limit=10):
        if search_responses is None:
            return []
        from rrxray.services.firecrawl_client import SearchResult
        for key, items in search_responses.items():
            if key in query:
                return [SearchResult(**item) for item in items[:limit]]
        return []

    fc.scrape_url = AsyncMock(side_effect=fake_scrape)
    fc.search = AsyncMock(side_effect=fake_search)

    wb = MagicMock()
    wb.snapshots = AsyncMock(return_value=[])
    config = MagicMock(domain="acme.com")
    return CollectorContext(
        domain="acme.com",
        company_name=None,
        firecrawl=fc,
        wayback=wb,
        evidence_dir=tmp_path / "evidence",
        config=config,
    )


def test_collector_name_constant():
    assert revenue_motion.NAME == "revenue_motion"


def test_discover_careers_url_at_slash_careers(tmp_path):
    ctx = _make_ctx(tmp_path, scrape_responses={
        "https://acme.com/careers": {
            "html": _load("careers_simple.html"),
            "markdown": "# Careers",
            "metadata": {"sourceURL": "https://acme.com/careers"},
        },
    })
    url, page = asyncio.run(revenue_motion._discover_careers_url(ctx))
    assert url == "https://acme.com/careers"
    assert page is not None


def test_discover_careers_url_falls_back_to_slash_jobs(tmp_path):
    ctx = _make_ctx(tmp_path, scrape_responses={
        "https://acme.com/jobs": {
            "html": _load("careers_simple.html"),
            "markdown": "# Jobs",
            "metadata": {"sourceURL": "https://acme.com/jobs"},
        },
    })
    url, _ = asyncio.run(revenue_motion._discover_careers_url(ctx))
    assert url == "https://acme.com/jobs"


def test_discover_careers_url_returns_none_when_nothing_found(tmp_path):
    ctx = _make_ctx(tmp_path, scrape_responses={})
    url, page = asyncio.run(revenue_motion._discover_careers_url(ctx))
    assert url is None
    assert page is None


def test_detect_ats_lever():
    html = _load("careers_with_ats_link.html")
    name, url = revenue_motion._detect_ats(html)
    assert name == "lever"
    assert "jobs.lever.co/acme" in url


def test_detect_ats_greenhouse():
    html = '<a href="https://boards.greenhouse.io/linear">Apply</a>'
    name, _url = revenue_motion._detect_ats(html)
    assert name == "greenhouse"


def test_detect_ats_ashby():
    html = '<iframe src="https://example.ashbyhq.com/embed"></iframe>'
    name, _url = revenue_motion._detect_ats(html)
    assert name == "ashby"


def test_detect_ats_workable():
    html = '<a href="https://apply.workable.com/exampleco">View jobs</a>'
    name, _url = revenue_motion._detect_ats(html)
    assert name == "workable"


def test_detect_ats_returns_none_when_no_ats_link():
    html = _load("careers_simple.html")
    name, url = revenue_motion._detect_ats(html)
    assert name is None
    assert url is None


def test_categorize_title_ae():
    cat, kw = revenue_motion._categorize_title("Senior Account Executive")
    assert cat == "ae"
    assert "account executive" in kw.lower()


def test_categorize_title_sdr():
    cat, _ = revenue_motion._categorize_title("Sales Development Representative")
    assert cat == "sdr"


def test_categorize_title_bdr():
    cat, _ = revenue_motion._categorize_title("BDR — Outbound")
    assert cat == "sdr"


def test_categorize_title_sales_leadership():
    for title in ["VP of Sales", "Chief Revenue Officer", "Head of Revenue"]:
        cat, _ = revenue_motion._categorize_title(title)
        assert cat == "sales_leadership", f"{title} should be sales_leadership; got {cat}"


def test_categorize_title_csm():
    cat, _ = revenue_motion._categorize_title("Senior Customer Success Manager")
    assert cat == "csm"


def test_categorize_title_unknown_returns_other():
    cat, kw = revenue_motion._categorize_title("Senior Software Engineer")
    assert cat == "other"
    assert kw is None


def test_categorize_title_case_insensitive():
    cat, _ = revenue_motion._categorize_title("ACCOUNT EXECUTIVE")
    assert cat == "ae"


def test_extract_roles_from_simple_careers_page():
    html = _load("careers_simple.html")
    roles = revenue_motion._extract_roles(html, source="company_careers", base_url="https://acme.com")
    titles = [r.title for r in roles]
    assert "Senior Account Executive" in titles
    assert "Sales Development Representative" in titles
    assert "Chief Technology Officer" in titles


def test_extract_roles_categorizes_correctly():
    html = _load("careers_simple.html")
    roles = revenue_motion._extract_roles(html, source="company_careers", base_url="https://acme.com")
    cat_map = {r.title: r.category for r in roles}
    assert cat_map["Senior Account Executive"] == "ae"
    assert cat_map["Sales Development Representative"] == "sdr"
    assert cat_map["Chief Technology Officer"] == "other"


def test_extract_roles_resolves_relative_urls():
    html = _load("careers_simple.html")
    roles = revenue_motion._extract_roles(html, source="company_careers", base_url="https://acme.com")
    ae_role = next(r for r in roles if r.category == "ae")
    assert ae_role.url is not None
    assert ae_role.url.startswith("https://acme.com")


def test_extract_roles_returns_empty_for_html_with_no_links():
    roles = revenue_motion._extract_roles(
        "<html><body><p>No jobs</p></body></html>",
        source="company_careers",
        base_url="https://acme.com",
    )
    assert roles == []


def test_linkedin_search_jobs_parses_results(tmp_path):
    ctx = _make_ctx(tmp_path, search_responses={
        "site:linkedin.com/jobs": [
            {"url": "https://www.linkedin.com/jobs/view/123",
             "title": "Account Executive at Acme Corp",
             "description": "Sell to enterprise..."},
            {"url": "https://www.linkedin.com/jobs/view/456",
             "title": "SDR at Acme Corp",
             "description": "Outbound prospecting..."},
            {"url": "https://www.linkedin.com/jobs/view/789",
             "title": "Senior Engineer at Acme Corp",
             "description": "Build the platform..."},
        ],
    })
    roles = asyncio.run(revenue_motion._linkedin_search_jobs(ctx.firecrawl, "acme.com"))
    assert len(roles) == 3
    titles = [r.title for r in roles]
    assert "Account Executive at Acme Corp" in titles
    cat_map = {r.title: r.category for r in roles}
    assert cat_map["Account Executive at Acme Corp"] == "ae"
    assert all(r.source == "linkedin" for r in roles)


def test_linkedin_search_jobs_empty_when_no_results(tmp_path):
    ctx = _make_ctx(tmp_path, search_responses={})
    roles = asyncio.run(revenue_motion._linkedin_search_jobs(ctx.firecrawl, "acme.com"))
    assert roles == []


def test_linkedin_search_jobs_swallows_firecrawl_error(tmp_path):
    """Search failure must NOT raise — collector continues with careers data."""
    ctx = _make_ctx(tmp_path)

    async def fail(query, limit=10):
        from rrxray.services.firecrawl_client import FirecrawlError
        raise FirecrawlError("simulated failure")

    ctx.firecrawl.search = AsyncMock(side_effect=fail)
    roles = asyncio.run(revenue_motion._linkedin_search_jobs(ctx.firecrawl, "acme.com"))
    assert roles == []


def test_linkedin_employee_count_parses_snippet(tmp_path):
    ctx = _make_ctx(tmp_path, search_responses={
        "site:linkedin.com/company": [
            {"url": "https://www.linkedin.com/company/acme",
             "title": "Acme Corp | LinkedIn",
             "description": "Acme Corp · Software · 247 employees on LinkedIn ..."},
        ],
    })
    count = asyncio.run(revenue_motion._linkedin_employee_count(ctx.firecrawl, "acme.com"))
    assert count == 247


def test_linkedin_employee_count_returns_none_when_snippet_unparseable(tmp_path):
    ctx = _make_ctx(tmp_path, search_responses={
        "site:linkedin.com/company": [
            {"url": "https://www.linkedin.com/company/acme",
             "title": "Acme | LinkedIn",
             "description": "no number in this description"},
        ],
    })
    count = asyncio.run(revenue_motion._linkedin_employee_count(ctx.firecrawl, "acme.com"))
    assert count is None


def test_linkedin_employee_count_handles_search_failure(tmp_path):
    ctx = _make_ctx(tmp_path)

    async def fail(query, limit=10):
        from rrxray.services.firecrawl_client import FirecrawlError
        raise FirecrawlError("boom")

    ctx.firecrawl.search = AsyncMock(side_effect=fail)
    count = asyncio.run(revenue_motion._linkedin_employee_count(ctx.firecrawl, "acme.com"))
    assert count is None


def test_compute_role_metrics_basic():
    roles = [
        JobPosting(title="AE 1", category="ae", source="company_careers"),
        JobPosting(title="AE 2", category="ae", source="company_careers"),
        JobPosting(title="SDR 1", category="sdr", source="company_careers"),
    ]
    counts, ratio = revenue_motion._compute_role_metrics(roles)
    assert counts["ae"] == 2
    assert counts["sdr"] == 1
    assert ratio == 2.0


def test_compute_role_metrics_zero_sdr_returns_none_ratio():
    roles = [
        JobPosting(title="AE 1", category="ae", source="company_careers"),
        JobPosting(title="AE 2", category="ae", source="company_careers"),
    ]
    counts, ratio = revenue_motion._compute_role_metrics(roles)
    assert counts["ae"] == 2
    assert ratio is None


def test_compute_role_metrics_zero_ae_returns_none_ratio():
    roles = [
        JobPosting(title="SDR 1", category="sdr", source="company_careers"),
    ]
    _counts, ratio = revenue_motion._compute_role_metrics(roles)
    assert ratio is None


def test_emit_findings_high_ae_to_sdr_ratio():
    roles = [
        JobPosting(title=f"AE {i}", category="ae", source="company_careers")
        for i in range(8)
    ] + [JobPosting(title="SDR 1", category="sdr", source="company_careers")]
    counts = {"ae": 8, "sdr": 1}
    findings, gaps, _questions = revenue_motion._emit_findings(
        domain="acme.com", careers_url="https://acme.com/careers",
        roles=roles, counts=counts, ratio=8.0,
        employee_count=None, ats_platform=None,
    )
    finding_text = " ".join(f.text.lower() for f in findings) + " " + " ".join(gaps).lower()
    assert "ae" in finding_text or "sdr" in finding_text


def test_emit_findings_ae_without_sdr():
    roles = [
        JobPosting(title="AE 1", category="ae", source="company_careers"),
    ]
    counts = {"ae": 1, "sdr": 0}
    _findings, gaps, _questions = revenue_motion._emit_findings(
        domain="acme.com", careers_url="https://acme.com/careers",
        roles=roles, counts=counts, ratio=None,
        employee_count=None, ats_platform=None,
    )
    gap_text = " ".join(gaps).lower()
    assert "ae" in gap_text or "sdr" in gap_text or "founder" in gap_text


def test_emit_findings_sales_leadership_posted():
    roles = [
        JobPosting(title="VP of Sales", category="sales_leadership", source="company_careers"),
    ]
    counts = {"sales_leadership": 1}
    findings, _gaps, _q = revenue_motion._emit_findings(
        domain="acme.com", careers_url="https://acme.com/careers",
        roles=roles, counts=counts, ratio=None,
        employee_count=None, ats_platform=None,
    )
    finding_text = " ".join(f.text.lower() for f in findings)
    assert "leadership" in finding_text or "transition" in finding_text or "vp" in finding_text


def test_emit_findings_no_roles_emits_finding():
    findings, _gaps, _q = revenue_motion._emit_findings(
        domain="acme.com", careers_url=None,
        roles=[], counts={}, ratio=None,
        employee_count=None, ats_platform=None,
    )
    finding_text = " ".join(f.text.lower() for f in findings)
    assert "no" in finding_text and ("careers" in finding_text or "roles" in finding_text or "open" in finding_text)


def test_collect_writes_evidence(tmp_path):
    ctx = _make_ctx(tmp_path, scrape_responses={
        "https://acme.com/careers": {
            "html": _load("careers_simple.html"),
            "markdown": "",
            "metadata": {"sourceURL": "https://acme.com/careers"},
        },
    })
    asyncio.run(revenue_motion.collect(ctx))
    evidence = tmp_path / "evidence" / "revenue_motion"
    assert (evidence / "careers.html").exists()


def test_collect_returns_revenue_motion_data(tmp_path):
    from rrxray.schemas.revenue_motion import RevenueMotionData

    ctx = _make_ctx(tmp_path, scrape_responses={
        "https://acme.com/careers": {
            "html": _load("careers_simple.html"),
            "markdown": "",
            "metadata": {"sourceURL": "https://acme.com/careers"},
        },
    }, search_responses={
        "site:linkedin.com/jobs": [
            {"url": "https://www.linkedin.com/jobs/view/123",
             "title": "Account Executive at Acme",
             "description": ""},
        ],
        "site:linkedin.com/company": [
            {"url": "https://www.linkedin.com/company/acme",
             "title": "Acme | LinkedIn",
             "description": "Acme · Software · 200 employees on LinkedIn"},
        ],
    })
    result = asyncio.run(revenue_motion.collect(ctx))
    assert isinstance(result, RevenueMotionData)
    assert result.careers_page_url == "https://acme.com/careers"
    assert len(result.open_roles) >= 3
    assert result.linkedin_employee_count == 200
    assert result.linkedin_job_count == 1


def test_collect_handles_no_careers_page(tmp_path):
    ctx = _make_ctx(tmp_path, scrape_responses={})
    result = asyncio.run(revenue_motion.collect(ctx))
    assert result.careers_page_url is None
    assert result.open_roles == []
    assert len(result.findings) >= 1


def test_collect_follows_ats_link(tmp_path):
    ctx = _make_ctx(tmp_path, scrape_responses={
        "https://acme.com/careers": {
            "html": _load("careers_with_ats_link.html"),
            "markdown": "",
            "metadata": {"sourceURL": "https://acme.com/careers"},
        },
        "https://jobs.lever.co/acme": {
            "html": _load("careers_simple.html"),
            "markdown": "",
            "metadata": {"sourceURL": "https://jobs.lever.co/acme"},
        },
    })
    result = asyncio.run(revenue_motion.collect(ctx))
    assert result.ats_platform == "lever"
    assert any(r.source == "ats" for r in result.open_roles)


def test_source_citation_path_relative_to_evidence_dir(tmp_path):
    """SourceCitation.evidence_path must NOT start with 'evidence/' to avoid template double-prefix."""
    ctx = _make_ctx(tmp_path, scrape_responses={
        "https://acme.com/careers": {
            "html": _load("careers_simple.html"),
            "markdown": "",
            "metadata": {"sourceURL": "https://acme.com/careers"},
        },
    })
    result = asyncio.run(revenue_motion.collect(ctx))
    for source in result.sources:
        if source.evidence_path:
            assert not source.evidence_path.startswith("evidence/")
            assert source.evidence_path.startswith("revenue_motion/")
