# rrxray Phase 2.1c: revenue_motion Collector Design

**Date:** 2026-05-07
**Status:** Approved (brainstorming complete)
**Phase:** 2.1c (third sub-phase inside Phase 2)
**Builds on:** Phase 2.1b Section A multi-collector synthesizer (commit `fb0d089`)

---

## Context

Phase 2.1b shipped Section A reading from `pricing_packaging` + `tech_stack`. The quality-gate iteration confirmed cross-signal reasoning works on real domains, but the diagnostic depth is still constrained by the data available — two signals from a public homepage and a pricing page. The dial moves further when we add hiring-shape data.

Careers pages and JD content are the highest-signal indicator of GTM motion intent that's publicly available. What you're hiring tells you everything about motion direction: AE/SDR ratio, "first sales hire" / "founding AE" patterns, "Enterprise AE" titles vs "Account Executive," sales leadership presence, geographic shape, growth pace.

Phase 2.1c adds the `revenue_motion` collector. Scope locked: company-hosted careers page + LinkedIn job postings + LinkedIn employee count snippet (via Firecrawl `search`). This phase also extends `FirecrawlClient` with the `search()` method that Phase 1 deferred — a one-time extension that pays for itself across Phase 2.1c (LinkedIn signals), Phase 2.2 (`leadership_stability` press-release search), and Phase 2.3 (`buyer_sentiment` G2/Reddit/Glassdoor search).

After this phase: Section A reads from THREE collectors. The `observed_gtm_motion` synthesizer's "available signals" prompt frame already accommodates new collector blocks — we add a third conditional `{% if revenue_motion %}` block to the prompt template. No synthesizer logic change beyond reading one more collector output.

---

## Scope

### In scope

- New collector module `rrxray/collectors/revenue_motion.py` plus role-taxonomy catalog `rrxray/collectors/_revenue_motion_catalog.py`
- New schema module `rrxray/schemas/revenue_motion.py` with `RevenueMotionData` and `JobPosting`
- `FirecrawlClient.search()` method (the deferred Phase 1 capability) — async wrapper around the Firecrawl SDK's search; same disk-cache + concurrency-cap pattern as `scrape_url`
- Careers page URL discovery (try `/careers`, `/jobs`, `/work-with-us`, `/join-us`)
- ATS-link detection: scan careers page HTML for links to Lever, Greenhouse, Ashby, Workable subdomains; if found, scrape that surface too
- HTML parsing for role titles via the catalog's keyword lists
- LinkedIn job postings via `FirecrawlClient.search()` (Google search query against `site:linkedin.com/jobs`)
- LinkedIn employee count via `FirecrawlClient.search()` (Google search query against `site:linkedin.com/company`)
- Rule-based findings, gaps, and discovery questions emitted from the collector itself (no LLM in collector path; matches Phase 1 pattern)
- New Jinja partial `templates/_revenue_motion_detail.md.jinja` for the Module Detail Appendix
- `revenue_motion: RevenueMotionData | None = None` field added to `CollectorOutputs`
- `revenue_motion` module appended to `pipeline.COLLECTORS`
- New conditional block in the synthesizer prompt template (`rrxray/prompts/observed_gtm_motion.md`) — Revenue Motion signal alongside the existing Pricing and Tech Stack blocks
- Synthesizer body updated to read `revenue_motion` from `collector_outputs` and pass to the prompt renderer
- Synthetic HTML + search-response fixture tests (matches Phase 1 pricing pattern; no live API calls in unit tests)
- Quality gate: 3-domain smoke + Dale-led prompt review (the same loop as Phase 2.1b)

### Out of scope (future cycles)

- Per-JD deep parsing (comp range extraction from JD body, tool mentions, motion-language analysis) — Phase 2.1c-deep or later
- LLM-augmented role classification — collectors stay rule-based
- Glassdoor / Indeed integration — separate collector, Phase 2.3 buyer_sentiment territory for some of it
- Paid third-party APIs (Coresignal, PeopleDataLabs, Apollo) — outside the project's "no paid third-party APIs" rule
- Per-employee LinkedIn profile scraping — login-walled, leadership_stability collector territory in Phase 2.2 via press-release search
- Headcount-over-time trajectory (requires Wayback snapshots of LinkedIn pages, which are inconsistent) — possible Phase 2.2 addition

