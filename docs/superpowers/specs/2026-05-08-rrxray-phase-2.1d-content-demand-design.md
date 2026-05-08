# rrxray Phase 2.1d: content_demand Collector Design

**Date:** 2026-05-08
**Status:** Approved (brainstorming complete)
**Phase:** 2.1d (fourth sub-phase inside Phase 2; closes Section A)
**Builds on:** Phase 2.1c `revenue_motion` collector (commit `97e1d1c`) merged into `main` (commit `de297bf`)

---

## Context

Phase 2.1c shipped the third Section A signal (`revenue_motion`). The synthesizer now reads pricing + tech stack + hiring shape and produces a diagnostic narrative that integrates all three (validated on Swayable, SQA Services, Linear during the Phase 2.1c quality gate). Phase 2.1d adds the fourth and final Section A signal: `content_demand`. After this phase, Section A draws on a complete read of the prospect's outside-visible GTM motion.

Content posture is high-signal because it tells the diagnostic exactly what KIND of pipeline-generation strategy the company is running:

- Heavy thought leadership = enterprise positioning, sales-led brand-building
- All SEO listicles = paid-acquisition supplement, top-of-funnel content shop, often outsourced
- Founder essays dominant = personal-brand strategy, niche positioning, often early-stage
- Lead-magnet-heavy = funnel-driven email-capture motion (typically pairs with HubSpot/Marketo stack)
- 0 lead magnets despite blog = trust-building only, conversion happens elsewhere or not at all
- Podcast + heavy thought leadership = brand-category investment, ABM-adjacent positioning
- Substack newsletter = founder-direct distribution rather than corporate funnel
- No detectable content = relationship-led GTM; pipeline does not run through content channels

This phase is structurally identical to Phase 2.1c: new collector module, new schema, new catalog, new renderer partial, fourth conditional block on the Section A synthesizer prompt, one-line additions to `pipeline.COLLECTORS` and `CollectorOutputs`. No new shared services. Cheaper than Phase 2.1c per live run (2 Firecrawl scrapes per domain, no LinkedIn searches, no Wayback).

---

## Scope

### In scope

- New collector module `rrxray/collectors/content_demand.py` plus content-category catalog `rrxray/collectors/_content_demand_catalog.py`
- New schema module `rrxray/schemas/content_demand.py` with `BlogPost`, `LeadMagnet`, `ContentDemandData`
- Blog page discovery (try `/blog`, `/insights`, `/resources`, `/news`, `/articles`, `/learn`)
- Blog index parsing for the most recent 15 posts: title + author + published_date + URL + category
- Content categorization via 8-category keyword catalog (`thought_leadership`, `seo_listicle`, `case_study`, `product_announcement`, `founder_essay`, `tutorial`, `news_pr`, `other`)
- Lead-magnet detection on homepage + blog index (CTA-text heuristic + form-near-CTA proximity check + asset-type inference)
- Podcast detection via `<link rel="alternate" type="application/rss+xml">` head sniff + Apple Podcasts / Spotify URL regex
- Newsletter detection via Substack subdomain regex + embedded-form heuristic
- Rule-based findings emitted from the collector (no LLM in collector path; matches Phase 1+2.1a-c pattern)
- New Jinja partial `templates/_content_demand_detail.md.jinja` for the Module Detail Appendix
- `content_demand: ContentDemandData | None = None` field added to `CollectorOutputs`
- `content_demand` module appended to `pipeline.COLLECTORS`
- Fourth conditional block in `rrxray/prompts/observed_gtm_motion.md` plus framework-guidance bullets for content-posture interpretation
- Synthesizer body updated to read `content_demand` from `collector_outputs` and pass to the prompt renderer
- Synthetic-HTML fixture tests (no live API calls in unit tests)
- Quality gate: 3-domain smoke against Swayable / SQA Services / Linear plus Dale-led prompt review

### Out of scope (future cycles)

- Wayback comparison of blog index for cadence trajectory ("burst then silence" patterns) — Phase 2.1d-deep candidate
- Per-post body parsing (sentiment, keyword density, internal-linking analysis) — Phase 2.1d-deep candidate
- Newsletter archive cadence analysis (fetching Substack archive page) — detect-only is enough for this phase
- Podcast episode count or recency (fetching RSS feed or Apple/Spotify pages) — presence is the signal
- Lead-magnet form-field analysis (counting fields, gating intensity) — detect-only is enough
- LLM-based content categorization — collector stays rule-based and deterministic
- SEO keyword extraction or search-keyword performance — Phase 2.3 `buyer_sentiment` territory
- Paid third-party APIs (BuzzSumo, SimilarWeb, etc.) — outside the standing project rule

