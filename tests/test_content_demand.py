"""content_demand collector tests."""
# ruff: noqa: I001
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest  # noqa: F401

from rrxray.collectors import content_demand
from rrxray.context import CollectorContext
from rrxray.schemas.content_demand import BlogPost, LeadMagnet


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


def test_categorize_post_seo_listicle_via_numeric_prefix():
    cat, kw = content_demand._categorize_post("10 ways to close more deals", "")  # noqa: RUF059
    assert cat == "seo_listicle"


def test_categorize_post_seo_listicle_via_top_10():
    cat, _ = content_demand._categorize_post("Top 10 sales tools for 2026", "")
    assert cat == "seo_listicle"


def test_categorize_post_case_study():
    cat, kw = content_demand._categorize_post("Customer Story: Acme + BetaCo", "")
    assert cat == "case_study"
    assert "customer story" in kw.lower()


def test_categorize_post_product_announcement():
    cat, _ = content_demand._categorize_post("Introducing Workflow 2.0", "")
    assert cat == "product_announcement"


def test_categorize_post_tutorial():
    cat, _ = content_demand._categorize_post("How to write better outbound emails", "")
    assert cat == "tutorial"


def test_categorize_post_founder_essay():
    cat, _ = content_demand._categorize_post("Why I built this product", "")
    assert cat == "founder_essay"


def test_categorize_post_thought_leadership():
    cat, _ = content_demand._categorize_post("The Future of Revenue Ops", "")
    assert cat == "thought_leadership"


def test_categorize_post_news_pr():
    cat, _ = content_demand._categorize_post("Acme raises $50M Series B", "")
    assert cat == "news_pr"


def test_categorize_post_default_other():
    cat, kw = content_demand._categorize_post("A short status update", "")
    assert cat == "other"
    assert kw is None


def test_categorize_post_case_insensitive():
    cat, _ = content_demand._categorize_post("THE FUTURE OF SALES", "")
    assert cat == "thought_leadership"


def test_categorize_post_specificity_order_seo_beats_thought_leadership():
    """A title with both 'top 10' and 'the future of' should match seo_listicle (more specific, first in catalog)."""
    cat, _ = content_demand._categorize_post("Top 10 takes on the future of sales", "")
    assert cat == "seo_listicle"


def test_detect_lead_magnets_finds_ebook_with_form_gate():
    html = _load("blog_with_lead_magnets.html")
    magnets = content_demand._detect_lead_magnets(html, source_page="blog_index")
    ebook = next((m for m in magnets if m.asset_type == "ebook"), None)
    assert ebook is not None
    assert ebook.has_form_gate is True
    assert ebook.source_page == "blog_index"


def test_detect_lead_magnets_finds_calculator_without_gate():
    html = _load("blog_with_lead_magnets.html")
    magnets = content_demand._detect_lead_magnets(html, source_page="blog_index")
    calc = next((m for m in magnets if m.asset_type == "calculator"), None)
    assert calc is not None
    assert calc.has_form_gate is False


def test_detect_lead_magnets_finds_report():
    html = _load("blog_with_lead_magnets.html")
    magnets = content_demand._detect_lead_magnets(html, source_page="blog_index")
    assert any(m.asset_type == "report" for m in magnets)


def test_detect_lead_magnets_returns_empty_when_no_ctas():
    html = "<html><body><p>nothing here</p></body></html>"
    magnets = content_demand._detect_lead_magnets(html, source_page="homepage")
    assert magnets == []


def test_detect_lead_magnets_caps_at_ten():
    """Build HTML with 15 ebook CTAs; result should cap at 10."""
    parts = ["<html><body>"]
    for i in range(15):
        parts.append(f'<section><a href="/r/{i}">Download the ebook number {i}</a></section>')
    parts.append("</body></html>")
    html = "".join(parts)
    magnets = content_demand._detect_lead_magnets(html, source_page="homepage")
    assert len(magnets) <= 10