---

## Decisions Locked During Brainstorming

| Decision | Choice | Rationale |
|---|---|---|
| Cycle scope | Careers page + LinkedIn job postings + LinkedIn employee count snippet | Real signal beyond what /careers alone gives, without the cost of per-JD deep parsing |
| ATS handling | Generic scraping with ATS-link follow (Lever / Greenhouse / Ashby / Workable detected from careers page links) | Handles "own page" + "redirect to ATS" + "hybrid" patterns naturally; one extra HTTP per domain |
| Role taxonomy | Hardcoded keyword catalog with 8 categories | Matches Phase 2.1a tech_stack pattern; deterministic, no LLM in collector path |
| LinkedIn data path | Firecrawl `search()` against Google for `site:linkedin.com/...` queries | Best-effort but real signal; Firecrawl handles the rate-limit + scraping work for us |
| Schema location | New file `rrxray/schemas/revenue_motion.py` | Matches the per-collector-schema-file pattern from Phase 1 + 2.1a |
| FirecrawlClient extension | Add `search()` now (Phase 2.2 + 2.3 also need it) | One-time investment; future collectors inherit |
| Synthesizer change | Add third conditional block to existing prompt; one-line update to synthesizer body | Generic "available signals" frame already accommodates this |
| Quality gate | Dale-led review against Swayable, SQA Services, Linear (same domains as Phase 2.1b) | Direct A/B comparison: same domain, with vs without revenue_motion signal |

---

## Architecture

### File layout (changes only)

```
NEW:
  rrxray/collectors/revenue_motion.py             [collector entry: NAME, _discover_careers_url, _detect_ats, _extract_roles, _linkedin_search, _emit_findings, _write_evidence, collect]
  rrxray/collectors/_revenue_motion_catalog.py    [role taxonomy keyword catalog: 8 categories]
  rrxray/schemas/revenue_motion.py                [RevenueMotionData, JobPosting]
  templates/_revenue_motion_detail.md.jinja       [Module Detail partial]
  tests/test_revenue_motion.py                    [collector tests + synthetic fixtures]
  tests/test_revenue_motion_catalog.py            [catalog integrity tests]
  tests/fixtures/synthetic/revenue_motion/        [sample HTML + LinkedIn search response fixtures]

MODIFIED:
  rrxray/services/firecrawl_client.py             [add async search(query, limit=10) -> list[SearchResult]]
  tests/test_firecrawl_client.py                  [tests for search() method]
  rrxray/schemas/data.py                          [add revenue_motion field on CollectorOutputs]
  rrxray/pipeline.py                              [append revenue_motion to COLLECTORS]
  rrxray/prompts/observed_gtm_motion.md           [add third conditional block: Revenue Motion signal]
  rrxray/synthesizers/observed_gtm_motion.py      [read revenue_motion from collector_outputs; pass to _render_user_message]
  tests/test_synthesizer_observed_gtm_motion.py   [add test_synth_runs_with_three_collectors]
  templates/report_internal.md.jinja              [include _revenue_motion_detail partial in Module Detail Appendix]
```

---

## Components

### `FirecrawlClient.search()` extension (`rrxray/services/firecrawl_client.py`)

