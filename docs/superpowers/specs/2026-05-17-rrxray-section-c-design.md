# Section C: External Voice vs. Internal Voice — Design Spec

**Date:** 2026-05-17
**Phases:** 2.5a (positioning_drift), 2.5b (buyer_sentiment), 2.5c (synthesizer + render)
**Status:** Approved — proceed to implementation planning

---

## Overview

Section C answers: "Does the external market see what this company thinks it is?"

It crosses three signals:
1. **Positioning drift** — how the homepage messaging has shifted over 18 months (Wayback diffs)
2. **Buyer sentiment** — what customers and ex-reps say in public reviews (G2, Capterra, Trustpilot, Reddit, Glassdoor)
3. **Content demand** — already collected in Phase 2.1d; feeds the synthesizer directly

Currently Section C renders `[Module not available for this domain]`. After Phase 2.5c, it renders a full `external_voice_vs_internal` narrative.

---

## Architectural rules (carry-forward)

- **LLM in collector path**: `positioning_drift` is deterministic (no LLM). `buyer_sentiment` justifies LLM (Haiku 4.5) because review text is genuinely unstructured NL — implicit sentiment, role-specific framing, feature-specific callouts. Same justification as press-release extraction in Phase 2.2.
- **No new paid APIs**: all sources are free/public. G2, Capterra, Trustpilot, Reddit, Glassdoor via Firecrawl search + scrape. No Coresignal, no Review Trackers.
- **No LinkedIn profile-page scraping**: not applicable to Section C.
- **Verbatim Quarantine rule**: raw review text lives ONLY in `evidence/buyer_sentiment/raw/`. Never surfaces in schema, template, or rendered report. Schema holds extracted themes only.

---

## Phase 2.5a: `positioning_drift` collector

### Purpose

Detect messaging shift by diffing Wayback Machine homepage snapshots at 6-month intervals over 18 months.

### Data sources

- Wayback Machine snapshots of `https://<domain>/` — free, public
- Reuses `ctx.wayback.snapshots(url, interval_months=6, span_months=18)` already in the codebase (`pricing_packaging` uses it)
- Each archive URL scraped via Firecrawl to get readable markdown text

### Extraction strategy (deterministic, no LLM)

From each snapshot's markdown text:
- **Hero headline**: first H1 found; fall back to `og:title` or first non-empty line of significant length (>15 chars)
- **Sub-headline**: first paragraph after the H1 (or meta description); truncate to 300 chars
- **Primary nav**: all anchor link texts from the top 20% of document that are short (<40 chars) and alphabetically or structurally consistent with navigation

Diff oldest → newest snapshot:
- Compare hero_headline, sub_headline, primary_nav as string sets
- `changed_fields`: list of field names where values differ
- `diff_summary`: human-readable string, e.g., `"hero shifted from 'X' to 'Y'; 2 nav items added (Pricing, ROI Calculator)"`

### Schema

```python
# rrxray/schemas/positioning_drift.py

from __future__ import annotations
from datetime import date
from pydantic import BaseModel
from rrxray.schemas._shared import Finding, SourceCitation


class HomepageSnapshot(BaseModel):
    timestamp: date
    archive_url: str
    hero_headline: str | None = None
    sub_headline: str | None = None
    primary_nav: list[str] = []


class PositioningDriftData(BaseModel):
    snapshots: list[HomepageSnapshot] = []
    oldest_snapshot: HomepageSnapshot | None = None
    newest_snapshot: HomepageSnapshot | None = None
    changed_fields: list[str] = []          # ["hero_headline", "primary_nav"]
    diff_summary: str | None = None         # "hero shifted from X to Y"
    findings: list[Finding] = []
    gaps: list[str] = []
    discovery_questions: list[str] = []
    sources: list[SourceCitation] = []
```

### Evidence layout

```
evidence/positioning_drift/
  snapshot_YYYYMMDD.md       (one per Wayback snapshot; raw markdown)
  diff.json                  (changed_fields + diff_summary as JSON)
```

### Findings / gaps / questions logic (rule-based, no LLM)

- If 0 snapshots: gap "No Wayback Machine snapshots recovered; homepage messaging history not available"
- If 1 snapshot: finding "Only one historical snapshot recovered; drift assessment requires at least two data points"
- If 2+ snapshots and `changed_fields` is non-empty: finding per changed field, e.g., "Hero headline changed from X to Y over N months"
- If 2+ snapshots and `changed_fields` is empty: finding "Homepage messaging has been stable across all snapshots in the 18-month window"
- Discovery question if hero changed significantly (>50% character edit distance): "Your homepage hero shifted from X to Y over 18 months. What drove that repositioning?"

### Collector pattern