---

## Decisions Locked During Brainstorming

| Decision | Choice | Rationale |
|---|---|---|
| Cycle scope | Blog + podcast + lead magnets + newsletter (all four content surfaces) | Dale's explicit choice; closes Section A's content signal completely |
| Blog parsing depth | Last 15 posts: title + author + date + topic category | Mirrors Phase 2.1c shape; categorization is where content-as-GTM-signal becomes diagnostic |
| Content category catalog | 8 hardcoded categories: `thought_leadership`, `seo_listicle`, `case_study`, `product_announcement`, `founder_essay`, `tutorial`, `news_pr`, `other` | Matches Phase 2.1a tech_stack and Phase 2.1c revenue_motion pattern; deterministic, no LLM in collector path |
| Schema shape | Two typed list models (`BlogPost`, `LeadMagnet`) plus flat fields for podcast and newsletter on `ContentDemandData` | Lean: podcast/newsletter are 0-or-1 per domain; typed lists with one element are overkill |
| Lead-magnet detection scope | Homepage + blog index only; do NOT follow gated CTAs | Detect-presence is enough; following landing pages adds cost without proportional signal |
| Cross-signal integration | Add fourth `{% if content_demand %}` conditional block to existing Section A prompt; one-line synthesizer body update | Mirrors Phase 2.1c integration; N-collector-agnostic refactor is wider blast radius for marginal benefit |
| Quality gate | Dale-led review against Swayable, SQA Services, Linear (same domains as Phases 2.1b/2.1c) | Apples-to-apples comparison; same domains across phases lets us isolate the marginal value of the new signal |

---

## Architecture

### File layout (changes only)

```
NEW:
  rrxray/collectors/content_demand.py             [collector entry: NAME, _discover_blog_url, _parse_blog_posts, _categorize_post, _detect_lead_magnets, _detect_podcast, _detect_newsletter, _emit_findings, _write_evidence, collect]
  rrxray/collectors/_content_demand_catalog.py    [content category catalog: 8 categories + lead-magnet asset-type keywords]
  rrxray/schemas/content_demand.py                [BlogPost, LeadMagnet, ContentDemandData]
  templates/_content_demand_detail.md.jinja       [Module Detail partial]
  tests/test_content_demand.py                    [collector tests + synthetic fixtures]
  tests/test_content_demand_catalog.py            [catalog integrity tests]
  tests/test_content_demand_schemas.py            [schema round-trip + validation]
  tests/fixtures/synthetic/content_demand/        [sample HTML fixtures]

MODIFIED:
  rrxray/schemas/data.py                          [add content_demand field on CollectorOutputs + import + model_rebuild]
  rrxray/pipeline.py                              [append content_demand to COLLECTORS]
  rrxray/prompts/observed_gtm_motion.md           [add fourth conditional block: Content Demand signal + framework guidance]
  rrxray/synthesizers/observed_gtm_motion.py      [read content_demand from collector_outputs; pass to _render_user_message; extend skip-when-all-absent check]
  tests/test_synthesizer_observed_gtm_motion.py   [add test_synth_runs_with_four_collectors]
  templates/report_internal.md.jinja              [include _content_demand_detail partial in Module Detail Appendix]
```

---

## Components

### Schema (`rrxray/schemas/content_demand.py`)

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

### Schema integration

`rrxray/schemas/data.py` adds one field to `CollectorOutputs`:

```python
class CollectorOutputs(BaseModel):
    model_config = ConfigDict(validate_assignment=True)
    pricing_packaging: "PricingPackagingData | None" = None
    tech_stack: "TechStackData | None" = None
    revenue_motion: "RevenueMotionData | None" = None
    content_demand: "ContentDemandData | None" = None    # NEW
```

Plus the bottom-of-file import and `model_rebuild()`, matching the existing pattern.

### Content-category catalog (`rrxray/collectors/_content_demand_catalog.py`)

8 categories with hardcoded keyword lists. Pattern matching is case-insensitive substring against post `title + " " + (description or "")`. Order-by-specificity (more specific patterns checked first).