```python
class SearchResult(BaseModel):
    url: str
    title: str
    description: str = ""
    metadata: dict[str, Any] = {}


class FirecrawlClient:
    # ... existing __init__ and scrape_url ...

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        """Web search via Firecrawl SDK.

        Returns up to `limit` results. Useful for queries against LinkedIn,
        press release indexes, review sites, etc. Goes through the same
        cache layer as scrape_url.
        """
        args = {"query": query, "limit": limit}

        async def upstream() -> list[dict[str, Any]]:
            async with self._semaphore:
                try:
                    response = await asyncio.to_thread(
                        self._sdk.search, query, limit=limit,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    log.warning("Firecrawl search failed for %r: %s", query, e)
                    raise FirecrawlError(f"search({query!r}) failed: {e}") from e
            # firecrawl-py v2 returns a list of dicts (or a SearchResults object)
            if hasattr(response, "model_dump"):
                payload = response.model_dump()
                return payload.get("results", []) if isinstance(payload, dict) else []
            if isinstance(response, list):
                return response
            return []

        raw = await self.cache.get_or_call("firecrawl.search", args, upstream)
        results: list[SearchResult] = []
        for r in raw or []:
            if not isinstance(r, dict):
                continue
            results.append(SearchResult(
                url=r.get("url", ""),
                title=r.get("title", ""),
                description=r.get("description", "") or r.get("snippet", "") or "",
                metadata={k: v for k, v in r.items() if k not in {"url", "title", "description", "snippet"}},
            ))
        return results
```

