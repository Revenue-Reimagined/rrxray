# rrxray Phase 2.1a: tech_stack Collector Design

**Date:** 2026-05-07
**Status:** Approved (brainstorming complete)
**Phase:** 2.1a (smallest possible cycle inside Phase 2)
**Builds on:** Phase 1 foundation (commit `1023999` on `feat/phase-1-foundation`)

---

## Context

Phase 1 shipped the rrxray foundation: every infrastructure piece (schemas, cache, voice post-processor, anonymizer, service clients, pipeline orchestrator, CLI, renderer) plus the `pricing_packaging` collector and a pricing-only Section A synthesizer. Live runs against `sqaservices.com` and `swayable.com` produced clean reports.

Phase 2 originally scoped 8 new collectors, 2 new section synthesizers, an Executive Summary synthesizer, and a Section A upgrade. That's roughly 30-40 tasks. Splitting Phase 2 into multiple cycles trades cycle time for course-correction headroom and lets each cycle ship visible progress.

**Phase 2.1a is the smallest possible cycle:** add ONE new collector (`tech_stack`) end-to-end. No synthesizer change, no Section A upgrade, no new client surface beyond what Phase 1 ships. The goal is to validate that the new-collector pattern works for a non-pricing collector before scaling up to add 7 more.

When 2.1a lands, future cycles ramp:

- **Phase 2.1b:** Section A synthesizer upgrade reading from `pricing_packaging + tech_stack`. The first multi-collector synthesizer.
- **Phase 2.1c:** add `revenue_motion` collector. By end of 2.1c, Section A reads from 3 collectors.
- **Phase 2.1d:** add `content_demand` collector. Section A reads from 4 collectors and is fully spec'd.
- **Phase 2.2 onward:** Section B (`stability_trajectory`) and Section C (`external_voice_vs_internal`) collectors and synthesizers.

---

## Scope

### In scope

- New collector module `rrxray/collectors/tech_stack.py` plus its catalog at `rrxray/collectors/_tech_stack_catalog.py`
- New schema module `rrxray/schemas/tech_stack.py` with `TechStackData` and `DetectedTool`
- Catalog of approximately 40 tools across 9 categories (analytics, tag_manager, marketing_automation, chat, product_analytics, crm, cdp, ab_testing, attribution) with two-tier confidence (high / low) signatures
- Rule-based findings, gaps, and discovery_questions emitted from the collector itself (no LLM in collector path; matches Phase 1 pricing pattern)
- New Jinja partial `templates/_tech_stack_detail.md.jinja` for the Module Detail Appendix
- `tech_stack: TechStackData | None = None` field added to `CollectorOutputs`
- `tech_stack` module appended to `pipeline.COLLECTORS`
- Synthetic HTML fixture tests matching the Phase 1 pricing pattern
- Updated `roadmap.md` reflecting Phase 2.1a completion

### Out of scope (future cycles)

- Section A synthesizer upgrade to read from `tech_stack` (Phase 2.1b)
- BuiltWith public-profile cross-reference (deferred indefinitely; not high-signal enough for the work)
- Job-description tool parsing (belongs with `revenue_motion` collector in a later cycle)
- Cache thundering-herd fix (Phase 1 known limitation, not this cycle)
- Templates packaging for wheel installs (Phase 4)
- Section B / Section C / Executive Summary synthesizers (Phase 2.2 onward)
- LLM-based tool detection (collectors stay rule-based; LLM budget is reserved for synthesis)

---

## Decisions Locked During Brainstorming

| Decision | Choice | Rationale |
|---|---|---|
| Cycle scope | Single collector, no synthesizer change | Smallest possible validation of the new-collector pattern |
| Catalog size | ~40 tools across 9 categories | Cover the highest-signal GTM tooling categories without ballooning maintenance |
| Detection strictness | Two-tier (strict + loose) with confidence labels per detection | False positives are worse than misses, but loose signatures catch installations missed by strict patterns |
| Catalog format | Python module with regex constants | Type-safe, no new dependencies, easy to grep and extend |
| Findings logic | Rule-based, no LLM | Matches Phase 1 pattern; LLM budget reserved for synthesis |
| Module Detail layout | Categorized table per category | Best signal density for human reading |
| Schema location | New file `rrxray/schemas/tech_stack.py` | Matches Phase 1 pattern (one schema file per collector) |