def test_detect_lead_magnets_dedupes_by_url():
    html = (
        '<section><a href="/r/playbook">Download the ebook</a></section>'
        '<section><a href="/r/playbook">Free ebook</a></section>'
    )
    magnets = content_demand._detect_lead_magnets(html, source_page="homepage")
    assert len(magnets) == 1


def test_detect_podcast_apple():
    html = _load("homepage_with_podcast_apple.html")
    platform, name = content_demand._detect_podcast(html)
    assert platform == "apple_podcasts"
    # Name comes from the <link title=...> attribute when available
    assert name == "The Revenue Show" or name is None


def test_detect_podcast_spotify():
    html = _load("homepage_with_podcast_spotify.html")
    platform, _ = content_demand._detect_podcast(html)
    assert platform == "spotify"


def test_detect_podcast_rss_only():
    """RSS link present but no Apple/Spotify link."""
    html = (
        '<html><head>'
        '<link rel="alternate" type="application/rss+xml" title="Inside Sales" '
        'href="https://example.com/feed.xml">'
        '</head><body></body></html>'
    )
    platform, name = content_demand._detect_podcast(html)
    assert platform == "rss_only"
    assert name == "Inside Sales"


def test_detect_podcast_returns_none_when_absent():
    html = "<html><body><p>no podcast here</p></body></html>"
    platform, name = content_demand._detect_podcast(html)
    assert platform is None
    assert name is None


def test_detect_newsletter_substack():
    html = _load("homepage_with_substack_newsletter.html")
    platform, archive_url = content_demand._detect_newsletter(html)
    assert platform == "substack"
    assert archive_url and "substack.com" in archive_url


def test_detect_newsletter_embedded_form_with_subscribe_button():
    html = _load("homepage_with_embedded_newsletter_form.html")
    platform, archive_url = content_demand._detect_newsletter(html)
    assert platform == "embedded_form"
    assert archive_url is None


def test_detect_newsletter_form_without_newsletter_keyword_returns_none():
    """Generic contact form should NOT register as a newsletter."""
    html = (
        '<form><input type="email"><button>Contact us</button></form>'
    )
    platform, _ = content_demand._detect_newsletter(html)
    assert platform is None


def test_detect_newsletter_returns_none_when_absent():
    html = "<html><body><p>plain page</p></body></html>"
    platform, archive_url = content_demand._detect_newsletter(html)
    assert platform is None
    assert archive_url is None


def test_compute_post_counts_basic():
    posts = [
        BlogPost(title="Top 10", category="seo_listicle"),
        BlogPost(title="Top 5", category="seo_listicle"),
        BlogPost(title="Why I built X", category="founder_essay"),
    ]
    counts, recent = content_demand._compute_post_counts(posts)
    assert counts["seo_listicle"] == 2
    assert counts["founder_essay"] == 1
    assert recent is None  # no dates supplied


def test_compute_post_counts_most_recent_date():
    posts = [
        BlogPost(title="A", category="other", published_date="2026-01-15"),
        BlogPost(title="B", category="other", published_date="2026-04-15"),
        BlogPost(title="C", category="other", published_date="2026-02-20"),
    ]
    _counts, recent = content_demand._compute_post_counts(posts)
    assert recent == "2026-04-15"


def test_compute_post_counts_ignores_unparseable_dates():
    posts = [
        BlogPost(title="A", category="other", published_date="January 10, 2025"),
        BlogPost(title="B", category="other", published_date="2026-04-15"),
    ]
    _counts, recent = content_demand._compute_post_counts(posts)
    assert recent == "2026-04-15"


def test_emit_findings_no_content_at_all():
    findings, gaps, questions = content_demand._emit_findings(  # noqa: RUF059
        domain="acme.com",
        blog_index_url=None,
        blog_posts=[],
        post_counts={},
        most_recent_date=None,
        lead_magnets=[],
        podcast=(None, None),
        newsletter=(None, None),
    )
    text = " ".join(f.text.lower() for f in findings) + " " + " ".join(questions).lower()
    assert "no" in text
    assert "blog" in text or "content" in text or "insights" in text