The exact SDK return shape depends on `firecrawl-py` version. The implementer must verify via `inspect` and adapt if the v2 search returns a different shape (Phase 2.1a's T7 fix established this discipline).

### Role catalog (`rrxray/collectors/_revenue_motion_catalog.py`)

8 categories with hardcoded keyword lists. Pattern matching is case-insensitive substring (the title contains the keyword as a whole word).

```python
ROLE_CATEGORIES: list[str] = [
    "ae", "sdr", "revops", "csm",
    "sales_leadership", "marketing_leadership",
    "marketing_ops", "other",
]


# Keywords ordered by specificity (more-specific patterns checked first)
ROLE_KEYWORDS: list[dict[str, str | list[str]]] = [
    # AE titles
    {"category": "ae", "keywords": [
        "enterprise account executive", "strategic account executive",
        "mid-market account executive", "senior account executive",
        "account executive", "sales representative",
    ]},
    {"category": "ae", "keywords": ["AE", "enterprise AE", "strategic AE"]},

    # SDR titles
    {"category": "sdr", "keywords": [
        "sales development representative", "business development representative",
        "outbound SDR", "inbound SDR",
    ]},
    {"category": "sdr", "keywords": ["SDR", "BDR"]},

    # RevOps
    {"category": "revops", "keywords": [
        "revenue operations", "sales operations", "go-to-market operations",
        "GTM operations",
    ]},
    {"category": "revops", "keywords": ["RevOps", "SalesOps"]},

    # CSM
    {"category": "csm", "keywords": [
        "customer success manager", "customer success", "account manager",
        "post-sales", "renewals manager",
    ]},
    {"category": "csm", "keywords": ["CSM", "AM"]},

    # Sales leadership
    {"category": "sales_leadership", "keywords": [
        "chief revenue officer", "VP of sales", "VP sales",
        "head of sales", "director of sales", "VP revenue",
        "VP of revenue", "head of revenue",
    ]},
    {"category": "sales_leadership", "keywords": ["CRO"]},

    # Marketing leadership
    {"category": "marketing_leadership", "keywords": [
        "chief marketing officer", "VP marketing", "VP of marketing",
        "head of marketing", "director of marketing",
    ]},
    {"category": "marketing_leadership", "keywords": ["CMO"]},

    # Marketing ops
    {"category": "marketing_ops", "keywords": [
        "marketing operations", "marketing ops", "demand generation",
        "demand gen",
    ]},
]


# ATS subdomain patterns for follow-the-link detection
ATS_PATTERNS: list[dict[str, str]] = [
    {"name": "lever", "url_pattern": r"jobs\.lever\.co/([a-z0-9-]+)"},
    {"name": "greenhouse", "url_pattern": r"boards\.greenhouse\.io/([a-z0-9-]+)"},
    {"name": "ashby", "url_pattern": r"([a-z0-9-]+)\.ashbyhq\.com"},
    {"name": "workable", "url_pattern": r"apply\.workable\.com/([a-z0-9-]+)"},
]
```

### Schema (`rrxray/schemas/revenue_motion.py`)

```python
"""Schemas specific to the revenue_motion collector."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from rrxray.schemas._shared import Finding, SourceCitation

RoleCategory = Literal[
    "ae", "sdr", "revops", "csm",
    "sales_leadership", "marketing_leadership",
    "marketing_ops", "other",
]


class JobPosting(BaseModel):
    title: str
    category: RoleCategory
    url: str | None = None
    source: Literal["company_careers", "ats", "linkedin"]
    location: str | None = None
    matched_keyword: str | None = None


class RevenueMotionData(BaseModel):
    careers_page_url: str | None = None
    ats_platform: str | None = None              # "lever", "greenhouse", "ashby", "workable", or None
    open_roles: list[JobPosting] = []
    role_counts: dict[str, int] = {}             # {"ae": 8, "sdr": 1, ...}
    ae_to_sdr_ratio: float | None = None         # None if either count is 0
    linkedin_employee_count: int | None = None
    linkedin_job_count: int | None = None
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
    revenue_motion: "RevenueMotionData | None" = None    # new
```

Plus the bottom-of-file import and `model_rebuild()` to resolve the forward reference, matching the existing pattern for `pricing_packaging` and `tech_stack`.

### Collector (`rrxray/collectors/revenue_motion.py`)

Key functions:

- `_discover_careers_url(ctx)` — try `/careers`, `/jobs`, `/work-with-us`, `/join-us`. Return `(url, ScrapedPage)` or `(None, None)`.
- `_detect_ats(scraped_html)` — scan HTML for known ATS subdomain links. Return `(platform_name, ats_url)` or `(None, None)`.
- `_extract_roles(html, source)` — parse HTML for role titles. Match against `ROLE_KEYWORDS` to assign categories. Return `list[JobPosting]`.
- `_linkedin_search_jobs(firecrawl, domain)` — `firecrawl.search(f'site:linkedin.com/jobs/view "{domain}"', limit=10)`. Returns up to 10 LinkedIn job postings with titles. Each gets parsed for role category.
- `_linkedin_employee_count(firecrawl, domain)` — `firecrawl.search(f'"{domain}" employees site:linkedin.com/company', limit=3)`. Parse the snippet for "X employees" text. Return integer or None.
- `_compute_role_metrics(open_roles)` — aggregate counts per category, compute AE/SDR ratio.
- `_emit_findings(roles, role_counts, ratio, employee_count, ats_platform)` — rule-based findings/gaps/questions.
- `_write_evidence(evidence_dir, careers_html, ats_html, linkedin_search_responses)` — write `careers.html`, `ats.html` (if scraped), `linkedin_search_jobs.json`, `linkedin_search_employee_count.json`.
- `async collect(ctx)` — orchestrator following the Phase 2.1a pattern.

Graceful failure: if any individual sub-step fails (no careers page, LinkedIn search returns nothing, ATS link not followable), the collector continues with whatever data it has and emits findings explaining the absence.

### Synthesizer prompt update (`rrxray/prompts/observed_gtm_motion.md`)

Add a new conditional block alongside the existing pricing and tech stack blocks:

```jinja
{% if revenue_motion %}
**Revenue Motion signal**

- Careers page: {{ revenue_motion.careers_page_url or "not found" }}
- ATS platform: {{ revenue_motion.ats_platform or "not detected" }}
- Total open roles: {{ revenue_motion.open_roles | length }}

Role counts by category:
{% for category, count in revenue_motion.role_counts.items() %}
- {{ category }}: {{ count }}
{% endfor %}

AE-to-SDR ratio: {{ "%.1f" | format(revenue_motion.ae_to_sdr_ratio) if revenue_motion.ae_to_sdr_ratio is not none else "n/a (zero in one or both)" }}
LinkedIn employee count: {{ revenue_motion.linkedin_employee_count or "not detected" }}
LinkedIn job postings on LinkedIn Jobs: {{ revenue_motion.linkedin_job_count or "not detected" }}

Specific roles open right now:
{% for role in revenue_motion.open_roles[:15] %}
- [{{ role.category }}] {{ role.title }}{% if role.location %} ({{ role.location }}){% endif %}{% if role.source != "company_careers" %} (source: {{ role.source }}){% endif %}
{% endfor %}

Findings from the collector:
{% if revenue_motion.findings %}
{% for f in revenue_motion.findings %}
- {{ f.text }}
{% endfor %}
{% else %}
(none)
{% endif %}
{% else %}
**Revenue Motion signal:** not collected.
{% endif %}
```

Add `revenue_motion` to the framework guidance section so the LLM knows what to do with hiring data:

```markdown
**Revenue motion (hiring shape) tells you:**

- AE/SDR ratio > 4 = outbound under-resourced relative to AE coverage; pipeline likely AE-self-sourced or founder-led
- AE count > 0 + SDR count == 0 = top of funnel is founder/AE responsibility; signals early-stage or recently-shifted motion
- "First sales hire" / "Founding AE" titles = motion still founder-led, transitioning
- "Enterprise AE" titles = upmarket positioning regardless of pricing
- VP Sales / CRO / Head of Revenue posted = motion in transition (current leader gone or company growing)
- Marketing leadership posted with no marketing ops = building demand-gen function from scratch
- LinkedIn job count significantly different from careers page count = channel-specific recruiting (LinkedIn often has older/different roles)
```

### Synthesizer body update (`rrxray/synthesizers/observed_gtm_motion.py`)

```python
async def synthesize(ctx: SynthesizerContext) -> ObservedGtmMotionNarrative | None:
    pricing = ctx.collector_outputs.pricing_packaging
    tech_stack = ctx.collector_outputs.tech_stack
    revenue_motion = ctx.collector_outputs.revenue_motion    # NEW

    # Skip only when ALL Section A collectors absent
    if pricing is None and tech_stack is None and revenue_motion is None:
        log.info("All Section A collectors absent; skipping synthesis")
        return None

    # ... rest unchanged, but pass revenue_motion to _render_user_message ...
```

### Pipeline integration (`rrxray/pipeline.py`)

```python
from rrxray.collectors import pricing_packaging, tech_stack, revenue_motion    # add

COLLECTORS = [pricing_packaging, tech_stack, revenue_motion]                   # append
```

### Renderer template (`templates/report_internal.md.jinja`)

Add to the Module Detail Appendix section, after the Tech Stack block:

```jinja
{% if data.collectors.revenue_motion %}
### Revenue Motion

{% include "_revenue_motion_detail.md.jinja" %}
{% endif %}
```

The partial `templates/_revenue_motion_detail.md.jinja` renders the role table + LinkedIn signals + findings/gaps/questions, matching the shape of `_pricing_detail.md.jinja` and `_tech_stack_detail.md.jinja`.

---

## Data flow

```
CollectorContext (domain, firecrawl, evidence_dir, ...)
   ↓
revenue_motion.collect(ctx)
   ├─ _discover_careers_url(ctx) → (url, ScrapedPage) or (None, None)
   ├─ _detect_ats(scraped_html) → (platform, ats_url) or (None, None)
   ├─ if ats_url: ctx.firecrawl.scrape_url(ats_url) → ScrapedPage
   ├─ _extract_roles(careers_html, "company_careers") + _extract_roles(ats_html, "ats")
   ├─ _linkedin_search_jobs(ctx.firecrawl, domain) → list[JobPosting] (LinkedIn-source)
   ├─ _linkedin_employee_count(ctx.firecrawl, domain) → int | None
   ├─ _compute_role_metrics(open_roles) → role_counts, ae_to_sdr_ratio
   ├─ _emit_findings(...) → findings, gaps, discovery_questions
   ├─ _write_evidence(evidence_dir / "revenue_motion", ...)
   ↓
RevenueMotionData (validated by pydantic)
   ↓
returned to pipeline → assigned to CollectorOutputs.revenue_motion
   ↓
synthesizer reads ctx.collector_outputs.revenue_motion
   ↓
prompt template renders the Revenue Motion conditional block
   ↓
LLM produces Section A narrative reading across pricing + tech_stack + revenue_motion
```

---

## Error handling

- **No careers page found** → return `RevenueMotionData(careers_page_url=None, open_roles=[], findings=[Finding(text="No careers/jobs page discovered on standard paths")])`. Synthesizer reads this gracefully via the "Revenue Motion signal: not collected" fallback path.
- **ATS link found but scrape fails** → log warning, continue with company-careers data only.
- **LinkedIn search returns zero results** → set `linkedin_employee_count=None`, `linkedin_job_count=0`, continue.
- **`FirecrawlClient.search()` raises `FirecrawlError`** → caught at the LinkedIn-step level; collector continues with careers-page data only. Logged as a warning.
- **Total failure (FirecrawlError on the initial careers scrape)** → return graceful `RevenueMotionData` with a single finding noting the failure. No exception escapes.
- **`asyncio.CancelledError`** propagates (matches Phase 1's pattern).

---

## Testing

### Test files

- `tests/test_revenue_motion_catalog.py` — catalog integrity (all categories present, keywords compile as substring patterns, no duplicate categorizations)
- `tests/test_revenue_motion.py` — collector tests using synthetic HTML + mocked search responses
- `tests/test_firecrawl_client.py` — extended with tests for the new `search()` method

### New tests added

| Test | Verifies |
|---|---|
| `test_search_method_caches_result` | `FirecrawlClient.search()` deduplicates identical queries via DiskCache |
| `test_search_method_handles_firecrawl_error` | `FirecrawlError` propagates correctly from search |
| `test_search_method_returns_search_results` | Parsed `SearchResult` objects have url, title, description |
| `test_catalog_has_eight_role_categories` | All 8 categories named in `ROLE_CATEGORIES` |
| `test_catalog_keywords_match_typical_titles` | "Senior Account Executive" → ae; "BDR" → sdr; etc. |
| `test_discover_careers_url_at_slash_careers` | Standard `/careers` path discovered |
| `test_discover_careers_url_falls_back_to_slash_jobs` | Falls back to `/jobs` if `/careers` empty |
| `test_detect_ats_lever` | `jobs.lever.co/CompanyName` link in HTML detected |
| `test_detect_ats_greenhouse` | `boards.greenhouse.io/CompanyName` detected |
| `test_extract_roles_categorizes_titles` | Multi-title HTML produces correct categorization |
| `test_extract_roles_no_matches_returns_empty` | HTML with no role titles returns `[]` |
| `test_compute_metrics_ae_to_sdr_ratio` | 8 AEs + 1 SDR → ratio 8.0 |
| `test_compute_metrics_zero_division_safe` | 5 AEs + 0 SDRs → ratio None (not exception) |
| `test_linkedin_search_jobs_parses_results` | Mocked search response yields JobPosting list |
| `test_linkedin_employee_count_parses_snippet` | "247 employees" extracted from search snippet |
| `test_emit_findings_high_ae_to_sdr_ratio` | Ratio > 4 produces finding |
| `test_emit_findings_first_sales_hire` | Title containing "first" + AE → finding |
| `test_collect_writes_evidence` | All evidence files written |
| `test_collect_handles_firecrawl_error` | Graceful fallback when initial scrape fails |
| `test_collect_handles_linkedin_search_failure` | LinkedIn fails → continue with careers data |
| `test_collect_returns_revenue_motion_data` | Full happy path produces populated RevenueMotionData |

Plus updated synthesizer tests:

| Test | Verifies |
|---|---|
| `test_synth_runs_with_three_collectors` | When all three collectors present, synthesizer reads all three; user message has all three blocks |
| `test_synth_runs_with_revenue_motion_only` | Edge case: only revenue_motion present, others None |

Plus updated render tests:

| Test | Verifies |
|---|---|
| `test_revenue_motion_module_detail_renders_with_roles` | Tech Stack subsection renders the role table |
| `test_revenue_motion_module_detail_omits_when_no_collector` | Section absent when revenue_motion is None |

### Test fixtures

`tests/fixtures/synthetic/revenue_motion/`:
- `careers_simple.html` — 5 open roles with diverse titles
- `careers_with_ats_link.html` — careers page with a Lever link in the body
- `careers_empty.html` — careers page with no role listings
- `ats_lever.html` — Lever-style HTML with role listings
- `linkedin_jobs_response.json` — mocked Firecrawl search response for LinkedIn jobs
- `linkedin_employee_count_response.json` — mocked search response with "247 employees" snippet

---

## Phase 2.1c acceptance criteria

| # | Criterion | Verified by |
|---|---|---|
| 1 | `revenue_motion` collector exists and is registered in `pipeline.COLLECTORS` | `tests/test_revenue_motion.py::test_collector_registered` |
| 2 | `FirecrawlClient.search()` method works against synthetic responses | `tests/test_firecrawl_client.py::test_search_*` |
| 3 | Catalog has 8 categories with at least 5 keywords each | `tests/test_revenue_motion_catalog.py::test_catalog_*` |
| 4 | Careers page discovery handles `/careers`, `/jobs`, fallback paths | `test_discover_careers_url_*` |
| 5 | ATS detection identifies Lever / Greenhouse / Ashby / Workable links | `test_detect_ats_*` |
| 6 | Role extraction categorizes titles via the catalog | `test_extract_roles_categorizes_titles` |
| 7 | LinkedIn search returns parsed JobPostings + employee count | `test_linkedin_search_*` |
| 8 | Rule-based findings emit on observable patterns | `test_emit_findings_*` |
| 9 | Evidence files written with correct relative paths | `test_collect_writes_evidence` |
| 10 | `data.json` round-trips with `revenue_motion` populated | existing `test_data_json_round_trips` |
| 11 | Module Detail Appendix renders Revenue Motion subsection | `test_revenue_motion_module_detail_*` |
| 12 | Synthesizer reads `revenue_motion` from collector_outputs and includes it in the user message | `test_synth_runs_with_three_collectors` |
| 13 | Live smoke against Swayable / SQA / Linear produces a Section A narrative referencing hiring shape | manual review (Dale-led quality gate) |
| 14 | Quality gate signed off by Dale | manual review |

---

## Risks and known limitations

- **LinkedIn search via Google is best-effort.** Google's indexing of LinkedIn pages is patchy. Some queries return zero results even for active companies. The synthesizer should frame absence as itself a signal — "LinkedIn signal not recovered" — without treating it as collector failure. Phase 2.1c-fix may add Bing-search fallback if needed.
- **Role title heterogeneity.** "Founding Account Executive" → ae; "First Sales Hire" → ae but with a finding flag; "Sales Engineer" → ambiguous (could be AE-adjacent or other). The catalog will need expansion as we hit real domains. Mitigation: comprehensive smoke testing in the quality gate against three different motion types (Swayable's enterprise-style, SQA's services, Linear's PLG).
- **ATS detection covers four platforms.** Lever / Greenhouse / Ashby / Workable cover the majority of B2B SaaS but miss SmartRecruiters, BambooHR, Recruitee, JazzHR, and others. The collector will fall back to company-careers-only for those; not a defect, just lower coverage.
- **Pay-transparency-law-driven comp ranges are NOT extracted in this phase.** Many JDs include comp ranges due to CA/NY/CO/WA disclosure laws. Extracting those requires per-JD scraping (Phase 2.1c-deep, future cycle).
- **Firecrawl `search()` cost adds up.** Each domain run now does 2-3 search calls (LinkedIn jobs, employee count, optionally department breakdown). At Firecrawl's pricing this adds maybe $0.02 per run on top of the existing ~$0.04. Acceptable; will be modeled in the dry-run estimator.

---

## Out of scope but accommodated by the design

- Phase 2.1d's `content_demand` collector adds a fourth conditional block in the prompt (~30 lines of Jinja); no synthesizer change.
- Phase 2.2's `leadership_stability` collector reuses `FirecrawlClient.search()` for press release queries.
- Phase 2.3's `buyer_sentiment` collector reuses `FirecrawlClient.search()` for G2 / Reddit / Glassdoor queries.
- Phase 3's Gemini integration treats `revenue_motion` as just another collector output. No special-case wiring.

---

## Open questions

None at this time. All material decisions are locked.
