# Phase 2.1d: content_demand Collector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the fourth Section A collector — content_demand — which surfaces blog cadence + post-category mix + lead-magnet posture + podcast presence + newsletter presence, then wire it into the Section A synthesizer so the prompt reads four signals.

**Architecture:** Structurally identical to Phase 2.1c. New collector module + new schema module + new catalog module + new renderer partial + one new conditional block on the existing Section A synthesizer prompt + one-line additions to `pipeline.COLLECTORS` and `CollectorOutputs`. No new shared services. Two Firecrawl scrapes per domain (homepage + blog index). No LLM in the collector path.

**Tech Stack:** Python 3.14, pydantic v2, pytest-asyncio, Jinja2 templates, Firecrawl SDK (already wired). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-05-08-rrxray-phase-2.1d-content-demand-design.md`

**Reference plan (same shape):** `docs/superpowers/plans/2026-05-07-rrxray-phase-2.1c-revenue-motion.md`

---

## File Structure

`[T#]` indicates the task that creates or modifies each file.

```
NEW:
  rrxray/schemas/content_demand.py                  [T1: BlogPost, LeadMagnet, ContentDemandData]
  rrxray/collectors/_content_demand_catalog.py      [T3: CONTENT_CATEGORIES, CONTENT_KEYWORDS, LEAD_MAGNET_CTA_PATTERNS, PODCAST_PATTERNS, SUBSTACK_PATTERN]
  rrxray/collectors/content_demand.py               [T4-T11: collector body]
  templates/_content_demand_detail.md.jinja         [T12: Module Detail partial]
  tests/test_content_demand_schemas.py              [T1: schema round-trip + validation]
  tests/test_content_demand_catalog.py              [T3: catalog integrity]
  tests/test_content_demand.py                      [T4-T11: collector tests]
  tests/fixtures/synthetic/content_demand/          [T4-T11: HTML fixtures]

MODIFIED:
  rrxray/schemas/data.py                            [T2: add content_demand field on CollectorOutputs + import + model_rebuild]
  rrxray/pipeline.py                                [T14: append content_demand to COLLECTORS]
  rrxray/prompts/observed_gtm_motion.md             [T13: fourth conditional block + framework guidance]
  rrxray/synthesizers/observed_gtm_motion.py        [T13: read content_demand from collector_outputs; pass to renderer; extend skip-when-all-absent check]
  tests/test_synthesizer_observed_gtm_motion.py     [T13: test_synth_runs_with_four_collectors]
  tests/test_schemas.py                             [T2: round-trip + field presence tests]
  templates/report_internal.md.jinja                [T12: include _content_demand_detail partial]
  tests/test_render_internal.py                     [T12: renderer tests]
  tests/test_pipeline_graceful_degradation.py       [T14: four-collector regression test]
```

---

## Task overview

14 tasks. T1-T3 build the foundation (schemas, CollectorOutputs wiring, catalog). T4-T11 implement the collector logic bottom-up (URL discovery → parsing → detection sub-routines → orchestration). T12 wires the renderer; T13 wires the synthesizer prompt + body; T14 registers in the pipeline. Quality gate is Dale-led after all coded tasks pass.

| # | Task | Model | Type |
|---|---|---|---|
| T1 | BlogPost / LeadMagnet / ContentDemandData schemas | Haiku 4.5 | Mechanical |
| T2 | Add `content_demand` field to `CollectorOutputs` | Haiku 4.5 | Mechanical |
| T3 | Content-category catalog + lead-magnet / podcast / newsletter patterns | Haiku 4.5 | Mechanical |
| T4 | Collector skeleton + `_discover_blog_url()` | Opus 4.7 | Logic |
| T5 | `_parse_blog_posts()` (anchor + `<time>` parsing, 15-post cap) | Opus 4.7 | Logic |
| T6 | `_categorize_post()` (keyword catalog + SEO listicle regex) | Opus 4.7 | Logic |
| T7 | `_detect_lead_magnets()` (CTA + form-near + asset-type, 10-per-domain cap) | Opus 4.7 | Logic |
| T8 | `_detect_podcast()` (RSS link head sniff + Apple/Spotify regex) | Opus 4.7 | Logic |
| T9 | `_detect_newsletter()` (Substack regex + embedded-form heuristic) | Opus 4.7 | Logic |
| T10 | `_compute_post_counts()` + `_emit_findings()` | Opus 4.7 | Logic |
| T11 | `collect()` orchestration + `_write_evidence()` | Opus 4.7 | Logic |
| T12 | Renderer partial + report template include + render tests | Haiku 4.5 | Mechanical |
| T13 | Synthesizer prompt fourth conditional block + body update | Opus 4.7 | Logic + taste |
| T14 | Pipeline registration + four-collector regression test | Haiku 4.5 | Mechanical |

---

## Task 1: BlogPost / LeadMagnet / ContentDemandData schemas

**Model:** Haiku 4.5 (mechanical).

**Files:**
- Create: `rrxray/schemas/content_demand.py`
- Create: `tests/test_content_demand_schemas.py`

- [ ] **Step 1: Write failing tests in `tests/test_content_demand_schemas.py`**

```python
"""ContentDemandData / BlogPost / LeadMagnet schema round-trip + validation."""
import json

import pytest
from pydantic import ValidationError

from rrxray.schemas.content_demand import (
    BlogPost,
    ContentCategory,
    ContentDemandData,
    LeadMagnet,
    LeadMagnetAssetType,
)


def test_blog_post_minimal():
    p = BlogPost(title="The Future of B2B Sales", category="thought_leadership")
    assert p.title == "The Future of B2B Sales"
    assert p.category == "thought_leadership"
    assert p.url is None
    assert p.author is None
    assert p.published_date is None
    assert p.matched_keyword is None


def test_blog_post_rejects_invalid_category():
    with pytest.raises(ValidationError):
        BlogPost(title="x", category="not_a_category")  # type: ignore[arg-type]


def test_lead_magnet_minimal():
    lm = LeadMagnet(title="The 2026 Sales Playbook", asset_type="ebook", source_page="homepage")
    assert lm.title == "The 2026 Sales Playbook"
    assert lm.asset_type == "ebook"
    assert lm.source_page == "homepage"
    assert lm.has_form_gate is False
    assert lm.url is None


def test_lead_magnet_rejects_invalid_asset_type():
    with pytest.raises(ValidationError):
        LeadMagnet(title="x", asset_type="not_a_type", source_page="homepage")  # type: ignore[arg-type]


def test_content_demand_data_defaults_empty():
    d = ContentDemandData()
    assert d.blog_index_url is None
    assert d.blog_posts == []
    assert d.post_counts_by_category == {}
    assert d.most_recent_post_date is None
    assert d.lead_magnets == []
    assert d.podcast_platform is None
    assert d.podcast_name is None
    assert d.newsletter_platform is None
    assert d.newsletter_archive_url is None
    assert d.findings == []
    assert d.gaps == []
    assert d.discovery_questions == []
    assert d.sources == []


def test_content_demand_data_round_trips():
    d = ContentDemandData(
        blog_index_url="https://example.com/blog",
        blog_posts=[
            BlogPost(title="Why I Built X", category="founder_essay"),
            BlogPost(title="10 ways to close more deals", category="seo_listicle"),
        ],
        post_counts_by_category={"founder_essay": 1, "seo_listicle": 1},
        most_recent_post_date="2026-04-15",
        lead_magnets=[
            LeadMagnet(title="The Playbook", asset_type="ebook", source_page="homepage", has_form_gate=True),
        ],
        podcast_platform="apple_podcasts",
        podcast_name="The Revenue Show",
        newsletter_platform="substack",
        newsletter_archive_url="https://example.substack.com",
    )
    serialized = d.model_dump_json()
    restored = ContentDemandData.model_validate(json.loads(serialized))
    assert restored.blog_index_url == "https://example.com/blog"
    assert len(restored.blog_posts) == 2
    assert restored.lead_magnets[0].has_form_gate is True
    assert restored.podcast_platform == "apple_podcasts"
    assert restored.newsletter_platform == "substack"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_content_demand_schemas.py -v
```

Expected: ERRORS with `ModuleNotFoundError: No module named 'rrxray.schemas.content_demand'`.

- [ ] **Step 3: Create `rrxray/schemas/content_demand.py`**

```python
"""Schemas specific to the content_demand collector."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from rrxray.schemas._shared import Finding, SourceCitation

ContentCategory = Literal[
    "thought_leadership",
    "seo_listicle",
    "case_study",
    "product_announcement",
    "founder_essay",
    "tutorial",
    "news_pr",
    "other",
]

LeadMagnetAssetType = Literal[
    "ebook", "whitepaper", "guide", "template", "calculator",
    "report", "webinar",
]


class BlogPost(BaseModel):
    title: str
    url: str | None = None
    author: str | None = None
    published_date: str | None = None     # ISO string; not all blogs surface a date
    category: ContentCategory
    matched_keyword: str | None = None


class LeadMagnet(BaseModel):
    title: str
    asset_type: LeadMagnetAssetType
    url: str | None = None
    has_form_gate: bool = False           # detected form near the CTA = email capture
    source_page: str                      # where on the site we saw it (homepage, blog index)


class ContentDemandData(BaseModel):
    blog_index_url: str | None = None
    blog_posts: list[BlogPost] = []
    post_counts_by_category: dict[str, int] = {}
    most_recent_post_date: str | None = None
    lead_magnets: list[LeadMagnet] = []
    podcast_platform: Literal["apple_podcasts", "spotify", "rss_only"] | None = None
    podcast_name: str | None = None
    newsletter_platform: Literal["substack", "embedded_form"] | None = None
    newsletter_archive_url: str | None = None
    findings: list[Finding] = []
    gaps: list[str] = []
    discovery_questions: list[str] = []
    sources: list[SourceCitation] = []
```

- [ ] **Step 4: Run tests + ruff**

```bash
uv run pytest tests/test_content_demand_schemas.py -v
uv run ruff check rrxray/ tests/
```

Expected: 6 tests pass. Ruff clean.

- [ ] **Step 5: Commit**

```bash
git add rrxray/schemas/content_demand.py tests/test_content_demand_schemas.py
git commit -m "Add ContentDemandData, BlogPost, LeadMagnet schemas"
```

---

## Task 2: Add content_demand field to CollectorOutputs

**Model:** Haiku 4.5 (mechanical).

**Files:**
- Modify: `rrxray/schemas/data.py`
- Modify: `tests/test_schemas.py`

- [ ] **Step 1: Append failing tests to `tests/test_schemas.py`**

```python
def test_collector_outputs_has_content_demand_field():
    """CollectorOutputs must accept a content_demand field."""
    from rrxray.schemas.content_demand import ContentDemandData
    from rrxray.schemas.data import CollectorOutputs

    co = CollectorOutputs(content_demand=ContentDemandData())
    assert co.content_demand is not None


def test_collector_outputs_content_demand_defaults_none():
    from rrxray.schemas.data import CollectorOutputs
    co = CollectorOutputs()
    assert co.content_demand is None


def test_collector_outputs_four_section_a_collectors_round_trip():
    import json
    from rrxray.schemas.content_demand import BlogPost, ContentDemandData
    from rrxray.schemas.data import CollectorOutputs
    from rrxray.schemas.pricing_packaging import PricingPackagingData
    from rrxray.schemas.revenue_motion import JobPosting, RevenueMotionData
    from rrxray.schemas.tech_stack import DetectedTool, TechStackData

    co = CollectorOutputs(
        pricing_packaging=PricingPackagingData(
            has_public_pricing=True, is_contact_us_gated=False,
            current_pricing_url="https://example.com/pricing",
        ),
        tech_stack=TechStackData(
            detected_tools=[DetectedTool(
                name="HubSpot", category="marketing_automation", confidence="high",
                signature_id="hubspot:strict_js", matched_text="x",
            )],
        ),
        revenue_motion=RevenueMotionData(
            careers_page_url="https://example.com/careers",
            open_roles=[JobPosting(title="AE", category="ae", source="company_careers")],
        ),
        content_demand=ContentDemandData(
            blog_index_url="https://example.com/blog",
            blog_posts=[BlogPost(title="The Future of X", category="thought_leadership")],
        ),
    )
    serialized = co.model_dump_json()
    restored = CollectorOutputs.model_validate(json.loads(serialized))
    assert restored.content_demand is not None
    assert restored.content_demand.blog_posts[0].title == "The Future of X"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_schemas.py -v -k content_demand
```

Expected: 3 new tests fail.

- [ ] **Step 3: Modify `rrxray/schemas/data.py`**

Add the `content_demand` field on `CollectorOutputs`:

```python
class CollectorOutputs(BaseModel):
    """One field per collector. None = not run or failed gracefully."""
    model_config = ConfigDict(validate_assignment=True)
    pricing_packaging: "PricingPackagingData | None" = None  # forward ref
    tech_stack: "TechStackData | None" = None  # forward ref
    revenue_motion: "RevenueMotionData | None" = None  # forward ref
    content_demand: "ContentDemandData | None" = None  # forward ref
    leadership_stability: "LeadershipStabilityData | None" = None  # forward ref
```

At the bottom of the file, alongside the existing forward-ref imports, add the new one (re-using the existing `model_rebuild()` call):

```python
# Resolve forward references
from rrxray.schemas.content_demand import ContentDemandData  # noqa: E402
from rrxray.schemas.leadership_stability import LeadershipStabilityData  # noqa: E402
from rrxray.schemas.pricing_packaging import PricingPackagingData  # noqa: E402
from rrxray.schemas.revenue_motion import RevenueMotionData  # noqa: E402
from rrxray.schemas.tech_stack import TechStackData  # noqa: E402

CollectorOutputs.model_rebuild()
```

- [ ] **Step 4: Run tests + ruff**

```bash
uv run pytest tests/test_schemas.py -v
uv run pytest -v 2>&1 | tail -3
uv run ruff check rrxray/ tests/
```

Expected: 3 new tests pass; full suite green.

- [ ] **Step 5: Commit**

```bash
git add rrxray/schemas/data.py tests/test_schemas.py
git commit -m "Add content_demand field to CollectorOutputs"
```

---

## Task 3: Content-category catalog + detection patterns

**Model:** Haiku 4.5 (mechanical).

**Files:**
- Create: `rrxray/collectors/_content_demand_catalog.py`
- Create: `tests/test_content_demand_catalog.py`
- Create: `tests/fixtures/synthetic/content_demand/.gitkeep`

- [ ] **Step 1: Write failing tests in `tests/test_content_demand_catalog.py`**

```python
"""Catalog integrity tests."""
import re

from rrxray.collectors._content_demand_catalog import (
    CONTENT_CATEGORIES,
    CONTENT_KEYWORDS,
    LEAD_MAGNET_CTA_PATTERNS,
    PODCAST_PATTERNS,
    SUBSTACK_PATTERN,
)


def test_content_categories_has_eight_entries():
    assert len(CONTENT_CATEGORIES) == 8
    expected = {
        "thought_leadership", "seo_listicle", "case_study",
        "product_announcement", "founder_essay", "tutorial",
        "news_pr", "other",
    }
    assert set(CONTENT_CATEGORIES) == expected


def test_content_keywords_all_have_required_keys():
    for entry in CONTENT_KEYWORDS:
        assert "category" in entry
        assert "keywords" in entry
        assert isinstance(entry["keywords"], list)
        assert len(entry["keywords"]) >= 3


def test_content_keywords_categories_are_valid():
    valid = set(CONTENT_CATEGORIES)
    for entry in CONTENT_KEYWORDS:
        assert entry["category"] in valid, f"unknown category {entry['category']}"


def test_content_keywords_seo_listicle_checked_first():
    """Order matters: more specific patterns should appear first in the list."""
    first_category = CONTENT_KEYWORDS[0]["category"]
    assert first_category == "seo_listicle"


def test_lead_magnet_cta_patterns_have_seven_asset_types():
    asset_types = {p["asset_type"] for p in LEAD_MAGNET_CTA_PATTERNS}
    expected = {"ebook", "whitepaper", "guide", "template", "calculator", "report", "webinar"}
    assert asset_types == expected


def test_podcast_patterns_compile_and_match():
    by_platform = {p["platform"]: p["url_pattern"] for p in PODCAST_PATTERNS}
    apple = re.compile(by_platform["apple_podcasts"])
    spotify = re.compile(by_platform["spotify"])
    assert apple.search("https://podcasts.apple.com/us/podcast/abc-show")
    assert spotify.search("https://open.spotify.com/show/abc123XYZ")


def test_substack_pattern_compiles_and_matches():
    p = re.compile(SUBSTACK_PATTERN)
    assert p.search("https://example.substack.com/archive")
    assert not p.search("https://example.com/blog")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_content_demand_catalog.py -v
```

Expected: ImportError on the catalog module.

- [ ] **Step 3: Create `rrxray/collectors/_content_demand_catalog.py`**

```python
"""Content-category and lead-magnet / podcast / newsletter detection catalogs.

Hardcoded keyword lists for deterministic categorization. Order matters: more
specific patterns appear first so they beat generic ones (e.g., SEO listicles
match before generic thought leadership).

Adding a content category keyword: append a dict to CONTENT_KEYWORDS at the
appropriate priority position.

Adding a podcast platform: append a dict to PODCAST_PATTERNS with platform +
url_pattern (regex).
"""
from __future__ import annotations

CONTENT_CATEGORIES: list[str] = [
    "thought_leadership",
    "seo_listicle",
    "case_study",
    "product_announcement",
    "founder_essay",
    "tutorial",
    "news_pr",
    "other",
]


# Order matters: more specific titles checked first
CONTENT_KEYWORDS: list[dict] = [
    # SEO listicles - very specific patterns. The numeric prefixes are checked
    # via a dedicated regex in addition to these substrings, since "5 ways to"
    # and "10 ways to" should both match without enumerating every integer.
    {"category": "seo_listicle", "keywords": [
        "top 10", "top 5", "top 7", "best 10", "best of",
        "the ultimate guide to", "the complete guide to",
        " ways to ", " tips for ", " mistakes to avoid",
    ]},

    # Case studies - distinct framing
    {"category": "case_study", "keywords": [
        "case study", "customer story", "how we helped",
        "customer spotlight", "success story", "results with",
    ]},

    # Product announcements
    {"category": "product_announcement", "keywords": [
        "introducing", "announcing", "now available", "new feature",
        "we shipped", "release notes", "what's new in",
        "product update", "general availability", "ga release",
    ]},

    # Tutorials
    {"category": "tutorial", "keywords": [
        "how to ", "step by step", "step-by-step", "tutorial",
        "getting started with", "quickstart", "the basics of",
        "walkthrough", "in 5 minutes", "in 10 minutes",
    ]},

    # News / PR
    {"category": "news_pr", "keywords": [
        "raises ", "raised ", "series a", "series b", "series c",
        "named to", "wins ", "award", "named a", "recognized as",
        "partnership with", "acquired", "acquires",
    ]},

    # Founder essay (single-author opinion pieces)
    {"category": "founder_essay", "keywords": [
        "why i ", "what i ", "the case for ", "the case against ",
        "lessons learned", "from the ceo", "from the founder",
        "my take on", "an open letter to",
    ]},

    # Thought leadership (catch-all for long-form expert content)
    {"category": "thought_leadership", "keywords": [
        "the future of", "the state of", "rethinking ", "the new ",
        "framework", "playbook", "deep dive into",
        "what we learned", "research:", "data on",
    ]},
]


# Lead magnet detection: CTA-text patterns paired with asset-type inference
LEAD_MAGNET_CTA_PATTERNS: list[dict] = [
    {"asset_type": "ebook",       "patterns": ["download the ebook", "free ebook", "the ebook"]},
    {"asset_type": "whitepaper",  "patterns": ["download the whitepaper", "white paper", "whitepaper"]},
    {"asset_type": "guide",       "patterns": ["the guide", "free guide", "download the guide", "complete guide"]},
    {"asset_type": "template",    "patterns": ["free template", "the template", "download template"]},
    {"asset_type": "calculator",  "patterns": ["calculator", "roi calculator", "cost calculator"]},
    {"asset_type": "report",      "patterns": ["the report", "free report", "download the report", "state of"]},
    {"asset_type": "webinar",     "patterns": ["register for", "watch the webinar", "on-demand webinar", "live webinar"]},
]


# Podcast detection patterns
PODCAST_PATTERNS: list[dict[str, str]] = [
    {"platform": "apple_podcasts", "url_pattern": r"podcasts\.apple\.com/[a-z]+/podcast/[^\s\"']+"},
    {"platform": "spotify",        "url_pattern": r"open\.spotify\.com/show/[a-zA-Z0-9]+"},
]


# Newsletter detection
SUBSTACK_PATTERN = r"([a-z0-9-]+)\.substack\.com"
```

- [ ] **Step 4: Create the fixture directory marker**

```bash
mkdir -p tests/fixtures/synthetic/content_demand
touch tests/fixtures/synthetic/content_demand/.gitkeep
```

- [ ] **Step 5: Run tests + ruff**

```bash
uv run pytest tests/test_content_demand_catalog.py -v
uv run ruff check rrxray/ tests/
```

Expected: 7 catalog tests pass.

- [ ] **Step 6: Commit**

```bash
git add rrxray/collectors/_content_demand_catalog.py tests/test_content_demand_catalog.py tests/fixtures/synthetic/content_demand/.gitkeep
git commit -m "Add content_demand catalog: 8 categories + lead-magnet/podcast/newsletter patterns"
```

---

## Task 4: Collector skeleton + `_discover_blog_url()`

**Model:** Opus 4.7 (logic).

**Files:**
- Create: `rrxray/collectors/content_demand.py` (skeleton with `NAME` + `_discover_blog_url`)
- Create: `tests/test_content_demand.py` (test helpers + discovery tests)
- Create: `tests/fixtures/synthetic/content_demand/blog_simple.html`

- [ ] **Step 1: Create the synthetic HTML fixture**

`tests/fixtures/synthetic/content_demand/blog_simple.html`:

```html
<!doctype html>
<html><head><title>Blog - Acme</title></head>
<body>
<h1>Insights from Acme</h1>
<ul>
  <li><a href="/blog/the-future-of-revenue">The Future of Revenue Ops</a>
      <time datetime="2026-04-15">April 15, 2026</time>
      <span class="author">By Jane Doe</span></li>
  <li><a href="/blog/10-ways-to-close-deals">10 ways to close more deals</a>
      <time datetime="2026-03-10">March 10, 2026</time></li>
  <li><a href="/blog/customer-story-acme">Customer Story: Acme + BetaCo</a>
      <time datetime="2026-02-20">February 20, 2026</time></li>
  <li><a href="/blog/why-i-built-this">Why I built this product</a>
      <time datetime="2026-01-12">January 12, 2026</time>
      <span class="author">By John Founder</span></li>
  <li><a href="/blog/how-to-write-emails">How to write better outbound emails</a>
      <time datetime="2025-12-05">December 5, 2025</time></li>
</ul>
</body></html>
```

- [ ] **Step 2: Write failing tests in `tests/test_content_demand.py`**

```python
"""content_demand collector tests."""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

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
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
uv run pytest tests/test_content_demand.py -v
```

Expected: ImportError on the collector module.

- [ ] **Step 4: Create `rrxray/collectors/content_demand.py` skeleton**

```python
"""content_demand collector: blog cadence + post mix + lead magnets + podcast + newsletter."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rrxray.context import CollectorContext

NAME = "content_demand"
log = logging.getLogger(f"rrxray.collectors.{NAME}")

CANDIDATE_BLOG_PATHS = ["/blog", "/insights", "/resources", "/news", "/articles", "/learn"]


async def _discover_blog_url(ctx: "CollectorContext"):
    """Try standard blog paths. Return (url, ScrapedPage) or (None, None)."""
    from rrxray.services.firecrawl_client import FirecrawlError
    base = f"https://{ctx.domain}"
    for path in CANDIDATE_BLOG_PATHS:
        url = base + path
        try:
            page = await ctx.firecrawl.scrape_url(url, only_main_content=False)
            html = page.html or ""
            if html.strip() and len(html) > 200:
                return url, page
        except FirecrawlError as e:
            log.debug("blog discover: %s not reachable: %s", url, e)
            continue
    return None, None
```

- [ ] **Step 5: Run tests + ruff**

```bash
uv run pytest tests/test_content_demand.py -v
uv run ruff check rrxray/ tests/
```

Expected: 5 tests pass.

- [ ] **Step 6: Commit**

```bash
git add rrxray/collectors/content_demand.py tests/test_content_demand.py tests/fixtures/synthetic/content_demand/blog_simple.html
git commit -m "Add content_demand collector skeleton: blog URL discovery"
```

---

## Task 5: `_parse_blog_posts()` (anchor + `<time>` parsing, 15-post cap)

**Model:** Opus 4.7 (logic).

**Files:**
- Modify: `rrxray/collectors/content_demand.py` (append `_parse_blog_posts`)
- Modify: `tests/test_content_demand.py` (append parsing tests)
- Create: `tests/fixtures/synthetic/content_demand/blog_no_dates.html`

- [ ] **Step 1: Create the no-dates fixture**

`tests/fixtures/synthetic/content_demand/blog_no_dates.html`:

```html
<!doctype html>
<html><head><title>Insights</title></head>
<body>
<h1>Insights</h1>
<article><a href="/insights/post-1">Post One Title</a></article>
<article><a href="/insights/post-2">Post Two Title</a></article>
<article><a href="/insights/post-3">Post Three Title</a></article>
</body></html>
```

- [ ] **Step 2: Append failing tests**

```python
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
```

- [ ] **Step 3: Append implementation to `rrxray/collectors/content_demand.py`**

```python
import re  # noqa: E402
from urllib.parse import urljoin  # noqa: E402

from rrxray.schemas.content_demand import BlogPost  # noqa: E402


_BLOG_LINK_RE = re.compile(
    r'<a[^>]*\bhref=["\']([^"\']+)["\'][^>]*>([^<]+)</a>',
    re.IGNORECASE,
)

# Match <time datetime="2026-04-15"> or <time datetime="2026-04-15T10:00:00Z">
_TIME_DATETIME_RE = re.compile(
    r'<time[^>]*\bdatetime=["\'](\d{4}-\d{2}-\d{2})[^"\']*["\']',
    re.IGNORECASE,
)

# Fallback: match "Month DD, YYYY" or "YYYY-MM-DD" in nearby text
_DATE_TEXT_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2})|"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}",
    re.IGNORECASE,
)

_AUTHOR_RE = re.compile(
    r'(?:class=["\'][^"\']*author[^"\']*["\']|>By\s+)([^<]+)',
    re.IGNORECASE,
)


def _parse_blog_posts(html: str, base_url: str) -> list[BlogPost]:
    """Extract up to 15 blog posts from HTML.

    Anchor tags are the primary signal. Dates come from a nearby <time
    datetime=...> attribute (preferred) or any "YYYY-MM-DD" / "Month DD, YYYY"
    substring within the surrounding chunk. Author extraction is best-effort.

    Returns first 15 in document order.
    """
    if not html:
        return []

    posts: list[BlogPost] = []
    seen_titles: set[str] = set()

    # Split into rough per-post chunks by anchor positions so we can correlate
    # nearby <time> / author tags with the link above them.
    matches = list(_BLOG_LINK_RE.finditer(html))
    for i, m in enumerate(matches):
        href = m.group(1).strip()
        title = m.group(2).strip()
        if not title or len(title) > 250:
            continue
        # Skip obvious nav links
        if title.lower() in {"home", "about", "contact", "blog", "insights", "next", "previous"}:
            continue
        if title in seen_titles:
            continue
        seen_titles.add(title)

        # Chunk: from this anchor to the next one (or end of html), used to
        # find date / author near this post.
        chunk_start = m.end()
        chunk_end = matches[i + 1].start() if i + 1 < len(matches) else min(len(html), chunk_start + 1000)
        chunk = html[chunk_start:chunk_end]

        # Date: prefer <time datetime="..."> attribute
        published_date: str | None = None
        time_m = _TIME_DATETIME_RE.search(chunk)
        if time_m:
            published_date = time_m.group(1)
        else:
            date_m = _DATE_TEXT_RE.search(chunk)
            if date_m:
                published_date = date_m.group(0)

        # Author: best-effort
        author: str | None = None
        author_m = _AUTHOR_RE.search(chunk)
        if author_m:
            author = author_m.group(1).strip()
            if author.lower().startswith("by "):
                author = author[3:].strip()
            if len(author) > 80:
                author = None

        full_url = urljoin(base_url, href) if href and not href.startswith("#") else None
        posts.append(BlogPost(
            title=title,
            url=full_url,
            author=author,
            published_date=published_date,
            category="other",  # categorization happens later via _categorize_post
            matched_keyword=None,
        ))

        if len(posts) >= 15:
            break

    return posts
```

- [ ] **Step 4: Run tests + ruff**

```bash
uv run pytest tests/test_content_demand.py -v
uv run ruff check rrxray/ tests/
```

Expected: 11 tests pass (5 from T4 + 6 new).

- [ ] **Step 5: Commit**

```bash
git add rrxray/collectors/content_demand.py tests/test_content_demand.py tests/fixtures/synthetic/content_demand/blog_no_dates.html
git commit -m "Add blog post parsing with anchor + time-tag extraction"
```

---

## Task 6: `_categorize_post()` (keyword catalog + SEO listicle regex)

**Model:** Opus 4.7 (logic).

**Files:**
- Modify: `rrxray/collectors/content_demand.py` (append `_categorize_post`)
- Modify: `tests/test_content_demand.py` (append categorization tests)

- [ ] **Step 1: Append failing tests**

```python
def test_categorize_post_seo_listicle_via_numeric_prefix():
    cat, kw = content_demand._categorize_post("10 ways to close more deals", "")
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
```

- [ ] **Step 2: Append implementation to `rrxray/collectors/content_demand.py`**

```python
from rrxray.collectors._content_demand_catalog import CONTENT_KEYWORDS  # noqa: E402


# Numeric-prefix SEO listicle pattern: "5 ways", "12 tips", "7 mistakes", etc.
_SEO_NUMERIC_RE = re.compile(
    r"^\s*\d{1,3}\s+(ways|tips|mistakes|reasons|things|tools|strategies|tactics|examples|signs|lessons)\b",
    re.IGNORECASE,
)


def _categorize_post(title: str, description: str = "") -> tuple[str, str | None]:
    """Categorize a post via the keyword catalog.

    Order-by-specificity: CONTENT_KEYWORDS is pre-ordered (SEO listicles
    first, thought leadership last as catch-all). First-match wins.

    A dedicated SEO-listicle numeric-prefix regex runs before the keyword
    catalog so "5 ways to...", "12 tips for..." etc. categorize even when the
    exact substring isn't in the catalog.

    Returns (category, matched_keyword). Falls back to ("other", None).
    """
    haystack = f"{title} {description}".lower()

    # SEO listicle numeric-prefix short-circuit
    if _SEO_NUMERIC_RE.search(title):
        return "seo_listicle", "<numeric-prefix>"

    for entry in CONTENT_KEYWORDS:
        for kw in entry["keywords"]:
            if kw.lower() in haystack:
                return entry["category"], kw
    return "other", None
```

- [ ] **Step 3: Run tests + ruff**

```bash
uv run pytest tests/test_content_demand.py -v
uv run ruff check rrxray/ tests/
```

Expected: 22 tests pass (11 prior + 11 new).

- [ ] **Step 4: Commit**

```bash
git add rrxray/collectors/content_demand.py tests/test_content_demand.py
git commit -m "Add content categorization: 8-category keyword catalog + SEO listicle regex"
```

---

## Task 7: `_detect_lead_magnets()` (CTA + form-near + asset-type)

**Model:** Opus 4.7 (logic).

**Files:**
- Modify: `rrxray/collectors/content_demand.py` (append `_detect_lead_magnets`)
- Modify: `tests/test_content_demand.py` (append lead-magnet tests)
- Create: `tests/fixtures/synthetic/content_demand/blog_with_lead_magnets.html`

### Note on T7 adaptations

Two bugs were caught against the verbatim code during the original execution (commit `aef24a8`) and the Step 3 block below now reflects the working version, not the initial draft. Re-executors should keep both adaptations.

First, anchor selection inside the +/-400-char match window must prefer an anchor whose anchor-text contains the matched pattern; falling back to the first anchor in the window picks up an unrelated earlier link (e.g. a nav link) and produces wrong `title` / `url` pairs. Second, the form-gate proximity check searches forward-only from the match (not over the full +/-400-char window) and clips at the next `<h1-6>` or `</section>` boundary, so an unrelated next-section signup form does not bleed in and falsely flag `has_form_gate=True`. The synthetic fixture has adjacent sections with and without form gates, so both adaptations are required for the tests to pass.

- [ ] **Step 1: Create the lead-magnets fixture**

`tests/fixtures/synthetic/content_demand/blog_with_lead_magnets.html`:

```html
<!doctype html>
<html><head><title>Resources</title></head>
<body>
<h1>Resources</h1>

<section>
  <h2>The 2026 Revenue Playbook</h2>
  <p>Our complete guide to running a modern revenue engine.</p>
  <a href="/resources/playbook">Download the ebook</a>
  <form action="/subscribe" method="post">
    <input type="email" name="email" required>
    <button type="submit">Get the ebook</button>
  </form>
</section>

<section>
  <h2>Pipeline ROI Calculator</h2>
  <a href="/tools/roi-calculator">Try the calculator</a>
</section>

<section>
  <h2>The State of Sales 2026</h2>
  <a href="/research/state-of-sales">Download the report</a>
  <form action="/gate" method="post">
    <input type="email" name="email" required>
    <button type="submit">Get the report</button>
  </form>
</section>

</body></html>
```

- [ ] **Step 2: Append failing tests**

```python
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
```

- [ ] **Step 3: Append implementation to `rrxray/collectors/content_demand.py`**

```python
from rrxray.collectors._content_demand_catalog import LEAD_MAGNET_CTA_PATTERNS  # noqa: E402
from rrxray.schemas.content_demand import LeadMagnet  # noqa: E402


_FORM_NEARBY_RE = re.compile(
    r'<form[^>]*>[\s\S]{0,500}<input[^>]*type=["\']email["\']',
    re.IGNORECASE,
)


def _detect_lead_magnets(html: str, source_page: str) -> list[LeadMagnet]:
    """Scan HTML for lead-magnet CTAs.

    For each CTA-text pattern from LEAD_MAGNET_CTA_PATTERNS, capture the
    surrounding anchor's href + title, infer asset_type from the matched
    pattern, and run a proximity check for a <form> with an email input in
    the same chunk to set has_form_gate.

    Cap: 10 results per call. Dedupe by URL (or title if URL is missing).
    """
    if not html:
        return []

    magnets: list[LeadMagnet] = []
    seen_keys: set[str] = set()

    for entry in LEAD_MAGNET_CTA_PATTERNS:
        asset_type = entry["asset_type"]
        for pattern in entry["patterns"]:
            for m in re.finditer(re.escape(pattern), html, re.IGNORECASE):
                # Capture the anchor surrounding (or just-after) this match
                start = max(0, m.start() - 400)
                end = min(len(html), m.end() + 400)
                window = html[start:end]

                # Prefer an anchor whose text contains the match (so a CTA
                # like "Try the calculator" wins over an unrelated earlier
                # anchor in the same window). Fall back to the first anchor
                # in the window otherwise.
                anchor_re = re.compile(
                    r'<a[^>]*\bhref=["\']([^"\']+)["\'][^>]*>([^<]+)</a>',
                    re.IGNORECASE,
                )
                anchor_m = None
                for cand in anchor_re.finditer(window):
                    if pattern.lower() in cand.group(2).lower():
                        anchor_m = cand
                        break
                if anchor_m is None:
                    anchor_m = anchor_re.search(window)
                if anchor_m:
                    url = anchor_m.group(1).strip()
                    title = anchor_m.group(2).strip()
                else:
                    url = ""
                    # Fall back to nearest <h*> text above the match
                    heading_m = re.search(
                        r"<h[1-6][^>]*>([^<]+)</h[1-6]>", window, re.IGNORECASE,
                    )
                    title = heading_m.group(1).strip() if heading_m else pattern

                if not title or len(title) > 200:
                    continue

                key = url or title.lower()
                if key in seen_keys:
                    continue
                seen_keys.add(key)

                # Form-gate proximity: look forward from the match for a
                # <form> with an email input, but stop at the next section
                # boundary (next <h1-6> or </section>) so we don't bleed
                # into the following lead-magnet's form.
                forward = html[m.end():m.end() + 600]
                boundary_m = re.search(
                    r"</section\s*>|<h[1-6]\b", forward, re.IGNORECASE,
                )
                forward_clipped = (
                    forward[: boundary_m.start()] if boundary_m else forward
                )
                has_form_gate = bool(_FORM_NEARBY_RE.search(forward_clipped))

                magnets.append(LeadMagnet(
                    title=title,
                    asset_type=asset_type,  # type: ignore[arg-type]
                    url=url or None,
                    has_form_gate=has_form_gate,
                    source_page=source_page,
                ))

                if len(magnets) >= 10:
                    return magnets

    return magnets
```

- [ ] **Step 4: Run tests + ruff**

```bash
uv run pytest tests/test_content_demand.py -v
uv run ruff check rrxray/ tests/
```

Expected: 28 tests pass (22 prior + 6 new).

- [ ] **Step 5: Commit**

```bash
git add rrxray/collectors/content_demand.py tests/test_content_demand.py tests/fixtures/synthetic/content_demand/blog_with_lead_magnets.html
git commit -m "Add lead-magnet detection: CTA patterns + form-near heuristic + asset-type inference"
```

---

## Task 8: `_detect_podcast()` (RSS link head sniff + Apple/Spotify regex)

**Model:** Opus 4.7 (logic).

**Files:**
- Modify: `rrxray/collectors/content_demand.py` (append `_detect_podcast`)
- Modify: `tests/test_content_demand.py` (append podcast tests)
- Create: `tests/fixtures/synthetic/content_demand/homepage_with_podcast_apple.html`
- Create: `tests/fixtures/synthetic/content_demand/homepage_with_podcast_spotify.html`

- [ ] **Step 1: Create the podcast fixtures**

`tests/fixtures/synthetic/content_demand/homepage_with_podcast_apple.html`:

```html
<!doctype html>
<html>
<head>
  <title>Acme - Revenue Tools</title>
  <link rel="alternate" type="application/rss+xml" title="The Revenue Show" href="https://feeds.acme.com/podcast.xml">
</head>
<body>
<p>Listen to our podcast on
  <a href="https://podcasts.apple.com/us/podcast/the-revenue-show/id123456">Apple Podcasts</a>.
</p>
</body></html>
```

`tests/fixtures/synthetic/content_demand/homepage_with_podcast_spotify.html`:

```html
<!doctype html>
<html><head><title>Acme</title></head>
<body>
<p>Find us on
  <a href="https://open.spotify.com/show/AbCdEf123XyZ">Spotify</a>.
</p>
</body></html>
```

- [ ] **Step 2: Append failing tests**

```python
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
```

- [ ] **Step 3: Append implementation to `rrxray/collectors/content_demand.py`**

```python
from rrxray.collectors._content_demand_catalog import PODCAST_PATTERNS  # noqa: E402


_RSS_LINK_RE = re.compile(
    r'<link[^>]*\brel=["\']alternate["\'][^>]*\btype=["\']application/rss\+xml["\'][^>]*>',
    re.IGNORECASE,
)

_RSS_TITLE_RE = re.compile(
    r'\btitle=["\']([^"\']+)["\']',
    re.IGNORECASE,
)


def _detect_podcast(homepage_html: str) -> tuple[str | None, str | None]:
    """Detect podcast presence.

    Priority: Apple Podcasts / Spotify URLs (concrete platforms) before
    rss_only. The RSS <link> title attribute provides the podcast name when
    present.

    Returns (platform, name) or (None, None).
    """
    if not homepage_html:
        return None, None

    # Parse the RSS title once (used to enrich any platform match).
    name: str | None = None
    rss_m = _RSS_LINK_RE.search(homepage_html)
    if rss_m:
        title_m = _RSS_TITLE_RE.search(rss_m.group(0))
        if title_m:
            name = title_m.group(1).strip() or None

    for entry in PODCAST_PATTERNS:
        if re.search(entry["url_pattern"], homepage_html, re.IGNORECASE):
            return entry["platform"], name

    if rss_m:
        return "rss_only", name

    return None, None
```

- [ ] **Step 4: Run tests + ruff**

```bash
uv run pytest tests/test_content_demand.py -v
uv run ruff check rrxray/ tests/
```

Expected: 32 tests pass (28 prior + 4 new).

- [ ] **Step 5: Commit**

```bash
git add rrxray/collectors/content_demand.py tests/test_content_demand.py tests/fixtures/synthetic/content_demand/homepage_with_podcast_apple.html tests/fixtures/synthetic/content_demand/homepage_with_podcast_spotify.html
git commit -m "Add podcast detection: RSS head sniff + Apple/Spotify regex"
```

---

## Task 9: `_detect_newsletter()` (Substack regex + embedded form heuristic)

**Model:** Opus 4.7 (logic).

**Files:**
- Modify: `rrxray/collectors/content_demand.py` (append `_detect_newsletter`)
- Modify: `tests/test_content_demand.py` (append newsletter tests)
- Create: `tests/fixtures/synthetic/content_demand/homepage_with_substack_newsletter.html`
- Create: `tests/fixtures/synthetic/content_demand/homepage_with_embedded_newsletter_form.html`

- [ ] **Step 1: Create the newsletter fixtures**

`tests/fixtures/synthetic/content_demand/homepage_with_substack_newsletter.html`:

```html
<!doctype html>
<html><head><title>Acme</title></head>
<body>
<p>Subscribe to our weekly take at
  <a href="https://acmenotes.substack.com">acmenotes.substack.com</a>.
</p>
</body></html>
```

`tests/fixtures/synthetic/content_demand/homepage_with_embedded_newsletter_form.html`:

```html
<!doctype html>
<html><head><title>Acme</title></head>
<body>
<footer>
  <h3>Join the newsletter</h3>
  <form action="/subscribe" method="post">
    <input type="email" name="email" placeholder="you@example.com" required>
    <button type="submit">Subscribe</button>
  </form>
</footer>
</body></html>
```

- [ ] **Step 2: Append failing tests**

```python
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
```

- [ ] **Step 3: Append implementation to `rrxray/collectors/content_demand.py`**

```python
from rrxray.collectors._content_demand_catalog import SUBSTACK_PATTERN  # noqa: E402


_NEWSLETTER_BUTTON_RE = re.compile(
    r"<button[^>]*>([^<]*)</button>",
    re.IGNORECASE,
)

_NEWSLETTER_KEYWORDS = ("subscribe", "newsletter", "sign up", "sign-up", "signup")


def _detect_newsletter(homepage_html: str) -> tuple[str | None, str | None]:
    """Detect newsletter posture.

    Substack first (concrete platform + archive URL). Otherwise an embedded
    <form> with an email input AND a nearby button whose text contains
    'subscribe', 'newsletter', or 'sign up' counts as embedded_form.

    Returns (platform, archive_url) or (None, None).
    """
    if not homepage_html:
        return None, None

    substack_m = re.search(SUBSTACK_PATTERN, homepage_html, re.IGNORECASE)
    if substack_m:
        subdomain = substack_m.group(1)
        return "substack", f"https://{subdomain}.substack.com"

    # Embedded form heuristic: <form> with <input type="email"> AND a nearby
    # button whose text contains a newsletter keyword.
    for form_m in re.finditer(
        r'<form[\s\S]{0,2000}?</form>', homepage_html, re.IGNORECASE,
    ):
        block = form_m.group(0)
        if not re.search(r'<input[^>]*\btype=["\']email["\']', block, re.IGNORECASE):
            continue
        for btn_m in _NEWSLETTER_BUTTON_RE.finditer(block):
            btn_text = btn_m.group(1).lower()
            if any(kw in btn_text for kw in _NEWSLETTER_KEYWORDS):
                return "embedded_form", None
        # Heading near the form: check 200 chars before the form for a newsletter cue
        before = homepage_html[max(0, form_m.start() - 200):form_m.start()].lower()
        if any(kw in before for kw in _NEWSLETTER_KEYWORDS):
            return "embedded_form", None

    return None, None
```

- [ ] **Step 4: Run tests + ruff**

```bash
uv run pytest tests/test_content_demand.py -v
uv run ruff check rrxray/ tests/
```

Expected: 36 tests pass (32 prior + 4 new).

- [ ] **Step 5: Commit**

```bash
git add rrxray/collectors/content_demand.py tests/test_content_demand.py tests/fixtures/synthetic/content_demand/homepage_with_substack_newsletter.html tests/fixtures/synthetic/content_demand/homepage_with_embedded_newsletter_form.html
git commit -m "Add newsletter detection: Substack regex + embedded-form heuristic"
```

---

## Task 10: `_compute_post_counts()` + `_emit_findings()`

**Model:** Opus 4.7 (logic).

**Files:**
- Modify: `rrxray/collectors/content_demand.py` (append `_compute_post_counts`, `_emit_findings`)
- Modify: `tests/test_content_demand.py` (append metrics + findings tests)
- Create: `tests/fixtures/synthetic/content_demand/blog_dormant.html`
- Create: `tests/fixtures/synthetic/content_demand/blog_seo_dominant.html`

- [ ] **Step 1: Create the dormant + seo-dominant fixtures**

`tests/fixtures/synthetic/content_demand/blog_dormant.html`:

```html
<!doctype html>
<html><head><title>Blog</title></head>
<body>
<h1>Blog</h1>
<article><a href="/blog/older-post">Reflections from last year</a>
  <time datetime="2025-01-10">January 10, 2025</time></article>
<article><a href="/blog/even-older">A note from 2024</a>
  <time datetime="2024-09-01">September 1, 2024</time></article>
</body></html>
```

`tests/fixtures/synthetic/content_demand/blog_seo_dominant.html`:

```html
<!doctype html>
<html><head><title>Blog</title></head>
<body>
<h1>Resources</h1>
<article><a href="/blog/1">Top 10 sales tools</a></article>
<article><a href="/blog/2">5 ways to close more deals</a></article>
<article><a href="/blog/3">12 tips for better outbound</a></article>
<article><a href="/blog/4">Best of: cold email subject lines</a></article>
<article><a href="/blog/5">7 mistakes to avoid in pipeline reviews</a></article>
<article><a href="/blog/6">The ultimate guide to forecasting</a></article>
<article><a href="/blog/7">10 ways to negotiate better</a></article>
<article><a href="/blog/8">Top 5 dashboards every CRO needs</a></article>
<article><a href="/blog/9">8 reasons sellers miss quota</a></article>
<article><a href="/blog/10">The complete guide to discovery calls</a></article>
<article><a href="/blog/11">15 tips for SDR onboarding</a></article>
<article><a href="/blog/12">9 mistakes to avoid in QBRs</a></article>
<article><a href="/blog/13">Customer Story: BetaCo unlocked 3x pipeline</a></article>
<article><a href="/blog/14">Why I left big tech</a></article>
<article><a href="/blog/15">The future of B2B buyer enablement</a></article>
</body></html>
```

- [ ] **Step 2: Append failing tests**

```python
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
    findings, gaps, questions = content_demand._emit_findings(
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
```

Also add the imports needed in the test file (add near the top of `tests/test_content_demand.py` if not already present):

```python
from rrxray.schemas.content_demand import BlogPost, LeadMagnet
```

- [ ] **Step 3: Append implementation to `rrxray/collectors/content_demand.py`**

```python
from datetime import UTC, date, datetime  # noqa: E402

from rrxray.schemas._shared import Finding, SourceCitation  # noqa: E402


def _compute_post_counts(
    blog_posts: list[BlogPost],
) -> tuple[dict[str, int], str | None]:
    """Aggregate counts per category and derive the most recent ISO date.

    Dates that don't parse as YYYY-MM-DD are ignored when computing
    most_recent_post_date (but the original string remains on the BlogPost).
    """
    counts: dict[str, int] = {}
    for p in blog_posts:
        counts[p.category] = counts.get(p.category, 0) + 1

    iso_dates: list[date] = []
    for p in blog_posts:
        if not p.published_date:
            continue
        try:
            iso_dates.append(date.fromisoformat(p.published_date))
        except ValueError:
            continue

    most_recent = max(iso_dates).isoformat() if iso_dates else None
    return counts, most_recent


def _emit_findings(
    domain: str,
    blog_index_url: str | None,
    blog_posts: list[BlogPost],
    post_counts: dict[str, int],
    most_recent_date: str | None,
    lead_magnets: list[LeadMagnet],
    podcast: tuple[str | None, str | None],
    newsletter: tuple[str | None, str | None],
) -> tuple[list[Finding], list[str], list[str]]:
    """Rule-based findings/gaps/questions for content posture. No LLM."""
    now = datetime.now(UTC)
    source_url = blog_index_url or f"https://{domain}"
    findings: list[Finding] = []
    gaps: list[str] = []
    questions: list[str] = []

    # No detectable content anywhere
    if (
        not blog_posts
        and not lead_magnets
        and podcast[0] is None
        and newsletter[0] is None
    ):
        findings.append(Finding(
            text=(
                f"No blog, lead magnets, podcast, or newsletter detected on {domain}. "
                f"Pipeline does not appear to run through content channels; the GTM "
                f"motion looks relationship-led or outbound-only."
            ),
            source=SourceCitation(url=source_url, timestamp=now),
        ))
        questions.append(
            "We did not detect a public content surface (blog, lead magnets, podcast, "
            "or newsletter). How does your GTM generate top-of-funnel demand today: "
            "outbound, referral, paid, or events?"
        )
        return findings, gaps, questions

    total_posts = len(blog_posts)
    podcast_platform, podcast_name = podcast
    newsletter_platform, _newsletter_archive = newsletter

    # Stale / dormant blog (most recent post > 90 days old)
    if most_recent_date:
        try:
            recent = date.fromisoformat(most_recent_date)
            days_since = (now.date() - recent).days
            if days_since > 90:
                findings.append(Finding(
                    text=(
                        f"Most recent blog post is from {most_recent_date} "
                        f"({days_since} days ago). Content function appears "
                        f"de-prioritized; check whether the team pivoted off "
                        f"content as a channel or simply defunded it."
                    ),
                    source=SourceCitation(url=source_url, timestamp=now),
                ))
                questions.append(
                    f"Your most recent blog post is from {most_recent_date}. "
                    "Was content de-prioritized intentionally, or did the function "
                    "shift to a different surface (newsletter, podcast, social)?"
                )
        except ValueError:
            pass

    # SEO-dominant content mix
    if total_posts > 0:
        seo_count = post_counts.get("seo_listicle", 0)
        if seo_count / total_posts >= 0.5 and seo_count >= 5:
            findings.append(Finding(
                text=(
                    f"Content mix is SEO-dominant ({seo_count} of {total_posts} "
                    f"posts are listicles). This pattern matches a top-of-funnel "
                    f"content shop or outsourced SEO supplement, often paired "
                    f"with paid acquisition rather than sales-led pipeline."
                ),
                source=SourceCitation(url=source_url, timestamp=now),
            ))

    # Thought leadership dominant
    if total_posts > 0:
        tl_count = post_counts.get("thought_leadership", 0)
        if tl_count / total_posts >= 0.5 and tl_count >= 3:
            findings.append(Finding(
                text=(
                    f"Content mix skews to thought leadership "
                    f"({tl_count} of {total_posts}). Signals enterprise positioning "
                    f"and sales-led brand-building, not a paid-acquisition motion."
                ),
                source=SourceCitation(url=source_url, timestamp=now),
            ))

    # Founder essay dominant
    if total_posts > 0:
        fe_count = post_counts.get("founder_essay", 0)
        if fe_count / total_posts >= 0.4 and fe_count >= 3:
            findings.append(Finding(
                text=(
                    f"{fe_count} of {total_posts} posts are founder essays. "
                    f"Personal-brand distribution rather than corporate content "
                    f"funnel; common in early-stage / niche-positioning plays."
                ),
                source=SourceCitation(url=source_url, timestamp=now),
            ))

    # Lead-magnet posture
    if blog_posts and not lead_magnets:
        gaps.append(
            "Blog publishing without any visible lead magnets. Content is "
            "trust-building only; conversion either happens via sales channels "
            "or pipeline does not run through email capture."
        )
        questions.append(
            "Your blog is active but we did not find any gated lead magnets. "
            "Is content meant to drive pipeline, or is it positioning-only?"
        )
    elif len(lead_magnets) >= 5:
        findings.append(Finding(
            text=(
                f"{len(lead_magnets)} lead magnets visible. Funnel-driven "
                f"email-capture motion; typically pairs with marketing-automation "
                f"in the tech stack (HubSpot / Marketo / Pardot)."
            ),
            source=SourceCitation(url=source_url, timestamp=now),
        ))

    # Podcast signal
    if podcast_platform:
        findings.append(Finding(
            text=(
                f"Podcast detected ({podcast_platform}"
                f"{f', {podcast_name}' if podcast_name else ''}). "
                f"Often signals brand-category investment and ABM-adjacent "
                f"positioning; pairs with thought leadership when both are present."
            ),
            source=SourceCitation(url=source_url, timestamp=now),
        ))

    # Newsletter signal
    if newsletter_platform == "substack":
        findings.append(Finding(
            text=(
                "Substack newsletter detected. Founder-direct distribution "
                "model rather than corporate funnel; usually a personal-brand "
                "or niche-positioning play."
            ),
            source=SourceCitation(url=source_url, timestamp=now),
        ))
    elif newsletter_platform == "embedded_form":
        findings.append(Finding(
            text=(
                "Embedded newsletter signup detected. Corporate-newsletter shape "
                "(captures email for ongoing nurture), typical of marketing-automation "
                "funnel rather than founder-direct distribution."
            ),
            source=SourceCitation(url=source_url, timestamp=now),
        ))

    return findings, gaps, questions
```

- [ ] **Step 4: Run tests + ruff**

```bash
uv run pytest tests/test_content_demand.py -v
uv run ruff check rrxray/ tests/
```

Expected: 45 tests pass (36 prior + 9 new).

- [ ] **Step 5: Commit**

```bash
git add rrxray/collectors/content_demand.py tests/test_content_demand.py tests/fixtures/synthetic/content_demand/blog_dormant.html tests/fixtures/synthetic/content_demand/blog_seo_dominant.html
git commit -m "Add post-count aggregation and rule-based content_demand findings"
```

---

## Task 11: `collect()` orchestration + `_write_evidence()`

**Model:** Opus 4.7 (logic).

**Files:**
- Modify: `rrxray/collectors/content_demand.py` (append `_write_evidence`, `collect`)
- Modify: `tests/test_content_demand.py` (append integration tests)

- [ ] **Step 1: Append failing tests**

```python
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
```

- [ ] **Step 2: Append implementation to `rrxray/collectors/content_demand.py`**

```python
import json  # noqa: E402
from pathlib import Path  # noqa: E402

from rrxray.schemas.content_demand import ContentDemandData  # noqa: E402


def _write_evidence(
    evidence_dir: Path,
    homepage_html: str,
    blog_html: str | None,
    lead_magnets: list[LeadMagnet],
    podcast: tuple[str | None, str | None],
    newsletter: tuple[str | None, str | None],
    blog_posts: list[BlogPost],
    post_counts: dict[str, int],
    most_recent_date: str | None,
) -> None:
    """Write raw HTML + structured summary to the evidence dir."""
    evidence_dir.mkdir(parents=True, exist_ok=True)
    # Clean stale evidence from prior runs
    for stale in evidence_dir.glob("*.html"):
        stale.unlink()
    for stale in evidence_dir.glob("*.json"):
        stale.unlink()

    if homepage_html:
        (evidence_dir / "homepage.html").write_text(homepage_html, encoding="utf-8")
    if blog_html:
        (evidence_dir / "blog.html").write_text(blog_html, encoding="utf-8")
    (evidence_dir / "lead_magnets.json").write_text(
        json.dumps([m.model_dump() for m in lead_magnets], indent=2),
        encoding="utf-8",
    )
    summary = {
        "blog_posts": [p.model_dump() for p in blog_posts],
        "post_counts_by_category": post_counts,
        "most_recent_post_date": most_recent_date,
        "podcast_platform": podcast[0],
        "podcast_name": podcast[1],
        "newsletter_platform": newsletter[0],
        "newsletter_archive_url": newsletter[1],
    }
    (evidence_dir / "content_demand_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8",
    )


async def collect(ctx) -> ContentDemandData:
    """Scrape homepage + blog, run categorization + detection, emit findings."""
    from rrxray.services.firecrawl_client import FirecrawlError

    now = datetime.now(UTC)
    homepage_url = f"https://{ctx.domain}"

    # Homepage scrape (best-effort; needed for podcast/newsletter detection)
    homepage_html = ""
    try:
        homepage_page = await ctx.firecrawl.scrape_url(homepage_url, only_main_content=False)
        homepage_html = (homepage_page.html or "") if homepage_page else ""
    except FirecrawlError as e:
        log.warning("homepage scrape failed for %s: %s", homepage_url, e)

    # Blog discovery + scrape (best-effort)
    blog_url, blog_page = await _discover_blog_url(ctx)
    blog_html = (blog_page.html if blog_page else "") or ""

    # Parse + categorize blog posts
    blog_posts: list[BlogPost] = []
    if blog_html:
        parsed = _parse_blog_posts(blog_html, base_url=blog_url or homepage_url)
        for p in parsed:
            category, matched = _categorize_post(p.title, "")
            blog_posts.append(BlogPost(
                title=p.title,
                url=p.url,
                author=p.author,
                published_date=p.published_date,
                category=category,  # type: ignore[arg-type]
                matched_keyword=matched,
            ))

    # Lead magnet detection (homepage + blog index combined; capped to 10)
    homepage_magnets = _detect_lead_magnets(homepage_html, source_page="homepage")
    blog_magnets = _detect_lead_magnets(blog_html, source_page="blog_index")
    lead_magnets: list[LeadMagnet] = []
    seen_keys: set[str] = set()
    for lm in homepage_magnets + blog_magnets:
        key = lm.url or lm.title.lower()
        if key in seen_keys:
            continue
        seen_keys.add(key)
        lead_magnets.append(lm)
        if len(lead_magnets) >= 10:
            break

    # Podcast + newsletter (homepage only)
    podcast = _detect_podcast(homepage_html)
    newsletter = _detect_newsletter(homepage_html)

    # Aggregate
    post_counts, most_recent_date = _compute_post_counts(blog_posts)

    # Findings
    findings, gaps, questions = _emit_findings(
        domain=ctx.domain,
        blog_index_url=blog_url,
        blog_posts=blog_posts,
        post_counts=post_counts,
        most_recent_date=most_recent_date,
        lead_magnets=lead_magnets,
        podcast=podcast,
        newsletter=newsletter,
    )

    # Evidence
    _write_evidence(
        ctx.evidence_dir / NAME,
        homepage_html,
        blog_html if blog_html else None,
        lead_magnets,
        podcast,
        newsletter,
        blog_posts,
        post_counts,
        most_recent_date,
    )

    # Source citations
    sources = []
    if blog_url:
        sources.append(SourceCitation(
            url=blog_url, timestamp=now,
            evidence_path=str(
                (ctx.evidence_dir / NAME / "blog.html").relative_to(ctx.evidence_dir)
            ) if blog_html else None,
        ))
    if homepage_html:
        sources.append(SourceCitation(
            url=homepage_url, timestamp=now,
            evidence_path=str(
                (ctx.evidence_dir / NAME / "homepage.html").relative_to(ctx.evidence_dir)
            ),
        ))

    return ContentDemandData(
        blog_index_url=blog_url,
        blog_posts=blog_posts,
        post_counts_by_category=post_counts,
        most_recent_post_date=most_recent_date,
        lead_magnets=lead_magnets,
        podcast_platform=podcast[0],  # type: ignore[arg-type]
        podcast_name=podcast[1],
        newsletter_platform=newsletter[0],  # type: ignore[arg-type]
        newsletter_archive_url=newsletter[1],
        findings=findings,
        gaps=gaps,
        discovery_questions=questions,
        sources=sources,
    )
```

- [ ] **Step 3: Run tests + full suite + ruff**

```bash
uv run pytest tests/test_content_demand.py -v
uv run pytest -v 2>&1 | tail -3
uv run ruff check rrxray/ tests/
```

Expected: 52 tests pass in `test_content_demand.py` (45 prior + 7 new). Full suite green.

- [ ] **Step 4: Commit**

```bash
git add rrxray/collectors/content_demand.py tests/test_content_demand.py
git commit -m "Wire content_demand collect() with evidence + graceful error handling"
```

---

## Task 12: Renderer partial + report template include + render tests

**Model:** Haiku 4.5 (mechanical).

**Files:**
- Create: `templates/_content_demand_detail.md.jinja`
- Modify: `templates/report_internal.md.jinja` (include the new partial)
- Modify: `tests/test_render_internal.py` (append render tests)

- [ ] **Step 1: Append failing tests to `tests/test_render_internal.py`**

```python
def test_content_demand_module_detail_renders_with_posts():
    from rrxray.schemas.content_demand import BlogPost, ContentDemandData, LeadMagnet

    cd = ContentDemandData(
        blog_index_url="https://example.com/blog",
        blog_posts=[
            BlogPost(title="The Future of Revenue", category="thought_leadership",
                     published_date="2026-04-15"),
            BlogPost(title="10 ways to close more deals", category="seo_listicle"),
        ],
        post_counts_by_category={"thought_leadership": 1, "seo_listicle": 1},
        most_recent_post_date="2026-04-15",
        lead_magnets=[
            LeadMagnet(title="The 2026 Playbook", asset_type="ebook",
                       source_page="homepage", has_form_gate=True),
        ],
        podcast_platform="apple_podcasts",
        podcast_name="The Revenue Show",
        newsletter_platform="substack",
        newsletter_archive_url="https://example.substack.com",
    )
    data = make_data()
    data.collectors.content_demand = cd
    out = render_internal(data, Anonymizer(), VoicePostProcessor())
    assert "### Content Demand" in out
    assert "The Future of Revenue" in out
    assert "The 2026 Playbook" in out
    assert "apple_podcasts" in out
    assert "substack" in out


def test_content_demand_module_detail_omits_when_no_collector():
    data = make_data()
    out = render_internal(data, Anonymizer(), VoicePostProcessor())
    assert "### Content Demand" not in out
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_render_internal.py -v -k content_demand
```

Expected: 2 new tests fail.

- [ ] **Step 3: Create `templates/_content_demand_detail.md.jinja`**

```jinja
{% set cd = data.collectors.content_demand %}
**Blog index:** {{ cd.blog_index_url or "not found" }}
**Total recent posts captured:** {{ cd.blog_posts | length }}
**Most recent post date:** {{ cd.most_recent_post_date or "unknown" }}

{% if cd.post_counts_by_category %}
| Category | Count |
|---|---|
{% for category, count in cd.post_counts_by_category.items() %}
| {{ category }} | {{ count }} |
{% endfor %}
{% endif %}

{% if cd.blog_posts %}
**Recent posts:**

{% for post in cd.blog_posts[:15] %}
- [{{ post.category }}] {{ post.title | voice_collector }}{% if post.author %} (by {{ post.author }}){% endif %}{% if post.published_date %} ({{ post.published_date }}){% endif %}
{% endfor %}
{% endif %}

**Lead magnets:** {{ cd.lead_magnets | length }}
{% if cd.lead_magnets %}
{% for lm in cd.lead_magnets[:10] %}
- [{{ lm.asset_type }}{% if lm.has_form_gate %}, gated{% endif %}] {{ lm.title | voice_collector }} (source: {{ lm.source_page }})
{% endfor %}
{% endif %}

**Podcast:** {{ cd.podcast_platform or "not detected" }}{% if cd.podcast_name %} ({{ cd.podcast_name }}){% endif %}
**Newsletter:** {{ cd.newsletter_platform or "not detected" }}{% if cd.newsletter_archive_url %} ({{ cd.newsletter_archive_url }}){% endif %}

{% if cd.findings %}
**Findings:**

{% for f in cd.findings %}
- {{ f.text | voice_collector }} *(source: [{{ f.source.url }}]({{ f.source.url }}))*
{% endfor %}
{% endif %}

{% if cd.gaps %}
**Gaps:**
{% for g in cd.gaps %}
→ {{ g | voice_collector }}
{% endfor %}
{% endif %}

{% if cd.discovery_questions %}
**Discovery questions:**
{% for q in cd.discovery_questions %}
- {{ q }}
{% endfor %}
{% endif %}
```

- [ ] **Step 4: Modify `templates/report_internal.md.jinja`**

Find the Module Detail Appendix section. After the Revenue Motion conditional block and before the Leadership Stability block, add:

```jinja
{% if data.collectors.content_demand %}
### Content Demand

{% include "_content_demand_detail.md.jinja" %}
{% endif %}
```

- [ ] **Step 5: Run tests + ruff**

```bash
uv run pytest tests/test_render_internal.py -v
uv run ruff check rrxray/ tests/
```

Expected: 2 new render tests pass; all existing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add templates/_content_demand_detail.md.jinja templates/report_internal.md.jinja tests/test_render_internal.py
git commit -m "Add Content Demand subsection to Module Detail Appendix"
```

---

## Task 13: Synthesizer prompt + body update

**Model:** Opus 4.7 (logic + taste).

**Files:**
- Modify: `rrxray/synthesizers/observed_gtm_motion.py` (read content_demand + pass to prompt; extend skip-when-all-absent check)
- Modify: `rrxray/prompts/observed_gtm_motion.md` (add fourth conditional block + framework guidance bullets)
- Modify: `tests/test_synthesizer_observed_gtm_motion.py` (append four-collector test)

- [ ] **Step 1: Append failing test to `tests/test_synthesizer_observed_gtm_motion.py`**

```python
def test_synth_runs_with_four_collectors():
    """When all four Section A collectors are present, all four blocks render in the user message."""
    from rrxray.schemas.content_demand import BlogPost, ContentDemandData, LeadMagnet
    from rrxray.schemas.revenue_motion import JobPosting, RevenueMotionData

    pricing = PricingPackagingData(
        has_public_pricing=True, is_contact_us_gated=False,
        current_pricing_url="https://example.com/pricing",
        current_tiers=[PricingTier(name="Pro", price="$50", cadence="month")],
    )
    tech = TechStackData(
        detected_tools=[DetectedTool(
            name="HubSpot", category="marketing_automation", confidence="high",
            signature_id="hubspot:strict_js", matched_text="x",
        )],
        categories_observed=["marketing_automation"],
        categories_absent=["analytics", "tag_manager", "chat", "product_analytics",
                           "crm", "cdp", "ab_testing", "attribution"],
    )
    rm = RevenueMotionData(
        careers_page_url="https://example.com/careers",
        ats_platform="lever",
        open_roles=[
            JobPosting(title="Senior AE", category="ae", source="company_careers"),
        ],
        role_counts={"ae": 1},
    )
    cd = ContentDemandData(
        blog_index_url="https://example.com/blog",
        blog_posts=[BlogPost(title="The Future of Revenue", category="thought_leadership")],
        post_counts_by_category={"thought_leadership": 1},
        most_recent_post_date="2026-04-15",
        lead_magnets=[LeadMagnet(title="The Playbook", asset_type="ebook",
                                 source_page="homepage", has_form_gate=True)],
        podcast_platform="apple_podcasts",
        podcast_name="The Revenue Show",
        newsletter_platform="substack",
    )

    fake_anthropic = MagicMock()
    fake_anthropic.complete_with_cached_system = AsyncMock(
        return_value=make_anthropic_response(
            ["Four-signal narrative."],
            ["Multi-signal observation"],
        ),
    )
    config = MagicMock(domain="example.com", model="claude-sonnet-4-6")
    config.evidence_dir = MagicMock()
    ctx = SynthesizerContext(
        collector_outputs=CollectorOutputs(
            pricing_packaging=pricing,
            tech_stack=tech,
            revenue_motion=rm,
            content_demand=cd,
        ),
        anthropic=fake_anthropic,
        voice=VoicePostProcessor(),
        anonymizer=Anonymizer(),
        config=config,
    )

    result = asyncio.run(observed_gtm_motion.synthesize(ctx))
    assert result is not None
    user_msg = ctx.anthropic.complete_with_cached_system.call_args.kwargs["user_message"]
    assert "Pricing & Packaging signal" in user_msg
    assert "Tech Stack signal" in user_msg
    assert "Revenue Motion signal" in user_msg
    assert "Content Demand signal" in user_msg
    assert "The Future of Revenue" in user_msg
    assert "apple_podcasts" in user_msg
    assert "substack" in user_msg


def test_synth_skips_when_all_four_collectors_absent():
    """If all four Section A collectors are None, synthesizer returns None."""
    fake_anthropic = MagicMock()
    config = MagicMock(domain="example.com", model="claude-sonnet-4-6")
    config.evidence_dir = MagicMock()
    ctx = SynthesizerContext(
        collector_outputs=CollectorOutputs(),
        anthropic=fake_anthropic,
        voice=VoicePostProcessor(),
        anonymizer=Anonymizer(),
        config=config,
    )
    result = asyncio.run(observed_gtm_motion.synthesize(ctx))
    assert result is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_synthesizer_observed_gtm_motion.py -v -k four_collectors
```

Expected: fails because the prompt template has no "Content Demand signal" block yet.

- [ ] **Step 3: Modify `rrxray/synthesizers/observed_gtm_motion.py`**

Update the `synthesize()` function to read `content_demand` from collector outputs, extend the skip-when-all-absent check, and pass through to the renderer:

```python
async def synthesize(ctx: SynthesizerContext) -> ObservedGtmMotionNarrative | None:
    pricing = ctx.collector_outputs.pricing_packaging
    tech_stack = ctx.collector_outputs.tech_stack
    revenue_motion = ctx.collector_outputs.revenue_motion
    content_demand = ctx.collector_outputs.content_demand    # NEW

    # Skip only when ALL Section A collectors absent
    if (
        pricing is None
        and tech_stack is None
        and revenue_motion is None
        and content_demand is None
    ):
        log.info("All Section A collectors absent; skipping observed_gtm_motion synthesis")
        return None

    # Read raw page excerpts from evidence (truncated to keep prompt size sane)
    raw_pricing_text = (
        _read_evidence_text(ctx, "pricing_packaging/current.md", max_chars=3000)
        if pricing
        else ""
    )
    raw_homepage_text = (
        _read_evidence_text(ctx, "tech_stack/homepage.html", max_chars=3000)
        if tech_stack
        else ""
    )

    system_prompt = _load_system_prompt()
    user_message = _render_user_message(
        ctx.config.domain,
        pricing,
        tech_stack,
        revenue_motion=revenue_motion,
        content_demand=content_demand,    # NEW
        raw_pricing_text=raw_pricing_text,
        raw_homepage_text=raw_homepage_text,
    )

    # ... rest unchanged ...
```

Update `_render_user_message` to accept `content_demand`:

```python
def _render_user_message(
    domain: str,
    pricing,
    tech_stack,
    revenue_motion=None,
    content_demand=None,    # NEW
    raw_pricing_text: str = "",
    raw_homepage_text: str = "",
) -> str:
    """Render the Section A user message.

    All four Section A collector outputs are optional. The Jinja template
    renders a conditional block per signal: full data when present, "not
    collected" fallback when None.
    """
    template_text = files("rrxray.prompts").joinpath("observed_gtm_motion.md").read_text()
    env = Environment(trim_blocks=True, lstrip_blocks=True)
    return env.from_string(template_text).render(
        domain=domain,
        pricing=pricing,
        tech_stack=tech_stack,
        revenue_motion=revenue_motion,
        content_demand=content_demand,    # NEW
        raw_pricing_text=raw_pricing_text,
        raw_homepage_text=raw_homepage_text,
    )
```

- [ ] **Step 4: Modify `rrxray/prompts/observed_gtm_motion.md`**

Find the framework guidance section. After the existing "Revenue motion (hiring shape) tells you" subsection, add:

```markdown
**Content posture (content_demand) tells you:**

- Heavy thought leadership = enterprise positioning, sales-led brand-building
- All SEO listicles = paid-acquisition supplement, top-of-funnel content shop, often outsourced
- Founder essays dominant = personal-brand strategy, niche positioning, often early-stage
- Many lead magnets = funnel-driven email-capture motion (typically pairs with HubSpot/Marketo stack)
- 0 lead magnets despite blog = trust-building only, conversion happens elsewhere or not at all
- Stale blog (>90 days) = content function de-prioritized; check pivot vs. defund
- Podcast + heavy thought leadership = brand-category investment, ABM-adjacent positioning
- Newsletter (especially Substack) = founder-direct distribution, not corporate funnel
- No detectable content = relationship-led GTM; pipeline does not run through content channels
```

After the Revenue Motion signal block (and before any "Raw pricing page excerpt"), add the fourth conditional block:

```jinja
{% if content_demand %}
**Content Demand signal**

- Blog index: {{ content_demand.blog_index_url or "not found" }}
- Total recent posts captured: {{ content_demand.blog_posts | length }}
- Most recent post date: {{ content_demand.most_recent_post_date or "unknown" }}

Post counts by category:
{% for category, count in content_demand.post_counts_by_category.items() %}
- {{ category }}: {{ count }}
{% endfor %}

Specific recent posts:
{% for post in content_demand.blog_posts[:10] %}
- [{{ post.category }}] {{ post.title }}{% if post.author %} (by {{ post.author }}){% endif %}{% if post.published_date %} ({{ post.published_date }}){% endif %}
{% endfor %}

Lead magnets visible: {{ content_demand.lead_magnets | length }}
{% for lm in content_demand.lead_magnets[:5] %}
- [{{ lm.asset_type }}{% if lm.has_form_gate %}, gated{% endif %}] {{ lm.title }}
{% endfor %}

Podcast: {{ content_demand.podcast_platform or "not detected" }}{% if content_demand.podcast_name %} ({{ content_demand.podcast_name }}){% endif %}
Newsletter: {{ content_demand.newsletter_platform or "not detected" }}

Findings from the collector:
{% if content_demand.findings %}
{% for f in content_demand.findings %}
- {{ f.text }}
{% endfor %}
{% else %}
(none)
{% endif %}
{% else %}
**Content Demand signal:** not collected.
{% endif %}
```

- [ ] **Step 5: Run tests + ruff**

```bash
uv run pytest tests/test_synthesizer_observed_gtm_motion.py -v
uv run ruff check rrxray/ tests/
```

Expected: all synthesizer tests pass including `test_synth_runs_with_four_collectors` and `test_synth_skips_when_all_four_collectors_absent`.

- [ ] **Step 6: Commit**

```bash
git add rrxray/synthesizers/observed_gtm_motion.py rrxray/prompts/observed_gtm_motion.md tests/test_synthesizer_observed_gtm_motion.py
git commit -m "Wire Section A synthesizer to read content_demand as fourth signal

Adds Content Demand conditional block to the prompt template and framework
guidance for content-posture interpretation. Synthesizer body adds one line
to read content_demand from collector_outputs and extends the
skip-when-all-absent check to four collectors."
```

---

## Task 14: Pipeline registration + four-collector regression test

**Model:** Haiku 4.5 (mechanical).

**Files:**
- Modify: `rrxray/pipeline.py` (append `content_demand` to imports + COLLECTORS)
- Modify: `tests/test_pipeline_graceful_degradation.py` (one new regression test)

- [ ] **Step 1: Append regression test to `tests/test_pipeline_graceful_degradation.py`**

```python
def test_pipeline_runs_with_four_section_a_collectors(tmp_path, monkeypatch):
    """Pipeline orchestrator passes all four Section A collectors into the synthesizer context."""
    from rrxray.schemas.content_demand import BlogPost, ContentDemandData
    from rrxray.schemas.revenue_motion import JobPosting, RevenueMotionData
    from rrxray.schemas.tech_stack import DetectedTool, TechStackData

    config = fake_config(tmp_path)

    fake_pricing = MagicMock()
    fake_pricing.NAME = "pricing_packaging"
    async def pricing_collect(ctx):
        from rrxray.schemas.pricing_packaging import PricingPackagingData
        return PricingPackagingData(
            has_public_pricing=True, is_contact_us_gated=False,
            current_pricing_url="https://example.com/pricing",
        )
    fake_pricing.collect = pricing_collect

    fake_tech_stack = MagicMock()
    fake_tech_stack.NAME = "tech_stack"
    async def tech_collect(ctx):
        return TechStackData(
            detected_tools=[DetectedTool(
                name="HubSpot", category="marketing_automation", confidence="high",
                signature_id="hubspot:strict_js", matched_text="x",
            )],
            categories_observed=["marketing_automation"],
            categories_absent=["analytics", "tag_manager", "chat", "product_analytics",
                               "crm", "cdp", "ab_testing", "attribution"],
        )
    fake_tech_stack.collect = tech_collect

    fake_revenue_motion = MagicMock()
    fake_revenue_motion.NAME = "revenue_motion"
    async def rm_collect(ctx):
        return RevenueMotionData(
            careers_page_url="https://example.com/careers",
            open_roles=[JobPosting(title="AE", category="ae", source="company_careers")],
            role_counts={"ae": 1},
        )
    fake_revenue_motion.collect = rm_collect

    fake_content_demand = MagicMock()
    fake_content_demand.NAME = "content_demand"
    async def cd_collect(ctx):
        return ContentDemandData(
            blog_index_url="https://example.com/blog",
            blog_posts=[BlogPost(title="The Future of X", category="thought_leadership")],
            post_counts_by_category={"thought_leadership": 1},
        )
    fake_content_demand.collect = cd_collect

    fake_synth = MagicMock()
    fake_synth.NAME = "observed_gtm_motion"

    captured_ctx = {}
    async def synth_capture(ctx):
        captured_ctx["pricing"] = ctx.collector_outputs.pricing_packaging
        captured_ctx["tech_stack"] = ctx.collector_outputs.tech_stack
        captured_ctx["revenue_motion"] = ctx.collector_outputs.revenue_motion
        captured_ctx["content_demand"] = ctx.collector_outputs.content_demand
        return None
    fake_synth.synthesize = synth_capture

    monkeypatch.setattr(
        pipeline, "COLLECTORS",
        [fake_pricing, fake_tech_stack, fake_revenue_motion, fake_content_demand],
    )
    monkeypatch.setattr(pipeline, "SYNTHESIZERS", [fake_synth])
    monkeypatch.setattr(pipeline, "build_collector_context", lambda c: MagicMock())
    monkeypatch.setattr(
        pipeline, "build_synthesizer_context",
        lambda c, o, v, a: MagicMock(collector_outputs=o, voice=v, anonymizer=a, config=c),
    )

    asyncio.run(pipeline.run_pipeline(config))
    assert captured_ctx["pricing"] is not None
    assert captured_ctx["tech_stack"] is not None
    assert captured_ctx["revenue_motion"] is not None
    assert captured_ctx["content_demand"] is not None
    assert captured_ctx["content_demand"].blog_posts[0].title == "The Future of X"
```

- [ ] **Step 2: Modify `rrxray/pipeline.py`**

Update the import block and the `COLLECTORS` list (insert `content_demand` after `revenue_motion`, before `leadership_stability`):

```python
from rrxray.collectors import (
    content_demand,
    leadership_stability,
    pricing_packaging,
    revenue_motion,
    tech_stack,
)
```

```python
COLLECTORS = [
    pricing_packaging,
    tech_stack,
    revenue_motion,
    content_demand,
    leadership_stability,
]
```

- [ ] **Step 3: Run full test suite + ruff**

```bash
uv run pytest -v 2>&1 | tail -10
uv run ruff check rrxray/ tests/
```

Expected: all tests pass (full suite around 440 passed). Ruff clean.

- [ ] **Step 4: Commit**

```bash
git add rrxray/pipeline.py tests/test_pipeline_graceful_degradation.py
git commit -m "Register content_demand in pipeline COLLECTORS list"
```

---

## Quality gate (Dale-led, manual)

Not a checkbox task. After all 14 coded tasks pass tests + ruff + commits, run the 3-domain smoke and hand the rendered Section A to Dale for review. Iterate the prompt only; do not redesign the collector.

```bash
unset ANTHROPIC_API_KEY FIRECRAWL_API_KEY
uv run rrxray run --domain swayable.com --no-cache 2>&1 | tail -3
uv run rrxray run --domain healthicity.com --no-cache 2>&1 | tail -3
uv run rrxray run --domain linear.app --no-cache 2>&1 | tail -3
```

Extract Section A from each rendered report:

```bash
for d in swayable-com healthicity-com linear-app; do
  echo "================================================================"
  echo "=== $d Section A (with content_demand) ==="
  echo "================================================================"
  awk '/## 2\. Section A/,/## 3\./' /Users/dalezwizinski/Documents/Apps/rrxray/xray-$d-*/report.internal.md
done
```

Quality bar (per the spec's refreshed decision):

- Swayable + Healthicity (RR target ICP sign-off bar): Section A must integrate content_demand into the cross-signal narrative diagnostically. Discovery questions should reference observed posture (e.g., founder-essay-heavy, podcast presence, dormant blog) rather than be boilerplate.
- Linear (regression check for PLG / dense-content shape): content_demand should NOT regress narrative quality even though Linear's content surface is rich.

Iteration loop:

1. Dale flags issues (boilerplate phrasing, missed cross-signal reasoning, voice violations).
2. Edit `rrxray/prompts/observed_gtm_motion.md` only.
3. Re-run smoke against the affected domain.
4. Present revised Section A.
5. Repeat until Dale signs off.

Commit each prompt iteration separately:

```bash
git add rrxray/prompts/observed_gtm_motion.md
git commit -m "Tune Section A prompt for content_demand integration: <one-line description>"
```

After sign-off, write `docs/checkpoints/2026-05-13-phase-2.1d-content-demand-checkpoint.md` per the mandatory-checkpoint rule in `CLAUDE.md`.

---

## Self-Review

### Spec coverage check

| Spec section | Plan task |
|---|---|
| BlogPost / LeadMagnet / ContentDemandData schemas | T1 |
| CollectorOutputs.content_demand field + import + model_rebuild | T2 |
| Content-category catalog (8 categories) + lead-magnet / podcast / newsletter patterns | T3 |
| Blog page discovery (6 candidate paths) | T4 |
| Blog index parsing (15 posts, anchor + time + best-effort author/date) | T5 |
| Content categorization (catalog + SEO listicle regex) | T6 |
| Lead-magnet detection (CTA + form-near + asset-type, cap 10) | T7 |
| Podcast detection (RSS head + Apple/Spotify regex) | T8 |
| Newsletter detection (Substack regex + embedded-form heuristic) | T9 |
| Rule-based findings emission (no LLM in collector path) | T10 |
| `_compute_post_counts` with most-recent date | T10 |
| Evidence writing | T11 |
| `collect()` orchestration with graceful failure (no blog / homepage fail / blog fail / total failure) | T11 |
| Module Detail Appendix Content Demand subsection | T12 |
| Synthesizer prompt fourth conditional block + framework guidance | T13 |
| Synthesizer body reads content_demand + extended skip check | T13 |
| Synthesizer test for four-collector path | T13 |
| Pipeline registration | T14 |
| Pipeline regression test for four collectors | T14 |
| Live smoke + Dale-led quality gate | Quality gate section |

### Acceptance criteria coverage

| AC | Plan location |
|---|---|
| #1 collector registered in `pipeline.COLLECTORS` | T14 |
| #2 catalog has 8 categories with >=3 keywords each | T3 |
| #3 blog discovery handles 6 candidate paths | T4 |
| #4 post categorization correct against 8-category catalog | T6 |
| #5 lead-magnet detection (CTA + form-near + asset-type) | T7 |
| #6 podcast detection (Apple, Spotify, RSS-only) | T8 |
| #7 newsletter detection (Substack + embedded form) | T9 |
| #8 rule-based findings | T10 |
| #9 evidence files with correct relative paths | T11 |
| #10 data.json round-trips with content_demand populated | T2 |
| #11 Module Detail Appendix renders Content Demand subsection | T12 |
| #12 synthesizer reads content_demand from collector_outputs | T13 |
| #13 live smoke against Swayable + Healthicity + Linear | Quality gate |
| #14 quality gate signed off by Dale | Quality gate |

### Type / signature consistency check

- `_discover_blog_url(ctx) -> tuple[str | None, ScrapedPage | None]` defined T4, used T11
- `_parse_blog_posts(html, base_url) -> list[BlogPost]` defined T5, used T11
- `_categorize_post(title, description) -> tuple[str, str | None]` defined T6, used T11
- `_detect_lead_magnets(html, source_page) -> list[LeadMagnet]` defined T7, used T11
- `_detect_podcast(homepage_html) -> tuple[str | None, str | None]` defined T8, used T11
- `_detect_newsletter(homepage_html) -> tuple[str | None, str | None]` defined T9, used T11
- `_compute_post_counts(blog_posts) -> tuple[dict[str, int], str | None]` defined T10, used T11
- `_emit_findings(domain, blog_index_url, blog_posts, post_counts, most_recent_date, lead_magnets, podcast, newsletter)` defined T10, used T11
- `_write_evidence(evidence_dir, homepage_html, blog_html, lead_magnets, podcast, newsletter, blog_posts, post_counts, most_recent_date)` defined T11
- `collect(ctx) -> ContentDemandData` defined T11, used T14
- `ContentDemandData`, `BlogPost`, `LeadMagnet` defined T1, used everywhere downstream
- `ContentCategory`, `LeadMagnetAssetType` Literals defined T1, used T6, T7

### Placeholder scan

Searched for: TBD, TODO, "implement later", "fill in", "add appropriate", "similar to Task". None found.

---

## Risks and known limitations

- **Blog parsing heterogeneity.** WordPress, Ghost, Webflow, Notion-as-blog, Medium-hosted, custom Next.js all use different HTML conventions. Anchor extraction is reliable; date and author extraction is best-effort and will fail silently on some platforms. Mitigation: smoke against three different blog platforms during the quality gate.
- **Lead-magnet CTA-text heuristic will miss some.** Icon-only or generic "Download" buttons won't match. Mitigation: cap is 10 per domain; the diagnostic question is "are they running a funnel?", not exact count.
- **Podcast detection misses self-hosted RSS without standard `<link rel>`.** Defer richer detection to a future Phase 2.1d-deep cycle.
- **Newsletter embedded-form heuristic will produce false positives.** Any site with a footer email signup that happens to use "subscribe" wording will trigger it. Mitigation: require the keyword in the button text or nearby heading; accept residual false positives as "newsletter-shaped intent."
- **Blog parsing may capture nav links.** Mitigated by a small skip-list of common nav titles; same noise tolerance as Phase 2.1c careers parsing.
- **Date format variance.** Best-effort regex; on failure, `published_date=None` and `most_recent_post_date` reflects whichever date IS parseable.
- **Cost.** Two Firecrawl scrapes per domain (homepage + blog index); no LinkedIn searches in this collector. Cheaper than Phase 2.1c.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-13-rrxray-phase-2.1d-content-demand.md`. Two execution options:

**1. Subagent-Driven (recommended)** - fresh subagent per task, two-stage review for T1-T13, then T14 stops to ask Dale for the quality read.

**2. Inline Execution** - `superpowers:executing-plans` with batch checkpoints.

Which approach?