---

## Architecture

### File layout (new files in **bold**)

```
rrxray/
  collectors/
    pricing_packaging.py                              [Phase 1]
    **tech_stack.py**                                 [collector entry point: NAME, collect()]
    **_tech_stack_catalog.py**                        [catalog of signatures]
  schemas/
    pricing_packaging.py                              [Phase 1]
    **tech_stack.py**                                 [TechStackData, DetectedTool]
    data.py                                           [modify: add tech_stack field on CollectorOutputs]
  pipeline.py                                         [modify: append tech_stack to COLLECTORS]
templates/
  _pricing_detail.md.jinja                            [Phase 1]
  **_tech_stack_detail.md.jinja**                     [new partial]
  report_internal.md.jinja                            [modify: include the new partial in Module Detail]
tests/
  **test_tech_stack.py**                              [collector tests]
  **test_tech_stack_catalog.py**                      [catalog signature tests]
  **fixtures/synthetic/tech_stack/**                  [synthetic HTML fixtures]
```

---

## Components

### Catalog (`rrxray/collectors/_tech_stack_catalog.py`)

Flat list of signature dicts. Each dict has:

- `tool: str` — display name (e.g., "HubSpot", "Google Tag Manager")
- `category: str` — one of the 9 fixed categories
- `id: str` — stable signature identifier (e.g., `"hubspot:strict_js"`); used for audit
- `pattern: str` — Python regex pattern; case-insensitive matching applied at compile time
- `confidence: Literal["high", "low"]`

Example:

```python
SIGNATURES: list[dict[str, str]] = [
    # Analytics
    {"tool": "Google Analytics 4", "category": "analytics", "id": "ga4:strict_gtag",
     "pattern": r"\bgtag\s*\(\s*['\"]config['\"]\s*,\s*['\"]G-[A-Z0-9]+['\"]", "confidence": "high"},
    {"tool": "Mixpanel", "category": "analytics", "id": "mixpanel:strict_lib",
     "pattern": r"cdn\.mxpnl\.com/libs/mixpanel-[0-9.]+\.min\.js", "confidence": "high"},

    # Tag manager
    {"tool": "Google Tag Manager", "category": "tag_manager", "id": "gtm:strict_dataLayer",
     "pattern": r"googletagmanager\.com/gtm\.js\?id=GTM-[A-Z0-9]+", "confidence": "high"},

    # Marketing automation
    {"tool": "HubSpot", "category": "marketing_automation", "id": "hubspot:strict_js",
     "pattern": r"js\.hs-scripts\.com/\d+\.js", "confidence": "high"},
    {"tool": "HubSpot", "category": "marketing_automation", "id": "hubspot:loose_form",
     "pattern": r"hsforms\.net|hsforms\.com", "confidence": "low"},
    {"tool": "Marketo", "category": "marketing_automation", "id": "marketo:strict_munchkin",
     "pattern": r"munchkin\.marketo\.net/munchkin\.js", "confidence": "high"},

    # Chat
    {"tool": "Intercom", "category": "chat", "id": "intercom:strict_widget",
     "pattern": r"widget\.intercom\.io/widget/[a-z0-9]+", "confidence": "high"},
    {"tool": "Drift", "category": "chat", "id": "drift:strict_js",
     "pattern": r"js\.driftt\.com/include/[A-Za-z0-9_]+/[a-z0-9]+\.js", "confidence": "high"},

    # Product analytics
    {"tool": "Pendo", "category": "product_analytics", "id": "pendo:strict_agent",
     "pattern": r"cdn\.pendo\.io/agent/static/[a-f0-9-]+/pendo\.js", "confidence": "high"},
    {"tool": "Heap", "category": "product_analytics", "id": "heap:strict_lib",
     "pattern": r"cdn\.heapanalytics\.com/js/heap-\d+\.js", "confidence": "high"},

    # CRM
    {"tool": "Salesforce Web-to-Lead", "category": "crm", "id": "sfdc:strict_w2l",
     "pattern": r"webto\.salesforce\.com/servlet/servlet\.WebToLead", "confidence": "high"},

    # CDP
    {"tool": "Segment", "category": "cdp", "id": "segment:strict_analytics",
     "pattern": r"cdn\.segment\.com/analytics\.js/v1/[A-Za-z0-9]+/analytics\.min\.js", "confidence": "high"},
    {"tool": "Rudderstack", "category": "cdp", "id": "rudderstack:strict_lib",
     "pattern": r"cdn\.rudderlabs\.com/v1\.\d+/rudder-analytics\.min\.js", "confidence": "high"},

    # A/B testing
    {"tool": "Optimizely", "category": "ab_testing", "id": "optimizely:strict_lib",
     "pattern": r"cdn\.optimizely\.com/js/\d+\.js", "confidence": "high"},

    # Attribution
    {"tool": "Demandbase", "category": "attribution", "id": "demandbase:strict_lib",
     "pattern": r"tag\.demandbase\.com/[A-Za-z0-9_]+\.min\.js", "confidence": "high"},
    {"tool": "6sense", "category": "attribution", "id": "sixsense:strict_lib",
     "pattern": r"j\.6sc\.co/[A-Za-z0-9_]+\.js", "confidence": "high"},

    # ... (full catalog ships ~40 entries)
]

CATEGORIES: list[str] = [
    "analytics", "tag_manager", "marketing_automation", "chat",
    "product_analytics", "crm", "cdp", "ab_testing", "attribution",
]
```