```python
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
    # SEO listicles — very specific patterns. The numeric prefixes are checked
    # via a dedicated regex in addition to these substrings, since "5 ways to"
    # and "10 ways to" should both match without enumerating every integer.
    {"category": "seo_listicle", "keywords": [
        "top 10", "top 5", "top 7", "best 10", "best of",
        "the ultimate guide to", "the complete guide to",
        " ways to ", " tips for ", " mistakes to avoid",
    ]},

    # Case studies — distinct framing
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

### Collector (`rrxray/collectors/content_demand.py`)

Key functions:

- `_discover_blog_url(ctx)` — try `/blog`, `/insights`, `/resources`, `/news`, `/articles`, `/learn`. Return `(url, ScrapedPage)` or `(None, None)`. Mirrors Phase 2.1c's `_discover_careers_url` shape.
- `_parse_blog_posts(html, base_url)` — parse anchor tags + nearby `<time>` / `datetime=...` attributes; capture title, URL, author (best-effort), published_date (best-effort, ISO string). Capture **up to 15** posts (whatever is visible if fewer); take the first 15 in document order. Return `list[BlogPost]`.
- `_categorize_post(title, description)` — match against `CONTENT_KEYWORDS`. Return `(category, matched_keyword)`. Default to `("other", None)`.
- `_detect_lead_magnets(html, source_page)` — scan HTML for CTA-text patterns from `LEAD_MAGNET_CTA_PATTERNS`; for each match, run a proximity check for `<form>` with email input; infer asset_type from the matched pattern. Capture **up to 10 per domain** (across both homepage + blog index combined; deduplicate by URL or by title if URL is missing). Return `list[LeadMagnet]`.
- `_detect_podcast(homepage_html)` — sniff `<link rel="alternate" type="application/rss+xml">` plus `PODCAST_PATTERNS` regex. Return `(platform, name)` or `(None, None)`.
- `_detect_newsletter(homepage_html)` — `SUBSTACK_PATTERN` regex first; fall back to embedded-form heuristic (`<form>` with email input + button text matching `subscribe|newsletter|sign up`). Return `(platform, archive_url)` or `(None, None)`.
- `_compute_post_counts(blog_posts)` — aggregate counts per category, derive `most_recent_post_date` from the maximum parseable `published_date` across the captured posts. If no post has a parseable date, return `most_recent_post_date=None`. Return `(post_counts_by_category, most_recent_post_date)`.
- `_emit_findings(blog_posts, post_counts, most_recent, lead_magnets, podcast, newsletter)` — rule-based findings + gaps + discovery questions per Section 3 of the design.
- `_write_evidence(evidence_dir, homepage_html, blog_html, lead_magnet_data, podcast_info, newsletter_info)` — write `homepage.html`, `blog.html` (if scraped), `lead_magnets.json`, `content_demand_summary.json`.
- `async collect(ctx)` — orchestrator following the Phase 2.1c pattern.

Graceful failure: if any individual sub-step fails (no blog discovered, lead-magnet scan finds nothing, podcast/newsletter not detected), the collector continues with whatever data it has and emits findings explaining the absence.

### Synthesizer prompt update (`rrxray/prompts/observed_gtm_motion.md`)

Add a new conditional block alongside the existing pricing, tech stack, and revenue_motion blocks:

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

Add framework guidance bullets:

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

### Synthesizer body update (`rrxray/synthesizers/observed_gtm_motion.py`)

```python
async def synthesize(ctx: SynthesizerContext) -> ObservedGtmMotionNarrative | None:
    pricing = ctx.collector_outputs.pricing_packaging
    tech_stack = ctx.collector_outputs.tech_stack
    revenue_motion = ctx.collector_outputs.revenue_motion
    content_demand = ctx.collector_outputs.content_demand    # NEW

    # Skip only when ALL Section A collectors absent
    if pricing is None and tech_stack is None and revenue_motion is None and content_demand is None:
        log.info("All Section A collectors absent; skipping synthesis")
        return None

    # ... rest unchanged, but pass content_demand to _render_user_message ...
```

### Pipeline integration (`rrxray/pipeline.py`)

```python
from rrxray.collectors import (
    pricing_packaging, tech_stack, revenue_motion, content_demand,    # add content_demand
)