def test_emit_findings_seo_dominant():
    posts = [BlogPost(title=f"Top {i}", category="seo_listicle") for i in range(12)]
    posts += [BlogPost(title="x", category="other") for _ in range(3)]
    counts = {"seo_listicle": 12, "other": 3}
    findings, _gaps, _q = content_demand._emit_findings(
        domain="acme.com",
        blog_index_url="https://acme.com/blog",
        blog_posts=posts,
        post_counts=counts,
        most_recent_date="2026-04-15",
        lead_magnets=[],
        podcast=(None, None),
        newsletter=(None, None),
    )
    text = " ".join(f.text.lower() for f in findings)
    assert "seo" in text or "listicle" in text


def test_emit_findings_dormant_blog():
    """most_recent_date > 90 days old triggers a stale-content finding."""
    posts = [BlogPost(title="Old", category="other", published_date="2025-01-10")]
    findings, _gaps, _q = content_demand._emit_findings(
        domain="acme.com",
        blog_index_url="https://acme.com/blog",
        blog_posts=posts,
        post_counts={"other": 1},
        most_recent_date="2025-01-10",
        lead_magnets=[],
        podcast=(None, None),
        newsletter=(None, None),
    )
    text = " ".join(f.text.lower() for f in findings)
    assert "stale" in text or "dormant" in text or "days" in text or "de-prioriti" in text


def test_emit_findings_blog_no_lead_magnets():
    posts = [BlogPost(title="A", category="thought_leadership") for _ in range(5)]
    findings, gaps, _q = content_demand._emit_findings(
        domain="acme.com",
        blog_index_url="https://acme.com/blog",
        blog_posts=posts,
        post_counts={"thought_leadership": 5},
        most_recent_date="2026-04-15",
        lead_magnets=[],
        podcast=(None, None),
        newsletter=(None, None),
    )
    text = (" ".join(f.text.lower() for f in findings) + " " + " ".join(gaps).lower())
    assert "lead magnet" in text or "conversion" in text or "trust" in text


def test_emit_findings_lead_magnet_heavy():
    posts = [BlogPost(title="A", category="thought_leadership") for _ in range(5)]
    magnets = [
        LeadMagnet(title=f"M{i}", asset_type="ebook", source_page="homepage", has_form_gate=True)
        for i in range(6)
    ]
    findings, _gaps, _q = content_demand._emit_findings(
        domain="acme.com",
        blog_index_url="https://acme.com/blog",
        blog_posts=posts,
        post_counts={"thought_leadership": 5},
        most_recent_date="2026-04-15",
        lead_magnets=magnets,
        podcast=(None, None),
        newsletter=(None, None),
    )
    text = " ".join(f.text.lower() for f in findings)
    assert "lead magnet" in text or "funnel" in text or "capture" in text


def test_emit_findings_substack_newsletter():
    findings, _gaps, _q = content_demand._emit_findings(
        domain="acme.com",
        blog_index_url=None,
        blog_posts=[],
        post_counts={},
        most_recent_date=None,
        lead_magnets=[],
        podcast=(None, None),
        newsletter=("substack", "https://acme.substack.com"),
    )
    text = " ".join(f.text.lower() for f in findings)
    assert "substack" in text or "founder" in text or "direct" in text


def test_collect_writes_evidence(tmp_path):
    ctx = _make_ctx(tmp_path, scrape_responses={
        "https://acme.com": {
            "html": _load("homepage_with_podcast_apple.html"),
            "markdown": "",
            "metadata": {"sourceURL": "https://acme.com"},
        },
        "https://acme.com/blog": {
            "html": _load("blog_simple.html"),
            "markdown": "",
            "metadata": {"sourceURL": "https://acme.com/blog"},
        },
    })
    asyncio.run(content_demand.collect(ctx))
    evidence = tmp_path / "evidence" / "content_demand"
    assert (evidence / "homepage.html").exists()
    assert (evidence / "blog.html").exists()
    assert (evidence / "content_demand_summary.json").exists()