The plan implementation will fill out the full ~40-entry list. Initial implementation lands enough entries to cover the spec's named tools (Segment, GTM, HubSpot, Marketo, Intercom, Drift, Pendo, Salesforce W2L) plus cross-category coverage. Future entries get added as gaps surface during real-domain runs.

### Schema (`rrxray/schemas/tech_stack.py`)

```python
"""Schemas specific to the tech_stack collector."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from rrxray.schemas._shared import Finding, SourceCitation


Category = Literal[
    "analytics", "tag_manager", "marketing_automation", "chat",
    "product_analytics", "crm", "cdp", "ab_testing", "attribution",
]


class DetectedTool(BaseModel):
    name: str                          # "HubSpot"
    category: Category
    confidence: Literal["high", "low"]
    signature_id: str                  # "hubspot:strict_js"
    matched_text: str                  # truncated to first 100 chars of the regex match


class TechStackData(BaseModel):
    detected_tools: list[DetectedTool] = []
    categories_observed: list[Category] = []
    categories_absent: list[Category] = []
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
    tech_stack: "TechStackData | None" = None    # new
```

Plus an end-of-file import and `model_rebuild()` for the forward reference, matching the Phase 1 pricing_packaging pattern.

### Collector (`rrxray/collectors/tech_stack.py`)

Module shape mirrors Phase 1's `pricing_packaging.py`:

```python
"""tech_stack collector: detects analytics/martech/CRM tools by HTML signature matching."""
from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from pathlib import Path

from rrxray.collectors._tech_stack_catalog import CATEGORIES, SIGNATURES
from rrxray.context import CollectorContext
from rrxray.schemas._shared import Finding, SourceCitation
from rrxray.schemas.tech_stack import Category, DetectedTool, TechStackData
from rrxray.services.firecrawl_client import FirecrawlError

NAME = "tech_stack"
log = logging.getLogger(f"rrxray.collectors.{NAME}")


def _compile_signatures():
    """Pre-compile every signature regex once at module load time."""
    compiled = []
    for sig in SIGNATURES:
        compiled.append({
            **sig,
            "compiled": re.compile(sig["pattern"], re.IGNORECASE),
        })
    return compiled


_COMPILED = _compile_signatures()


def _detect(html: str) -> list[DetectedTool]:
    """Run every compiled signature against the HTML; return one DetectedTool per tool name (highest confidence wins)."""
    matches: dict[str, DetectedTool] = {}
    for sig in _COMPILED:
        m = sig["compiled"].search(html)
        if not m:
            continue
        existing = matches.get(sig["tool"])
        new_conf = sig["confidence"]
        # Keep highest-confidence detection per tool name
        if existing and existing.confidence == "high" and new_conf == "low":
            continue
        matches[sig["tool"]] = DetectedTool(
            name=sig["tool"],
            category=sig["category"],
            confidence=new_conf,
            signature_id=sig["id"],
            matched_text=m.group(0)[:100],
        )
    return sorted(matches.values(), key=lambda t: (t.category, t.name))


def _emit_findings(detected: list[DetectedTool], domain: str, scrape_url: str, now: datetime) -> tuple[list[Finding], list[str], list[str]]:
    """Rule-based findings/gaps/questions emission. No LLM."""
    findings: list[Finding] = []
    gaps: list[str] = []
    questions: list[str] = []

    if not detected:
        findings.append(Finding(
            text="No analytics, marketing, or CRM tags detected on the homepage.",
            source=SourceCitation(url=scrape_url, timestamp=now),
        ))
        questions.append(
            "We did not detect any common marketing or analytics tooling on your homepage. "
            "Is that a deliberate posture (e.g., privacy-led), or are tags loaded server-side or via a tag manager we did not match?"
        )
        return findings, gaps, questions

    categories = {t.category for t in detected}
    absent = [c for c in CATEGORIES if c not in categories]

    # Detection-driven findings
    has_marketing = "marketing_automation" in categories
    has_crm = "crm" in categories
    has_product_analytics = "product_analytics" in categories
    has_chat = "chat" in categories

    if has_marketing and not has_crm:
        findings.append(Finding(
            text="Marketing automation present; no CRM signature detected on the homepage. CRM may be detected via other surfaces.",
            source=SourceCitation(url=scrape_url, timestamp=now),
        ))
    if has_product_analytics:
        questions.append(
            "Product analytics tooling indicates an in-product activation focus. "
            "What are your activation and time-to-value benchmarks today?"
        )
    if has_chat and not has_marketing:
        gaps.append(
            "Live chat tooling is present but no marketing automation was detected. "
            "Inbound conversations may not be feeding a nurture sequence."
        )

    # Category absence as gaps
    if "analytics" in absent and "tag_manager" in absent:
        gaps.append("Neither web analytics nor a tag manager was detected. Site engagement data may be sparse.")
    if "marketing_automation" in absent:
        gaps.append("No marketing automation tooling was detected; lead nurture may rely on manual outreach.")
    if "product_analytics" in absent:
        gaps.append("No product analytics was detected; activation and feature adoption signals are likely informal.")

    return findings, gaps, questions


def _write_evidence(evidence_dir: Path, html: str, detected: list[DetectedTool]) -> None:
    """Write the raw scraped HTML and the detection set to the evidence dir."""
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / "homepage.html").write_text(html, encoding="utf-8")
    import json
    (evidence_dir / "detections.json").write_text(
        json.dumps([t.model_dump() for t in detected], indent=2),
        encoding="utf-8",
    )


async def collect(ctx: CollectorContext) -> TechStackData:
    """Scrape the homepage; run all signatures; emit DetectedTool list and findings."""
    now = datetime.now(UTC)
    homepage_url = f"https://{ctx.domain}"

    try:
        page = await ctx.firecrawl.scrape_url(homepage_url, only_main_content=False)
    except FirecrawlError as e:
        log.warning("homepage scrape failed for %s: %s", homepage_url, e)
        return TechStackData(
            findings=[Finding(
                text=f"Could not fetch homepage at {homepage_url} for tech stack detection.",
                source=SourceCitation(url=homepage_url, timestamp=now),
            )],
        )

    detected = _detect(page.html or "")
    categories_observed = sorted({t.category for t in detected})
    categories_absent = [c for c in CATEGORIES if c not in categories_observed]

    findings, gaps, questions = _emit_findings(detected, ctx.domain, homepage_url, now)

    _write_evidence(ctx.evidence_dir / NAME, page.html or "", detected)

    sources = [SourceCitation(
        url=homepage_url,
        timestamp=now,
        evidence_path=str((ctx.evidence_dir / NAME / "homepage.html").relative_to(ctx.evidence_dir)),
    )]

    return TechStackData(
        detected_tools=detected,
        categories_observed=categories_observed,
        categories_absent=categories_absent,
        findings=findings,
        gaps=gaps,
        discovery_questions=questions,
        sources=sources,
    )
```

### Renderer template (`templates/_tech_stack_detail.md.jinja`)