```
rrxray/collectors/positioning_drift.py
rrxray/collectors/_positioning_drift_catalog.py
```

`_positioning_drift_catalog.py` constants:
- `MIN_HEADLINE_LEN = 10` — minimum chars for a string to be considered a headline candidate
- `MAX_HEADLINE_LEN = 200` — truncate captured headline to this
- `MAX_SUBNAV_TEXT_LEN = 40` — nav items longer than this are skipped (likely paragraphs, not nav labels)
- `MAX_NAV_ITEMS = 12` — cap nav list at this many items per snapshot
- `NAV_SKIP_PATTERNS` — compiled regex list for common non-nav link texts: "Skip to content", "Login", "Sign in", "Cookie", etc.
- `HOMEPAGE_PATHS = ["/", ""]` — paths considered the homepage

`collect(ctx) -> PositioningDriftData`

Steps:
1. `_fetch_snapshots(ctx)` — calls `ctx.wayback.snapshots(homepage_url, interval_months=6, span_months=18)`. On `WaybackError`: log warning, return empty list (graceful degradation).
2. `_scrape_snapshot(firecrawl, snapshot)` — scrapes archive URL via Firecrawl; returns markdown text. On `FirecrawlError`: log warning, return None.
3. `_extract_fields(markdown_text)` — returns `(hero, sub, nav)` via regex/text parsing. Pure function, no I/O.
4. `_diff_snapshots(oldest, newest)` — compares field values; returns `(changed_fields, diff_summary)`.
5. `_emit_findings(snapshots, diff)` — rule-based; returns `(findings, gaps, questions)`.
6. `_write_evidence(evidence_dir, snapshots_markdown, diff)` — writes files.
7. `collect(ctx)` — orchestrates; returns `PositioningDriftData`.

---

## Phase 2.5b: `buyer_sentiment` collector

### Purpose

Surface what customers and ex-reps say publicly about this company in review platforms and community forums. Extract themes (not verbatims) for safe rendering.

### Data sources (all free/public)

| Platform | Signal | Method |
|---|---|---|
| G2 | Buyer reviews | `site:g2.com "<domain>"` search → scrape listing page if accessible |
| Capterra | Buyer reviews | `site:capterra.com "<company name>"` search → snippets |
| Trustpilot | Buyer reviews | `site:trustpilot.com "<domain>"` search → scrape if accessible |
| Reddit | Community discussion | `"<domain>" site:reddit.com` search → scrape thread text |
| Glassdoor | Ex-rep (AE/SDR) reviews | `site:glassdoor.com "<company>" sales` search → snippets only (login-walled) |

Platform search uses `ctx.firecrawl.search(query, limit=5)` per platform (max 25 total search calls across all platforms).

Scraping: for platforms that return accessible HTML (G2, Trustpilot), attempt a single `ctx.firecrawl.scrape_url()` on the top search result. On `FirecrawlError` (Payment Required or otherwise): fall back to snippets only.

### LLM use justification

Review text is genuinely unstructured NL: "the implementation team was disorganized but the product itself is solid" → sentiment = mixed, theme = implementation experience. Regex cannot reliably extract this. Haiku 4.5 extracts themes per review chunk. Same precedent as press-release extraction in Phase 2.2.

### Verbatim Quarantine rule

- All raw scraped text (full page HTML, thread text, snippet concatenations) writes to `evidence/buyer_sentiment/raw/<platform>.txt`
- The `BuyerSentimentData` schema holds ONLY extracted themes and metadata — no verbatim quotes
- The Jinja template partial MUST NOT render any field that could contain verbatim review text
- The `_emit_findings()` function must reference themes, not raw quotes

### Extraction (LLM, Haiku 4.5)

`ExtractedSentimentThemes` — a Pydantic schema passed to `HaikuExtractor.extract_sentiment_themes(raw_text, platform)`:

```python
class ExtractedTheme(BaseModel):
    theme: str          # short phrase: "implementation support gaps"
    sentiment: Literal["positive", "negative", "mixed"]
    evidence_count: int  # how many reviews seemed to mention this

class ExtractedSentimentThemes(BaseModel):
    themes: list[ExtractedTheme]
    review_count_estimate: int | None   # if LLM can infer from page
    platform: str
```

Haiku is called once per platform (concatenated snippets/scraped text, truncated to 4000 chars). If Haiku call fails: log warning, platform themes = [].

### Schema

