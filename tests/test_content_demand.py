"""content_demand collector tests."""
# ruff: noqa: I001
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest  # noqa: F401

from rrxray.collectors import content_demand
from rrxray.context import CollectorContext


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "synthetic" / "content_demand"


def _load(name: str) -> str:
    return (FIXTURE_DIR / name).read_text()


def _make_ctx(
    tmp_path: Path,
    scrape_responses: dict[str, dict] | None = None,
) -> CollectorContext:
    """Build a CollectorContext with mocked Firecrawl scrape."""
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

    fc.scrape_url = AsyncMock(side_effect=fake_scrape)

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
    assert content_demand.NAME == "content_demand"


def test_discover_blog_url_at_slash_blog(tmp_path):
    ctx = _make_ctx(tmp_path, scrape_responses={
        "https://acme.com/blog": {
            "html": _load("blog_simple.html"),
            "markdown": "# Blog",
            "metadata": {"sourceURL": "https://acme.com/blog"},
        },
    })
    url, page = asyncio.run(content_demand._discover_blog_url(ctx))
    assert url == "https://acme.com/blog"
    assert page is not None


def test_discover_blog_url_falls_back_to_slash_insights(tmp_path):
    ctx = _make_ctx(tmp_path, scrape_responses={
        "https://acme.com/insights": {
            "html": _load("blog_simple.html"),
            "markdown": "",
            "metadata": {"sourceURL": "https://acme.com/insights"},
        },
    })
    url, _ = asyncio.run(content_demand._discover_blog_url(ctx))
    assert url == "https://acme.com/insights"


def test_discover_blog_url_falls_back_through_all_paths(tmp_path):
    """Ensure /resources, /news, /articles, /learn are all tried in order."""
    for path in ["/resources", "/news", "/articles", "/learn"]:
        ctx = _make_ctx(tmp_path, scrape_responses={
            f"https://acme.com{path}": {
                "html": _load("blog_simple.html"),
                "markdown": "",
                "metadata": {"sourceURL": f"https://acme.com{path}"},
            },
        })
        url, _ = asyncio.run(content_demand._discover_blog_url(ctx))
        assert url == f"https://acme.com{path}", f"expected /{path} fallback"


def test_discover_blog_url_returns_none_when_nothing_found(tmp_path):
    ctx = _make_ctx(tmp_path, scrape_responses={})
    url, page = asyncio.run(content_demand._discover_blog_url(ctx))
    assert url is None
    assert page is None


def test_parse_blog_posts_extracts_titles_and_urls():
    html = _load("blog_simple.html")
    posts = content_demand._parse_blog_posts(html, base_url="https://acme.com")
    titles = [p.title for p in posts]
    assert "The Future of Revenue Ops" in titles
    assert "10 ways to close more deals" in titles
    # URLs resolved against base_url
    first = next(p for p in posts if p.title == "The Future of Revenue Ops")
    assert first.url == "https://acme.com/blog/the-future-of-revenue"


def test_parse_blog_posts_extracts_dates_when_present():
    html = _load("blog_simple.html")
    posts = content_demand._parse_blog_posts(html, base_url="https://acme.com")
    dated = next(p for p in posts if p.title == "The Future of Revenue Ops")
    assert dated.published_date == "2026-04-15"


def test_parse_blog_posts_handles_missing_dates_gracefully():
    html = _load("blog_no_dates.html")
    posts = content_demand._parse_blog_posts(html, base_url="https://acme.com")
    assert len(posts) >= 3
    assert all(p.published_date is None for p in posts)


def test_parse_blog_posts_caps_at_fifteen():
    """Build a synthetic blog with 25 posts; only first 15 should be returned."""
    parts = ["<html><body>"]
    for i in range(25):
        parts.append(f'<article><a href="/blog/post-{i}">Post {i}</a></article>')
    parts.append("</body></html>")
    html = "".join(parts)
    posts = content_demand._parse_blog_posts(html, base_url="https://acme.com")
    assert len(posts) == 15


def test_parse_blog_posts_returns_empty_for_html_with_no_links():
    posts = content_demand._parse_blog_posts(
        "<html><body><p>No posts yet</p></body></html>",
        base_url="https://acme.com",
    )
    assert posts == []


def test_parse_blog_posts_preserves_document_order():
    html = _load("blog_simple.html")
    posts = content_demand._parse_blog_posts(html, base_url="https://acme.com")
    titles = [p.title for p in posts]
    # blog_simple.html lists "The Future of Revenue Ops" first
    assert titles[0] == "The Future of Revenue Ops"
