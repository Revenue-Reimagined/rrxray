"""revenue_motion collector tests."""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from rrxray.collectors import revenue_motion
from rrxray.context import CollectorContext

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