```python
# rrxray/schemas/buyer_sentiment.py

from __future__ import annotations
from typing import Literal
from pydantic import BaseModel
from rrxray.schemas._shared import Finding, SourceCitation


class ReviewTheme(BaseModel):
    theme: str
    sentiment: Literal["positive", "negative", "mixed"]
    source_platforms: list[str]
    frequency: Literal["single", "repeated", "dominant"]


class BuyerSentimentData(BaseModel):
    platforms_checked: list[str] = []
    platforms_found: list[str] = []        # platforms with at least one result
    review_count_estimate: int | None = None
    themes: list[ReviewTheme] = []
    sales_rep_themes: list[ReviewTheme] = []  # Glassdoor ex-AE/SDR specific
    findings: list[Finding] = []
    gaps: list[str] = []
    discovery_questions: list[str] = []
    sources: list[SourceCitation] = []
```

### Findings / gaps / questions logic (rule-based, no LLM)

- If 0 platforms found: gap "No public review presence detected on G2, Capterra, Trustpilot, Reddit, or Glassdoor"
- If dominant negative theme: finding naming the theme + platforms
- If dominant positive theme: finding naming the theme + platforms
- If sales_rep_themes is non-empty and any theme is negative: finding naming the theme + discovery question
- If G2/Capterra not found: gap "No G2 or Capterra presence detected; may indicate early-stage or channel-heavy sales motion where self-serve review discovery is not yet active"
- Discovery question if themes conflict with content_demand signals (synthesizer handles deeper cross-signal reasoning; collector just emits surface-level questions)

### Collector pattern

```
rrxray/collectors/buyer_sentiment.py
rrxray/collectors/_buyer_sentiment_catalog.py   (PLATFORM_QUERIES dict, QUARANTINE_PLATFORMS set)
```

`collect(ctx) -> BuyerSentimentData`

Steps:
1. `_search_platform(firecrawl, platform, query)` → search results. Catches `FirecrawlError`.
2. `_scrape_platform(firecrawl, url)` → markdown text. Catches `FirecrawlError`.
3. `_collect_platform_text(firecrawl, platform, domain)` → combined raw text (snippets + scraped). Writes to `evidence/buyer_sentiment/raw/<platform>.txt` (Verbatim Quarantine).
4. `_extract_themes(extractor, platform, raw_text)` → `ExtractedSentimentThemes`. LLM call.
5. `_merge_themes(platform_themes_list)` → deduplicated `list[ReviewTheme]` with frequency labels.
6. `_emit_findings(themes, platforms_found, sales_rep_themes)` → rule-based findings/gaps/questions.
7. `_write_evidence(evidence_dir, themes)` → writes `evidence/buyer_sentiment/themes.json`.
8. `collect(ctx)` — orchestrates all platforms via `asyncio.gather(return_exceptions=True)`; returns `BuyerSentimentData`.

---

## Phase 2.5c: `external_voice_vs_internal` synthesizer + render

### Purpose

Cross-signal synthesis: positioning drift vs. buyer reality vs. content posture. Opus 4.7 (multi-input reasoning).

### Inputs

- `ctx.collector_outputs.buyer_sentiment` — themes, platforms, sales-rep signal
- `ctx.collector_outputs.positioning_drift` — snapshot diffs, changed fields
- `ctx.collector_outputs.content_demand` — already present; cadence, categories, lead magnet posture

Skip if all three are None. If only one or two are present, synthesize with available signals (same skip-only-when-all-absent logic as Section A).

### Model

Opus 4.7 (`claude-opus-4-7`). Rationale per roadmap: "multi-input reasoning earns the premium."

### Schema additions

```python
# In rrxray/schemas/data.py

class ExternalVoiceNarrative(BaseModel):
    narrative_paragraphs: list[str]
    gap_bullets: list[str]
    findings: list[Finding] = []
    gaps: list[str] = []
    discovery_questions: list[str] = []
    model_used: str
    cache_hit: bool

# CollectorOutputs gets two new fields:
#   positioning_drift: "PositioningDriftData | None" = None
#   buyer_sentiment: "BuyerSentimentData | None" = None

# SynthesizerOutputs gets one new field:
#   external_voice_vs_internal: ExternalVoiceNarrative | None = None
```

### Synthesizer

```
rrxray/synthesizers/external_voice_vs_internal.py
rrxray/prompts/external_voice_vs_internal.md    (Jinja2 user message template)
```

Synthesizer pattern identical to `observed_gtm_motion.py`:
1. Read collector outputs
2. Read evidence excerpts (positioning_drift snapshots, buyer_sentiment themes.json) as raw text for context
3. Render Jinja2 user message
4. Call `ctx.anthropic.complete_with_cached_system()` with `claude-opus-4-7`
5. Apply voice post-processing on all string fields
6. Return `ExternalVoiceNarrative`

The prompt instructs Opus to:
- Name the gap between what buyers say and what the homepage claims (or confirm alignment)
- Identify whether messaging drift correlates with any buyer frustration theme
- Call out whether content posture matches the positioning the company projects
- Follow RR brand voice: no em dashes, no forbidden words, → for recommendation bullets, GTM Gap™ on first use