```jinja
{% set t = data.collectors.tech_stack %}
{% if t.detected_tools %}
**Detected tooling ({{ t.detected_tools | length }}):**

| Category | Tool | Confidence | Signature |
|---|---|---|---|
{% for tool in t.detected_tools %}
| {{ tool.category }} | {{ tool.name }} | {{ tool.confidence }} | `{{ tool.signature_id }}` |
{% endfor %}

**Categories observed:** {{ t.categories_observed | join(", ") }}
**Categories not detected:** {{ t.categories_absent | join(", ") }}
{% else %}
No analytics, marketing, or CRM tooling detected on the homepage.
{% endif %}

{% if t.findings %}
**Findings:**

{% for f in t.findings %}
- {{ f.text | voice_collector }} *(source: [{{ f.source.url }}]({{ f.source.url }}))*
{% endfor %}
{% endif %}

{% if t.gaps %}
**Gaps:**
{% for g in t.gaps %}
→ {{ g | voice_collector }}
{% endfor %}
{% endif %}

{% if t.discovery_questions %}
**Discovery questions:**
{% for q in t.discovery_questions %}
- {{ q }}
{% endfor %}
{% endif %}
```

`templates/report_internal.md.jinja` adds in the Module Detail Appendix:

```jinja
{% if data.collectors.tech_stack %}
### Tech Stack

{% include "_tech_stack_detail.md.jinja" %}
{% endif %}
```

### Pipeline integration (`rrxray/pipeline.py`)

```python
from rrxray.collectors import pricing_packaging, tech_stack    # add tech_stack

COLLECTORS = [pricing_packaging, tech_stack]                   # append
```

That's the entire pipeline change. The pipeline orchestrator's graceful-degradation path catches tech_stack failures the same way it catches pricing_packaging failures.

---

## Data flow

```
CollectorContext (domain, firecrawl, evidence_dir, ...)
   ↓
tech_stack.collect(ctx)
   ↓
firecrawl.scrape_url(homepage_url, only_main_content=False)   [HTML with <head>]
   ↓
_detect(html) iterates compiled signatures
   ↓
list[DetectedTool] (deduped per tool, highest confidence wins)
   ↓
_emit_findings(detected, ...)   [rule-based; no LLM]
   ↓
_write_evidence(...)             [homepage.html + detections.json]
   ↓
TechStackData (validated by pydantic)
   ↓
returned to pipeline → assigned to CollectorOutputs.tech_stack
```

---

## Error handling

- `FirecrawlError` from the homepage scrape: caught inside `collect()`. Returns a `TechStackData` with a single finding noting the failure. The pipeline does not see an exception.
- Empty `page.html`: detection yields zero matches; the empty-detection finding fires.
- Pydantic validation: `validate_assignment=True` on `CollectorOutputs` ensures wrong return types are caught at pipeline-set time.

Other failure modes (regex patterns that fail to compile at module load) are caught at import time and prevent the pipeline from starting; that's the right behavior for a code-correctness issue.

---

## Testing

### Test files

- **`tests/test_tech_stack_catalog.py`** — every signature compiles; every `tool` has a known category; `id` values are unique; confidence is high or low.
- **`tests/test_tech_stack.py`** — collector tests using synthetic HTML fixtures:
  - `test_detect_hubspot_strict` — HTML containing `js.hs-scripts.com/12345.js` produces one DetectedTool with confidence "high"
  - `test_detect_hubspot_loose_falls_through` — HTML with only `hsforms.net` produces confidence "low"
  - `test_strict_overrides_loose_for_same_tool` — HTML with both signatures produces ONE DetectedTool with confidence "high"
  - `test_categories_observed_and_absent` — given a fixture with HubSpot + Pendo, `categories_observed=["marketing_automation","product_analytics"]` and `categories_absent` excludes those two
  - `test_no_detections_emits_finding` — empty HTML produces a finding "No analytics, marketing, or CRM tags detected"
  - `test_chat_without_marketing_automation_gap` — Intercom but no MAP produces the "live chat without nurture" gap
  - `test_marketing_automation_without_crm_finding` — HubSpot but no Salesforce W2L produces the "MA present, no CRM detected" finding
  - `test_evidence_files_written` — `evidence/tech_stack/homepage.html` and `detections.json` written
  - `test_source_citation_path_relative_to_evidence_dir` — paths do not have doubled `evidence/`
  - `test_firecrawl_error_handled_gracefully` — `FirecrawlError` returns a `TechStackData` with a single fetch-failure finding (no exception escapes `collect()`)
  - `test_only_main_content_false` — collector calls `scrape_url(..., only_main_content=False)` (regression on Phase 1 pricing default)