COLLECTORS = [pricing_packaging, tech_stack, revenue_motion, content_demand]    # append
```

### Renderer template (`templates/report_internal.md.jinja`)

Add to the Module Detail Appendix section, after the Revenue Motion block:

```jinja
{% if data.collectors.content_demand %}
### Content Demand

{% include "_content_demand_detail.md.jinja" %}
{% endif %}
```

The partial `templates/_content_demand_detail.md.jinja` renders blog post table + lead-magnet table + podcast/newsletter signals + findings/gaps/questions, matching the shape of `_revenue_motion_detail.md.jinja`.

---

## Data flow

```
CollectorContext (domain, firecrawl, evidence_dir, ...)
   ↓
content_demand.collect(ctx)
   ├─ ctx.firecrawl.scrape_url(homepage_url) → ScrapedPage          [for podcast/newsletter detection]
   ├─ _discover_blog_url(ctx) → (url, ScrapedPage) or (None, None)
   ├─ if blog_url: _parse_blog_posts(blog_html, blog_url) → list[BlogPost]
   ├─ _categorize_post(title, description) per post → fills BlogPost.category
   ├─ _detect_lead_magnets(homepage_html, "homepage") + _detect_lead_magnets(blog_html, "blog_index")
   ├─ _detect_podcast(homepage_html) → (platform, name) or (None, None)
   ├─ _detect_newsletter(homepage_html) → (platform, archive_url) or (None, None)
   ├─ _compute_post_counts(blog_posts) → counts + most_recent_date
   ├─ _emit_findings(...) → findings, gaps, discovery_questions
   ├─ _write_evidence(evidence_dir / "content_demand", ...)
   ↓
ContentDemandData (validated by pydantic)
   ↓
returned to pipeline → assigned to CollectorOutputs.content_demand
   ↓
synthesizer reads ctx.collector_outputs.content_demand
   ↓
prompt template renders the Content Demand conditional block
   ↓