### Template changes

**`templates/report_internal.md.jinja`** — Section 4:

```jinja
## 4. Section C: External Voice vs. Internal Voice

{% if data.synthesizers.external_voice_vs_internal %}
{% for para in data.synthesizers.external_voice_vs_internal.narrative_paragraphs %}
{{ para | anonymize | voice_collector }}

{% endfor %}

**Gaps observed:**

{% for bullet in data.synthesizers.external_voice_vs_internal.gap_bullets %}
→ {{ bullet | anonymize | voice_collector }}
{% endfor %}
{% else %}
[Module not available for this domain]
{% endif %}
```

**Module Detail Appendix** — two new include blocks:

```jinja
{% if data.collectors.positioning_drift %}
### Positioning Drift

{% include "_positioning_drift_detail.md.jinja" %}
{% endif %}

{% if data.collectors.buyer_sentiment %}
### Buyer Sentiment

{% include "_buyer_sentiment_detail.md.jinja" %}
{% endif %}
```

**New partials:**

`templates/_positioning_drift_detail.md.jinja`:
- Number of snapshots recovered
- Date range
- Changed fields
- Diff summary (if available)
- Findings list

`templates/_buyer_sentiment_detail.md.jinja`:
- Platforms checked vs. found
- Review count estimate
- Theme list (theme, sentiment, frequency, platforms) — NO verbatims
- Sales-rep theme list separately
- Findings list

### Pipeline registration

Both new collectors appended to `COLLECTORS` in `rrxray/pipeline.py` after `funding_trajectory`:
```python
from rrxray.collectors import positioning_drift, buyer_sentiment
COLLECTORS = [..., funding_trajectory, positioning_drift, buyer_sentiment]
```

---

## Implementation order

1. **Phase 2.5a** (positioning_drift): schemas → catalog → collector → evidence → tests → pipeline registration
2. **Phase 2.5b** (buyer_sentiment): schemas → catalog → extractor method → collector → evidence → tests → pipeline registration
3. **Phase 2.5c** (synthesizer + render): data.py additions → synthesizer → prompt → template changes → partials → tests

Each phase gets its own implementation plan. Quality gate (3-domain smoke) runs after Phase 2.5c when Section C first renders real content.

---

## Quality gate

After Phase 2.5c:
- 3-domain smoke: Swayable (small/sparse ICP), Healthicity (RR ICP target), Linear (PLG regression)
- Section C must render non-placeholder content for at least one ICP domain
- No regressions in Section A or Section B narratives
- Opus whole-branch code review before merge to main

---

## Files created or modified

### Phase 2.5a
New:
- `rrxray/schemas/positioning_drift.py`
- `rrxray/collectors/positioning_drift.py`
- `rrxray/collectors/_positioning_drift_catalog.py`
- `tests/test_positioning_drift_schemas.py`
- `tests/test_positioning_drift.py`
- `tests/fixtures/synthetic/positioning_drift/` (HTML + JSON fixtures)

Modified:
- `rrxray/schemas/data.py` (CollectorOutputs.positioning_drift field)
- `rrxray/pipeline.py` (COLLECTORS registration)

### Phase 2.5b
New:
- `rrxray/schemas/buyer_sentiment.py`
- `rrxray/collectors/buyer_sentiment.py`
- `rrxray/collectors/_buyer_sentiment_catalog.py`
- `tests/test_buyer_sentiment_schemas.py`
- `tests/test_buyer_sentiment.py`
- `tests/fixtures/synthetic/buyer_sentiment/` (search result + scraped page fixtures)

Modified:
- `rrxray/schemas/data.py` (CollectorOutputs.buyer_sentiment field)
- `rrxray/services/extraction.py` (ExtractedSentimentThemes + extract_sentiment_themes on HaikuExtractor)
- `rrxray/pipeline.py` (COLLECTORS registration)

### Phase 2.5c
New:
- `rrxray/synthesizers/external_voice_vs_internal.py`
- `rrxray/prompts/external_voice_vs_internal.md`
- `templates/_positioning_drift_detail.md.jinja`
- `templates/_buyer_sentiment_detail.md.jinja`
- `tests/test_external_voice_synthesizer.py`

Modified:
- `rrxray/schemas/data.py` (ExternalVoiceNarrative class + SynthesizerOutputs field)
- `templates/report_internal.md.jinja` (Section C render block + Module Detail Appendix includes)
- `tests/test_render_internal.py` (Section C render test)
- `tests/test_schemas.py` (CollectorOutputs + SynthesizerOutputs field tests)
- `tests/test_pipeline.py` (pipeline registration tests)