### Synthetic fixtures

`tests/fixtures/synthetic/tech_stack/` holds:

- `hubspot_strict.html` — minimal HTML with `<script src="https://js.hs-scripts.com/12345.js">`
- `hubspot_loose.html` — HTML with only `hsforms.net` reference
- `multi_tool.html` — HubSpot + Pendo + Intercom + GTM + GA4
- `empty.html` — no detectable tags
- `chat_without_map.html` — Intercom only

### Running

```bash
uv run pytest tests/test_tech_stack.py tests/test_tech_stack_catalog.py -v
uv run pytest -v   # full suite stays green (~140 tests after this phase)
```

---

## Phase 2.1a acceptance criteria

| # | Criterion | Verified by |
|---|---|---|
| 1 | `tech_stack` collector exists and is registered in `pipeline.COLLECTORS` | `tests/test_tech_stack.py::test_collector_registered` |
| 2 | The catalog has at least 30 signature entries spanning all 9 categories | `tests/test_tech_stack_catalog.py::test_catalog_coverage` |
| 3 | Every regex in the catalog compiles | `tests/test_tech_stack_catalog.py::test_all_signatures_compile` |
| 4 | Strict signatures override loose for the same tool | `tests/test_tech_stack.py::test_strict_overrides_loose_for_same_tool` |
| 5 | Empty homepage HTML produces a graceful finding (not an exception) | `tests/test_tech_stack.py::test_no_detections_emits_finding` |
| 6 | `FirecrawlError` is caught and converted to a graceful Finding | `tests/test_tech_stack.py::test_firecrawl_error_handled_gracefully` |
| 7 | Evidence files written with the correct relative paths | `tests/test_tech_stack.py::test_evidence_files_written` and `test_source_citation_path_relative_to_evidence_dir` |
| 8 | `data.json` round-trips with `tech_stack` populated | `tests/test_pipeline_graceful_degradation.py::test_data_json_round_trips` (existing test, will exercise the new field) |
| 9 | The Module Detail Appendix renders the Tech Stack subsection when `tech_stack` is non-None | `tests/test_render_internal.py::test_tech_stack_module_detail_renders` (new) |
| 10 | A live run against `swayable.com` populates `tech_stack` with at least 3 detections | manual smoke; not a CI test |

---

## Risks and known limitations

- **Detection misses real installations behind proxies, server-side tag containers, or CSP/SRI-modified URLs.** Two-tier confidence partially mitigates by adding loose patterns where reasonable. Acceptable risk; we'd rather miss than emit false positives.
- **Homepage-only detection misses tools active only on inner pages (pricing, blog, app subdomain).** The full spec mentions JD parsing for sales-stack inference; that's the second collector pass deferred to `revenue_motion`. Acceptable for Phase 2.1a.
- **Catalog will need ongoing maintenance** as vendors change their CDN URLs and tracking schemes. The plan includes one mechanism for adding signatures (append a dict to `SIGNATURES`) and the catalog test suite will catch broken regexes immediately.
- **No HTML caching at the homepage URL beyond Firecrawl's cache layer.** First time a domain is run, the full homepage is scraped. Subsequent runs hit the disk cache (24h TTL). For frequent re-runs we'd want shorter TTLs or a `--no-cache` flag (already exists per Phase 1).
- **`only_main_content=False` returns more bytes than `True`.** Firecrawl charges per scrape, not per byte, so cost is the same. But cache files will be larger.
- **Detection ordering is not deterministic across runs unless we sort.** The collector sorts by `(category, name)` after detection so output is stable.

---

## Out of scope but accommodated by the design

- Phase 2.1b's Section A synthesizer upgrade reads `data.collectors.tech_stack` directly. The schema is shaped for cross-section reasoning.
- Phase 2.1c's `revenue_motion` collector will reuse the catalog-of-fingerprints pattern for JD tool parsing if useful.
- Phase 3's Gemini integration treats `tech_stack` as just another collector output. No special-case wiring.
- The renderer's voice and anonymizer filters apply to `tech_stack` findings/gaps/questions automatically (the partial uses `| voice_collector`).

---

## Open questions

None at this time. All material decisions are locked.