LLM produces Section A narrative reading across pricing + tech_stack + revenue_motion + content_demand
```

---

## Error handling

- **No blog page found** → return `ContentDemandData(blog_index_url=None, blog_posts=[], findings=[Finding(text="No blog or insights page discovered on standard paths")])`. Synthesizer reads this gracefully via the "Content Demand signal: not collected" fallback path.
- **Homepage scrape fails** → no podcast / newsletter / homepage-lead-magnet detection. Collector continues with blog-only data if blog discovery succeeds.
- **Blog index scrape fails** → no posts captured; collector continues with homepage-only data (lead magnets / podcast / newsletter on homepage).
- **Total failure (`FirecrawlError` on homepage AND no blog reachable)** → return graceful `ContentDemandData` with findings noting both failures. No exception escapes.
- **`asyncio.CancelledError`** propagates (matches the project's standing pattern).
- **Date parsing errors** → log at debug, set `published_date=None` on that post; do not fail the whole collector.

---

## Testing

### Test files

- `tests/test_content_demand_schemas.py` — schema round-trip + validation (~6 tests)
- `tests/test_content_demand_catalog.py` — catalog integrity, all 8 categories present, keywords compile, no duplicates (~7 tests)
- `tests/test_content_demand.py` — collector behavior end-to-end with synthetic fixtures (~30 tests)
- Synthesizer test additions — `test_synth_runs_with_four_collectors`, `test_synth_runs_with_content_demand_only` (~2 tests)
- Render test additions — `test_content_demand_module_detail_renders_with_posts`, `test_content_demand_module_detail_omits_when_no_collector` (~2 tests)

**Total: ~47 new tests.** Suite goes from 251 → ~298.

### Synthetic fixtures

`tests/fixtures/synthetic/content_demand/`:

- `blog_simple.html` — blog index with 5 posts, mixed categories, dates visible
- `blog_with_lead_magnets.html` — 3 inline CTAs to gated downloads
- `homepage_with_podcast_apple.html` — Apple Podcasts link in footer
- `homepage_with_podcast_spotify.html` — Spotify link in footer
- `homepage_with_substack_newsletter.html` — Substack subdomain link
- `homepage_with_embedded_newsletter_form.html` — `<form>` newsletter signup
- `blog_dormant.html` — last post date > 90 days old (for findings rule)
- `blog_seo_dominant.html` — 12 of 15 posts categorized as `seo_listicle`
- `blog_no_dates.html` — blog index without surfacing dates (graceful-degradation fixture)

### Acceptance criteria

| # | Criterion | Verified by |
|---|---|---|
| 1 | `content_demand` collector exists and is registered in `pipeline.COLLECTORS` | `tests/test_content_demand.py::test_collector_registered` |
| 2 | Catalog has 8 categories with ≥3 keywords each | `tests/test_content_demand_catalog.py::test_catalog_*` |
| 3 | Blog discovery handles `/blog`, `/insights`, `/resources`, `/news`, `/articles`, `/learn` (with fallback) | `test_discover_blog_url_*` |
| 4 | Post categorization correct against the 8-category catalog | `test_categorize_post_*` |
| 5 | Lead magnet detection works against synthetic HTML (CTA + form-near heuristic + asset-type inference) | `test_detect_lead_magnets_*` |
| 6 | Podcast detection identifies Apple, Spotify, RSS-only | `test_detect_podcast_*` |
| 7 | Newsletter detection identifies Substack + embedded forms | `test_detect_newsletter_*` |
| 8 | Rule-based findings emit on observable patterns | `test_emit_findings_*` |
| 9 | Evidence files written with correct relative paths | `test_collect_writes_evidence` |
| 10 | `data.json` round-trips with `content_demand` populated | existing `test_data_json_round_trips` |
| 11 | Module Detail Appendix renders Content Demand subsection | `test_content_demand_module_detail_*` |
| 12 | Synthesizer reads `content_demand` from `collector_outputs` and includes it in the user message | `test_synth_runs_with_four_collectors` |
| 13 | Live smoke against Swayable / SQA / Linear produces a Section A narrative referencing content posture | manual review (Dale-led quality gate) |
| 14 | Quality gate signed off by Dale | manual review |

---

## Risks and known limitations

- **Blog parsing heterogeneity.** Blogs use wildly different HTML conventions: WordPress, Ghost, custom, Webflow, Notion-as-blog, Medium-hosted. Title extraction via anchor tags is reliable; date and author extraction is best-effort and will fail silently on some platforms. Mitigation: comprehensive smoke testing against three different blog platforms during the quality gate (Swayable likely Webflow; SQA likely WordPress; Linear likely custom Next.js).
- **Lead-magnet CTA-text heuristic will miss some.** Buttons that just say "Download" or use icon-only CTAs won't match the keyword patterns. Mitigation: cap is 10 per domain, so missing a few is acceptable; the diagnostic question is "are they running a funnel?", not "exactly how many magnets do they have?"
- **Podcast detection misses self-hosted RSS without standard `<link rel>`.** Some companies host their own RSS feed without putting a discovery link in the HTML head. Mitigation: try `/podcast` path as a fallback. Defer richer detection to Phase 2.1d-deep.
- **Newsletter embedded-form heuristic will produce false positives.** Any site with a footer email signup will trigger it. Mitigation: require button text to match `subscribe|newsletter|sign up` keywords (not just any submit button); accept the residual false positive rate as "newsletter-shaped intent" rather than "definitely a newsletter."
- **Blog "post" parsing may capture nav links.** Same issue as Phase 2.1c careers parsing (where 28 nav links got categorized as roles for SQA Services, all in `other`). The synthesizer reads `other` as itself diagnostic, so this isn't a defect — but it's a known noise source.
- **Date format variance.** Some blogs publish dates as "May 8, 2026", some as `2026-05-08`, some as `8 May 2026`, some omit dates entirely. Best-effort regex parsing; on failure, set `published_date=None` and `most_recent_post_date` to whichever date IS parseable.
- **Cost.** 2 Firecrawl scrapes per domain (homepage + blog index); cheaper than Phase 2.1c's 3-4 scrapes + 2 LinkedIn searches. The dynamic dry-run estimator (Phase 2.1c improvement) will reflect this automatically.

---

## Out of scope but accommodated by the design

- Phase 2.2's `leadership_stability` collector ships in parallel; it operates on a different signal area (Section B) and does not interact with content_demand.
- Future Phase 2.1d-deep additions (Wayback cadence trajectory, per-post body parsing) can extend `ContentDemandData` with additional fields and add separate sub-step methods to the collector without touching the schema's existing fields.
- Phase 3's Gemini integration treats `content_demand` as just another collector output. No special-case wiring.

---

## Open questions

None at this time. All material decisions are locked.