def test_collect_returns_content_demand_data(tmp_path):
    from rrxray.schemas.content_demand import ContentDemandData

    ctx = _make_ctx(tmp_path, scrape_responses={
        "https://acme.com": {
            "html": _load("homepage_with_podcast_apple.html"),
            "markdown": "",
            "metadata": {"sourceURL": "https://acme.com"},
        },
        "https://acme.com/blog": {
            "html": _load("blog_simple.html"),
            "markdown": "",
            "metadata": {"sourceURL": "https://acme.com/blog"},
        },
    })
    result = asyncio.run(content_demand.collect(ctx))
    assert isinstance(result, ContentDemandData)
    assert result.blog_index_url == "https://acme.com/blog"
    assert len(result.blog_posts) >= 3
    assert result.podcast_platform == "apple_podcasts"


def test_collect_categorizes_posts(tmp_path):
    ctx = _make_ctx(tmp_path, scrape_responses={
        "https://acme.com": {
            "html": "<html></html>",
            "markdown": "",
            "metadata": {"sourceURL": "https://acme.com"},
        },
        "https://acme.com/blog": {
            "html": _load("blog_seo_dominant.html"),
            "markdown": "",
            "metadata": {"sourceURL": "https://acme.com/blog"},
        },
    })
    result = asyncio.run(content_demand.collect(ctx))
    assert result.post_counts_by_category.get("seo_listicle", 0) >= 8


def test_collect_handles_no_blog(tmp_path):
    """No blog reachable on standard paths: collector returns data with a finding, no exception."""
    ctx = _make_ctx(tmp_path, scrape_responses={
        "https://acme.com": {
            "html": "<html><body>homepage</body></html>",
            "markdown": "",
            "metadata": {"sourceURL": "https://acme.com"},
        },
    })
    result = asyncio.run(content_demand.collect(ctx))
    assert result.blog_index_url is None
    assert result.blog_posts == []
    assert len(result.findings) >= 1


def test_collect_handles_homepage_failure(tmp_path):
    """Homepage scrape fails: still collect blog data."""
    ctx = _make_ctx(tmp_path, scrape_responses={
        "https://acme.com/blog": {
            "html": _load("blog_simple.html"),
            "markdown": "",
            "metadata": {"sourceURL": "https://acme.com/blog"},
        },
    })
    result = asyncio.run(content_demand.collect(ctx))
    assert result.blog_index_url == "https://acme.com/blog"
    assert len(result.blog_posts) >= 3
    assert result.podcast_platform is None
    assert result.newsletter_platform is None


def test_collect_total_failure_returns_graceful_data(tmp_path):
    """All scrapes fail: collector returns a ContentDemandData with findings."""
    ctx = _make_ctx(tmp_path, scrape_responses={})
    result = asyncio.run(content_demand.collect(ctx))
    assert result.blog_index_url is None
    assert result.blog_posts == []
    assert len(result.findings) >= 1


def test_source_citation_evidence_path_relative(tmp_path):
    """SourceCitation.evidence_path must NOT start with 'evidence/' to avoid template double-prefix."""
    ctx = _make_ctx(tmp_path, scrape_responses={
        "https://acme.com/blog": {
            "html": _load("blog_simple.html"),
            "markdown": "",
            "metadata": {"sourceURL": "https://acme.com/blog"},
        },
    })
    result = asyncio.run(content_demand.collect(ctx))
    for source in result.sources:
        if source.evidence_path:
            assert not source.evidence_path.startswith("evidence/")
            assert source.evidence_path.startswith("content_demand/")
