# rrxray Phase 2.2: leadership_stability Collector + observed_stability_trajectory Synthesizer Design

**Date:** 2026-05-09
**Status:** Approved (brainstorming complete)
**Phase:** 2.2 (first Section B sub-phase inside Phase 2)
**Builds on:** Phase 2.1c `revenue_motion` (commit `de297bf`, merged into `main`)

---

## Context

Section A reads from three collectors after Phase 2.1c (`pricing_packaging` + `tech_stack` + `revenue_motion`). Section B is greenfield. `leadership_stability` is the first Section B collector and ships alongside the new `observed_stability_trajectory` Section B synthesizer in this same phase.

Why ship the synthesizer with the first collector instead of waiting for two: the Section A precedent worked. Phase 1 shipped a pricing-only synthesizer; Phase 2.1a/b/c widened it. Doing the same for Section B forces us to nail the diagnostic posture, prompt design, and aggregation shape against real one-collector data before Phase 2.4+ adds `funding_trajectory` or `customer_concentration`. It also runs the quality-gate iteration loop earlier rather than later, where it has caught real issues across every Section A phase.

`leadership_stability` is the first collector that:

1. **Uses an LLM in the collector path.** Press release titles and LinkedIn snippets are unstructured natural language; deterministic regex extraction misses 30-50% of real phrasings. The Phase 2.1c "no LLM in collector path" rule is amended to "no LLM in collector path *unless the data is genuinely unstructured natural language and a deterministic alternative would degrade quality*." Per-result Haiku call at ~$0.0003/run is cheap and the determinism is preserved at the per-call level (structured-output enforcement).
2. **Ships a `GeminiClient` next to `AnthropicClient`.** No `services/llm.py` provider abstraction layer (deferred to Phase 3 per `roadmap.md` line 87); just two service classes side-by-side. A single `make_extractor(config)` factory picks one based on `config.extractor_model`. Phase 3 will refactor both classes into the abstraction together.
3. **Populates the anonymizer name registry.** Per `roadmap.md` line 44. Press-release names are whitelisted (already public); LinkedIn-only names are anonymized to role descriptors. Pipeline-side registration keeps the collector pure.

After this phase: Sections A and B both have synthesizers; `pipeline.SYNTHESIZERS` has two entries; the report renders both Section A and Section B narratives plus their Module Detail Appendix subsections.

---

## Scope

### In scope

- New collector module `rrxray/collectors/leadership_stability.py` plus role-canonicalization catalog `rrxray/collectors/_leadership_stability_catalog.py`
- New schema module `rrxray/schemas/leadership_stability.py` with `LeadershipStabilityData`, `ExecChange`, `CurrentIncumbent`, `FounderTenure`, `NameRegistration`
- New `GeminiClient` at `rrxray/services/gemini_client.py` exposing `complete_structured(system_prompt, user_message, response_schema, model="gemini-2.0-flash")`
- New extractor module `rrxray/services/extraction.py` with `HaikuExtractor`, `GeminiFlashExtractor`, `ExtractedExecChange`, `ExtractedLinkedInIncumbent`, and a `make_extractor()` factory function
- New `--extractor=haiku|gemini-flash` CLI flag plumbed into config; default is `haiku`
- Press release search via `FirecrawlClient.search()` — three per-action queries (`appoints OR names OR hires OR welcomes OR joins`, `departs OR resigns OR steps down`, `promoted OR promotion`), 18-month lookback, `limit=10` each
- LinkedIn current C-suite search via `FirecrawlClient.search()` — seven per-role queries (CEO, CRO, VP Sales, VP Revenue, CMO, VP Marketing, founder), `limit=3` each
- Founder tenure inference: `/about` page scrape with regex parse (`Founded in YYYY`, `Since YYYY`, `Founded YYYY`) → Wayback homepage oldest-snapshot fallback if no founding year detected
- Pipeline-side anonymizer registration: collector returns `name_registrations` on its schema; `pipeline.py` post-collection loop calls `anonymizer.register_individual()` and `anonymizer.whitelist_from_press()` per record
- Rule-based findings, gaps, and discovery questions emitted from the collector itself
- New synthesizer `rrxray/synthesizers/observed_stability_trajectory.py` with prompt template at `rrxray/prompts/observed_stability_trajectory.md`
- Synthesizer pre-aggregates `LeadershipStabilityData` into name-free `StabilityAggregates` before rendering the prompt
- New Jinja partial `templates/_leadership_stability_detail.md.jinja` for the Module Detail Appendix
- `leadership_stability: LeadershipStabilityData | None = None` field added to `CollectorOutputs`
- `observed_stability_trajectory: ObservedStabilityTrajectoryNarrative | None = None` field added to `SynthesizerOutputs`
- `leadership_stability` module appended to `pipeline.COLLECTORS`; `observed_stability_trajectory` appended to `pipeline.SYNTHESIZERS`
- `GEMINI_API_KEY` field added to `rrxray/config.py`
- Synthetic HTML + search-response fixture tests; no live API calls in unit tests
- Quality gate: 4-domain smoke (Swayable, SQA Services, Linear, plus one leadership-rich domain TBD by Dale at quality-gate time) + Dale-led prompt review

### Out of scope (future cycles)

- Wayback `/team` / `/about` / `/leadership` page diffing across snapshots — deferred per Q1 decision; Phase 2.2-deep or later if signal warrants
- Per-person LinkedIn profile scraping — login-walled
- `services/llm.py` provider abstraction layer — deferred to Phase 3 per `roadmap.md` line 87
- CFO / COO / CTO / CPO leadership tracking — narrowed scope in Q2; the GTM-relevant set is CEO + CRO + VP Sales + VP Revenue + CMO + VP Marketing + founder
- Press-release date precision better than the search result's reported date — many results don't expose a clear date in the snippet; we accept `occurred_at: date | None`
- Multi-language press release extraction — LLM extractor handles English well; non-English coverage is best-effort and known limitation
- Tenure precision better than year — months-in-role for current incumbents is approximate (computed from the most recent role-change press release if any; otherwise unknown)
- Section B's eventual full synthesizer (which will additionally read from `funding_trajectory` and `customer_concentration`) — Phase 2.2 ships the single-collector first version; future phases widen via additional conditional blocks (Phase 2.1c precedent)

---

## Decisions Locked During Brainstorming

| # | Decision | Choice | Rationale |
|---|---|---|---|
| Q1 | Cycle-1 scope | Press releases + LinkedIn current C-suite + founder tenure (defer Wayback /team diffing) | Three well-worn signal patterns; Wayback /team has inconsistent surface availability |
| Q2 | Leadership scope | GTM (CRO, VP Sales, VP Revenue, CMO, VP Marketing) + CEO + founder | CEO/founder are strongest leading indicators of GTM motion shift; CFO/CTO/COO churn rarely affects GTM diagnosis |
| Q3 | Press extraction approach | Pure LLM extraction; Haiku 4.5 default; `--extractor=gemini-flash` flag opt-in | Press release titles too varied for reliable regex; LLM with structured output is the right tool; rule amended |
| Q4 | Section B synthesizer | Build now, named `observed_stability_trajectory` | Section A precedent: ship synthesizer with first collector; forces prompt-design discipline early |
| Q5 | Lookback / recent thresholds | 18 months / ≤9 months ("recent" change triggers in-transition finding) | 18mo aligns with Wayback default; 9mo matches GTM practitioner intuition for motion-ripple period |
| Q6a | Synthesizer prompt input | Aggregate signals only; names never enter the prompt | Diagnostic value is the pattern, not biographies; prevents LLM drifting into biographical commentary |
| Q6b | Whitelisting policy | Press-release names whitelisted; LinkedIn-only names anonymized | Press releases are public communications; LinkedIn names get tighter discipline |
| Q6c | Registration timing | Collector returns `name_registrations` on schema; pipeline registers post-collection | Keeps collector pure; matches Phase 1 side-effect-orchestration pattern |
| Q7a | LinkedIn query structure | One search per role (~7 searches) | Tighter Google semantics than compound boolean; cost difference is trivial |
| Q7b | Founder tenure source | `/about` page parse (F1) → Wayback homepage oldest-snapshot fallback (F2) | F1 cleanest when present; F2 is a reasonable lower bound on company age |
| Q8a | Press release queries | Three per-action queries (hire / departure / promotion) | Per-action grouping plays well with Google indexing; per-role queries duplicate the LLM extractor's classification |
| Q8b | Quality gate domains | Swayable + SQA Services + Linear + one leadership-rich domain (Dale picks at quality-gate time) | Continuity for A/B regression check; fourth domain stress-tests Section B against actual instability |

---

## Architecture

### File layout (changes only)

```
NEW:
  rrxray/services/gemini_client.py                      [thin GeminiClient: complete_structured()]
  rrxray/services/extraction.py                         [LLMExtractor duck typing: HaikuExtractor + GeminiFlashExtractor + make_extractor()]
  rrxray/collectors/leadership_stability.py             [collector orchestrator: NAME, _search_*, _extract_*, _infer_founder_tenure, _build_name_registrations, _emit_findings, _write_evidence, collect()]
  rrxray/collectors/_leadership_stability_catalog.py    [LEADERSHIP_ROLES (7 entries) + PRESS_ACTION_QUERIES (3 entries) + thresholds]
  rrxray/schemas/leadership_stability.py                [LeadershipStabilityData, ExecChange, CurrentIncumbent, FounderTenure, NameRegistration, ExecAction, RoleCanonical]
  rrxray/synthesizers/observed_stability_trajectory.py  [Section B synthesizer + StabilityAggregates pre-aggregation]
  rrxray/prompts/observed_stability_trajectory.md       [Section B prompt template]
  templates/_leadership_stability_detail.md.jinja       [Module Detail Appendix partial]
  tests/test_leadership_stability.py                    [collector tests]
  tests/test_leadership_stability_catalog.py            [catalog integrity tests]
  tests/test_leadership_stability_schemas.py            [schema round-trip + validation]
  tests/test_observed_stability_trajectory.py           [synthesizer tests]
  tests/test_extraction.py                              [HaikuExtractor + GeminiFlashExtractor + make_extractor]
  tests/test_gemini_client.py                           [thin client tests with injected SDK factory]
  tests/fixtures/synthetic/leadership_stability/        [search responses + HTML + Wayback fixtures]

MODIFIED:
  rrxray/config.py                                       [add GEMINI_API_KEY field; add extractor_model: Literal["haiku", "gemini-flash"] = "haiku"]
  rrxray/cli.py                                          [add --extractor flag → config.extractor_model]
  rrxray/schemas/data.py                                 [add leadership_stability field on CollectorOutputs; add ObservedStabilityTrajectoryNarrative; add observed_stability_trajectory on SynthesizerOutputs; bottom-of-file imports + model_rebuild]
  rrxray/pipeline.py                                     [register collector in COLLECTORS; register synthesizer in SYNTHESIZERS; pipeline-side anonymizer registration loop]
  rrxray/context.py                                      [add gemini: GeminiClient | None on CollectorContext + SynthesizerContext; add extractor: HaikuExtractor | GeminiFlashExtractor on CollectorContext]
  templates/report_internal.md.jinja                     [include _leadership_stability_detail partial in Module Detail Appendix; render Section B synthesizer narrative]
  roadmap.md                                             [one-line entry under Phase 2.2 recording what shipped]
```

### Architectural notes

- **No `services/llm.py` abstraction layer.** `GeminiClient` and `AnthropicClient` are sibling service classes. The single `make_extractor(config, anthropic, gemini) -> HaikuExtractor | GeminiFlashExtractor` factory picks the concrete extractor at startup. Phase 3 introduces the formal abstraction; both clients refactor together at that time.
- **`LLMExtractor` is duck-typed**, not a formal `Protocol`. Each concrete class exposes the same two `async` methods: `extract_exec_change(title, snippet)` and `extract_linkedin_role(title, snippet, role_query)`. Type annotations use the union `HaikuExtractor | GeminiFlashExtractor` until Phase 3.
- **Collector remains pure.** Returns `name_registrations: list[NameRegistration]` on the schema. Pipeline iterates after collection and calls anonymizer side effects.
- **Pre-aggregation in synthesizer body, not in prompt template.** `StabilityAggregates` is computed in Python before `_render_user_message()` runs. The prompt template receives only aggregates + the collector's `findings` list. Names appear nowhere in the prompt.
- **`google-genai` is a new third-party dependency.** This is the official Gemini SDK. Listed here as a known scope addition; Dale signs off at spec review.

---

## Components

### `GeminiClient` (`rrxray/services/gemini_client.py`)

```python
class GeminiError(Exception):
    pass


class ParsedResponse(BaseModel):
    parsed: BaseModel
    model_used: str
    cache_hit: bool = False  # Gemini Flash doesn't expose cache state on this surface; always False in this phase


class GeminiClient:
    def __init__(
        self,
        api_key: str,
        _client_factory: Callable[[], Any] | None = None,
    ):
        """`_client_factory` is a test seam — production defaults to google-genai SDK client."""
        ...

    async def complete_structured(
        self,
        system_prompt: str,
        user_message: str,
        response_schema: type[BaseModel],
        model: str = "gemini-2.0-flash",
    ) -> ParsedResponse:
        """Structured-output completion. Wraps the google-genai SDK call.
        Raises GeminiError on SDK failure (retries handled by SDK; we surface terminal errors).
        """
        ...
```

The SDK return shape will need to be verified by the implementer (matches the Phase 2.1a discipline of `inspect`-then-adapt). If google-genai's structured-output mode returns a different envelope than expected, the implementer adapts and tests against the real shape.

### `LLMExtractor` (`rrxray/services/extraction.py`)

```python
class ExecAction(StrEnum):
    HIRE = "hire"
    DEPARTURE = "departure"
    PROMOTION = "promotion"


RoleCanonical = Literal[
    "ceo", "cro", "vp_sales", "vp_revenue",
    "cmo", "vp_marketing", "founder",
]


class ExtractedExecChange(BaseModel):
    name: str
    role_canonical: RoleCanonical
    role_raw: str
    action: ExecAction
    is_relevant: bool


class ExtractedLinkedInIncumbent(BaseModel):
    name: str
    role_canonical: RoleCanonical
    role_raw: str
    is_relevant: bool


class HaikuExtractor:
    def __init__(self, anthropic: AnthropicClient):
        self.anthropic = anthropic

    async def extract_exec_change(self, title: str, snippet: str) -> ExtractedExecChange | None:
        """Call Haiku 4.5 with structured output; return None on irrelevant or extraction failure."""
        ...

    async def extract_linkedin_role(
        self, title: str, snippet: str, role_query: str,
    ) -> ExtractedLinkedInIncumbent | None:
        ...


class GeminiFlashExtractor:
    def __init__(self, gemini: GeminiClient):
        self.gemini = gemini

    async def extract_exec_change(self, title: str, snippet: str) -> ExtractedExecChange | None:
        ...

    async def extract_linkedin_role(
        self, title: str, snippet: str, role_query: str,
    ) -> ExtractedLinkedInIncumbent | None:
        ...


def make_extractor(
    config: Config,
    anthropic: AnthropicClient,
    gemini: GeminiClient | None,
) -> HaikuExtractor | GeminiFlashExtractor:
    """Factory: picks extractor based on config.extractor_model.
    Raises ConfigError if extractor_model='gemini-flash' but gemini is None.
    """
    ...
```

Both extractors return `None` (rather than raising) on:

- LLM-emitted `is_relevant=False` results
- Pydantic validation failures on the structured response
- Underlying client errors (logged at debug level)

This contract lets the collector iterate over results without per-call try/except.

### Catalog (`rrxray/collectors/_leadership_stability_catalog.py`)

```python
LEADERSHIP_ROLES: list[tuple[str, str]] = [
    # (canonical, linkedin search keyword fragment)
    ("ceo",            '"CEO"'),
    ("cro",            '"CRO" OR "Chief Revenue Officer"'),
    ("vp_sales",       '"VP Sales" OR "VP of Sales" OR "Head of Sales"'),
    ("vp_revenue",     '"VP Revenue" OR "VP of Revenue" OR "Head of Revenue"'),
    ("cmo",            '"CMO" OR "Chief Marketing Officer"'),
    ("vp_marketing",   '"VP Marketing" OR "VP of Marketing" OR "Head of Marketing"'),
    ("founder",        '"Founder" OR "Co-founder"'),
]


PRESS_ACTION_QUERIES: list[tuple[str, str]] = [
    # (action label, query keywords)
    ("hire",      "appoints OR names OR hires OR welcomes OR joins"),
    ("departure", 'departs OR resigns OR "steps down" OR "stepping down"'),
    ("promotion", "promoted OR promotion"),
]


PRESS_LOOKBACK_MONTHS: int = 18
RECENT_THRESHOLD_DAYS: int = 270   # ~9 months


ROLE_DISPLAY: dict[str, str] = {
    "ceo":          "CEO",
    "cro":          "CRO",
    "vp_sales":     "VP Sales",
    "vp_revenue":   "VP Revenue",
    "cmo":          "CMO",
    "vp_marketing": "VP Marketing",
    "founder":      "founder",
}


FOUNDED_YEAR_PATTERNS: list[str] = [
    r"founded\s+in\s+(\d{4})",
    r"since\s+(\d{4})",
    r"founded\s+(\d{4})",
    r"established\s+in\s+(\d{4})",
    r"established\s+(\d{4})",
]
```

`ROLE_DISPLAY` is used to render `role_descriptor` (e.g., `"Acme's CRO"`) and to compose finding text where `<role display>` placeholders appear in the rules table below. Findings text rendering takes the form `f"{ROLE_DISPLAY[role_canonical]} {rest}"`.

The `<Company>` token in role descriptors comes from `ctx.config.company_name` if set; otherwise the collector derives a fallback from the domain (e.g., `"acme.com"` → `"Acme"`) using a simple title-case-of-first-domain-segment heuristic. The fallback is acceptable because the role descriptor is a display string, not a search key.

### Schema (`rrxray/schemas/leadership_stability.py`)

```python
"""Schemas specific to the leadership_stability collector."""
from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel

from rrxray.schemas._shared import Finding, SourceCitation


RoleCanonical = Literal[
    "ceo", "cro", "vp_sales", "vp_revenue",
    "cmo", "vp_marketing", "founder",
]


class ExecAction(StrEnum):
    HIRE = "hire"
    DEPARTURE = "departure"
    PROMOTION = "promotion"


class ExecChange(BaseModel):
    name: str
    role_canonical: RoleCanonical
    role_raw: str
    action: ExecAction
    occurred_at: date | None = None
    press_url: str
    press_title: str


class CurrentIncumbent(BaseModel):
    name: str
    role_canonical: RoleCanonical
    role_raw: str
    linkedin_url: str | None = None
    confidence: Literal["high", "low"] = "high"


class FounderTenure(BaseModel):
    inferred_year: int | None = None
    source: Literal["about_page", "wayback_homepage", "unknown"] = "unknown"
    raw_evidence: str | None = None


class NameRegistration(BaseModel):
    name: str
    role_descriptor: str
    whitelist: bool = False


class LeadershipStabilityData(BaseModel):
    exec_changes: list[ExecChange] = []
    current_incumbents: list[CurrentIncumbent] = []
    founder_tenure: FounderTenure | None = None
    name_registrations: list[NameRegistration] = []
    findings: list[Finding] = []
    gaps: list[str] = []
    discovery_questions: list[str] = []
    sources: list[SourceCitation] = []
```

### `data.py` integration

```python
class CollectorOutputs(BaseModel):
    model_config = ConfigDict(validate_assignment=True)
    pricing_packaging: "PricingPackagingData | None" = None
    tech_stack: "TechStackData | None" = None
    revenue_motion: "RevenueMotionData | None" = None
    leadership_stability: "LeadershipStabilityData | None" = None  # new


class ObservedStabilityTrajectoryNarrative(BaseModel):
    narrative_paragraphs: list[str]
    findings: list[Finding] = []
    gaps: list[str] = []
    discovery_questions: list[str] = []
    model_used: str
    cache_hit: bool


class SynthesizerOutputs(BaseModel):
    model_config = ConfigDict(validate_assignment=True)
    observed_gtm_motion: ObservedGtmMotionNarrative | None = None
    observed_stability_trajectory: ObservedStabilityTrajectoryNarrative | None = None  # new
```

Plus the bottom-of-file import + `model_rebuild()`, matching the existing pattern for `pricing_packaging` / `tech_stack` / `revenue_motion`.

### Collector (`rrxray/collectors/leadership_stability.py`)

```python
NAME = "leadership_stability"


async def collect(ctx: CollectorContext) -> LeadershipStabilityData:
    """Orchestrator. Steps below run in sequence; each handles its own errors gracefully."""
```

Internal helpers (all underscore-prefixed):

| Helper | Returns | Notes |
|---|---|---|
| `_search_press_releases(firecrawl, company)` | `list[SearchResult]` | 3 per-action queries, deduped by URL |
| `_extract_exec_changes(results, extractor)` | `list[ExecChange]` | Per-result `extractor.extract_exec_change`; filters `is_relevant=False`; parses dates from result metadata when present |
| `_search_linkedin_incumbents(firecrawl, company)` | `dict[str, list[SearchResult]]` | Keyed by `role_canonical`; 7 per-role queries |
| `_extract_current_incumbents(results_by_role, extractor)` | `list[CurrentIncumbent]` | Per-result extraction; dedup by `(role, name)`; top-confidence match per role |
| `_infer_founder_tenure(firecrawl, wayback, domain)` | `FounderTenure` | F1 path: scrape `/about`, regex against `FOUNDED_YEAR_PATTERNS`. F2 fallback: `wayback.snapshots(homepage_url, interval_months=12, span_months=120)`, take earliest snapshot year. Returns `source="unknown"` if both fail |
| `_build_name_registrations(exec_changes, incumbents, company)` | `list[NameRegistration]` | Press names: `whitelist=True`. LinkedIn-only names: `whitelist=False`. Dedup logic: same name in both → single record; press takes precedence (`whitelist=True` wins). Role descriptor format: `"<Company>'s <role display>"` (e.g., `"Acme's CRO"`) |
| `_emit_findings(exec_changes, incumbents, founder_tenure)` | `tuple[list[Finding], list[str], list[str]]` | Rule-based; see "Findings rules" below |
| `_write_evidence(evidence_dir, ...)` | `None` | Writes search responses, scraped pages, extractor outputs |

### Findings emission rules

| Pattern | Finding text shape |
|---|---|
| ≥2 changes in same seat in past 18 months | `"<role display> seat has turned over <N> times in the past 18 months → buyer-side ownership of the conversation may shift mid-cycle."` |
| 1 change in same seat ≤270 days ago | `"<role display> is in transition; current incumbent in seat ~<months> months → motion direction likely still being defined."` |
| Recent CRO/VP Sales hire AND concurrent VP Marketing/CMO hire (both ≤270 days) | `"Both revenue and marketing leadership turned over within 9 months → top-of-funnel and pipeline motion both being redesigned simultaneously."` |
| Founder tenure ≥7 years AND a current CEO incumbent matches the founder name | `"Founder-led for <N> years → decision authority concentrated; commitment risk on multi-quarter buying decisions is lower than at professionally-led peers."` |
| Founder tenure unknown AND zero current incumbents found | `"Leadership signal not recovered from public sources → discovery should establish leadership stability and recent change directly."` |
| LinkedIn returned ≥1 high-confidence current incumbent AND zero exec changes in past 18 months | `"No public exec announcements in past 18 months → leadership stability inferred (within the limits of public-record visibility)."` |

### Synthesizer (`rrxray/synthesizers/observed_stability_trajectory.py`)

Mirrors `observed_gtm_motion.py` structure exactly:

```python
NAME = "observed_stability_trajectory"


class StabilityAggregates(BaseModel):
    """Name-free pre-aggregation passed to the prompt template."""
    seat_changes: dict[str, int]                    # {"cro": 2, "cmo": 1, ...}
    recent_changes: list[dict]                      # [{"role": "cro", "action": "hire", "occurred_at_months_ago": 4}, ...]
    current_incumbents_by_role: dict[str, dict]     # {"cro": {"tenure_months": 7, "confidence": "high"}, ...}
    founder_present_in_ceo_seat: bool
    founder_tenure_years: int | None
    seats_with_no_change_18mo: list[str]
    collector_findings: list[str]


class NarrativeResponse(BaseModel):
    narrative_paragraphs: list[str] = Field(description="2-4 paragraphs committing to a stability/trajectory hypothesis")
    findings: list[Finding] = []
    gaps: list[str] = []
    discovery_questions: list[str] = []


def _build_aggregates(data: LeadershipStabilityData) -> StabilityAggregates: ...


def _render_user_message(domain: str, aggregates: StabilityAggregates) -> str:
    """Renders observed_stability_trajectory.md prompt template with name-free aggregates."""
    ...


async def synthesize(ctx: SynthesizerContext) -> ObservedStabilityTrajectoryNarrative | None:
    leadership = ctx.collector_outputs.leadership_stability
    if leadership is None:
        log.info("leadership_stability collector absent; skipping observed_stability_trajectory synthesis")
        return None

    aggregates = _build_aggregates(leadership)
    system_prompt = _load_system_prompt()
    user_message = _render_user_message(ctx.config.domain, aggregates)

    response = await ctx.anthropic.complete_with_cached_system(
        system_prompt=system_prompt,
        user_message=user_message,
        model=ctx.config.model,
        response_schema=NarrativeResponse,
    )

    # Voice post-processing: same two-step pattern as observed_gtm_motion
    def _voice(text: str, ctx_label: str) -> str:
        clean = ctx.voice.sanitize_llm_output(text, context=ctx_label)
        return ctx.voice.process_synthesizer_text(clean, context=ctx_label)

    paragraphs = [_voice(p, f"{NAME} para {i}") for i, p in enumerate(response.parsed.narrative_paragraphs)]
    gaps = [_voice(g, f"{NAME} gap {i}") for i, g in enumerate(response.parsed.gaps)]
    discovery_questions = [_voice(q, f"{NAME} discovery {i}") for i, q in enumerate(response.parsed.discovery_questions)]
    findings = [
        Finding(text=_voice(f.text, f"{NAME} finding {i}"), source=f.source)
        for i, f in enumerate(response.parsed.findings)
    ]

    return ObservedStabilityTrajectoryNarrative(
        narrative_paragraphs=paragraphs,
        findings=findings,
        gaps=gaps,
        discovery_questions=discovery_questions,
        model_used=response.model_used,
        cache_hit=response.cache_hit,
    )
```

### Synthesizer prompt (`rrxray/prompts/observed_stability_trajectory.md`)

The prompt commits the LLM to a stability-trajectory hypothesis (not enumeration). Section A's quality-gate iteration learned this pattern; Section B inherits it:

```
Domain: {{ domain }}

# Section B: Observed Stability and Trajectory

You are diagnosing the prospect's leadership stability and trajectory based on publicly observable signals.

You will receive aggregated leadership data — counts and tenures, never names. Do not invent names. Refer to roles by descriptor only ("the CRO", "the CEO", "the founder").

## Aggregated leadership signals

{# seat_changes, recent_changes, current_incumbents_by_role, founder_present_in_ceo_seat,
   founder_tenure_years, seats_with_no_change_18mo, collector_findings rendered here #}

## Diagnostic posture

Commit to a single hypothesis about this company's leadership stability and trajectory. Do not enumerate possibilities; pick the strongest read of the data and write it.

Possible hypotheses:
- **Stable, founder-led** — founder still in CEO seat with multi-year tenure, no recent exec changes
- **Stable, professionalized** — non-founder CEO with tenure, no recent changes
- **In active transition** — one or more recent exec changes (≤9 months); motion direction likely shifting
- **Unstable / churning** — multiple changes in same seat in past 18 months; motion uncertainty high
- **Signal not recovered** — public sources insufficient to commit to a hypothesis; discovery must establish

Output 2-4 paragraphs. Each paragraph commits to a specific observation and its diagnostic implication. Use → for recommendation bullets when applicable. Avoid em dashes; use commas, periods, or colons. Do not use the words: leverage, leveraging, leveraged, synergies, synergy, holistic, streamline, impactful. Use GTM Gap™ on first reference if relevant.

Also produce findings, gaps, and discovery questions if applicable.
```

The prompt does not list specific incumbent names, dates, or any natural-language signal that would let the LLM "guess" individual identities. Aggregates only.

### Pipeline integration (`rrxray/pipeline.py`)

```python
from rrxray.collectors import (
    pricing_packaging, tech_stack, revenue_motion, leadership_stability,
)
from rrxray.synthesizers import observed_gtm_motion, observed_stability_trajectory


COLLECTORS = [
    pricing_packaging,
    tech_stack,
    revenue_motion,
    leadership_stability,   # new
]

SYNTHESIZERS = [
    observed_gtm_motion,
    observed_stability_trajectory,   # new
]
```

Plus a post-collection loop that registers names with the anonymizer:

```python
# After the collector loop, before synthesis:
for collector_name, output in collector_outputs.model_dump().items():
    if not output:
        continue
    registrations = output.get("name_registrations") if isinstance(output, dict) else []
    for reg in registrations:
        anonymizer.register_individual(reg["name"], reg["role_descriptor"])
        if reg["whitelist"]:
            anonymizer.whitelist_from_press(reg["name"])
```

(The implementer adapts the exact iteration shape to fit existing `pipeline.py` conventions; the contract is "post-collection, registrations applied to the anonymizer.")

### CLI integration (`rrxray/cli.py`)

```python
@click.option(
    "--extractor",
    type=click.Choice(["haiku", "gemini-flash"]),
    default="haiku",
    help="LLM model to use for press-release / LinkedIn extraction in the leadership_stability collector.",
)
def run(domain: str, ..., extractor: str, ...) -> None:
    config = Config(
        domain=domain,
        extractor_model=extractor,
        ...
    )
    ...
```

The `--extractor` flag flows into `Config.extractor_model`; `make_extractor()` reads from there at startup.

### Renderer template (`templates/report_internal.md.jinja`)

Two changes:

1. Render the Section B narrative after Section A:
   ```jinja
   {% if data.synthesizers.observed_stability_trajectory %}
   ## Section B: Observed Stability and Trajectory

   {% for paragraph in data.synthesizers.observed_stability_trajectory.narrative_paragraphs %}
   {{ paragraph | anonymize }}

   {% endfor %}
   {% endif %}
   ```
2. Include the Module Detail Appendix partial:
   ```jinja
   {% if data.collectors.leadership_stability %}
   ### Leadership Stability

   {% include "_leadership_stability_detail.md.jinja" %}
   {% endif %}
   ```

The partial `templates/_leadership_stability_detail.md.jinja` renders the `exec_changes` table + `current_incumbents` table + `founder_tenure` line + findings/gaps/questions. Same shape as `_revenue_motion_detail.md.jinja`. All name-bearing fields are piped through the `anonymize` filter at render time; whitelisted press names pass through unchanged, LinkedIn-only names get replaced with role descriptors.

---

## Data flow

```
CollectorContext (domain, firecrawl, wayback, anthropic, gemini, extractor, anonymizer, evidence_dir, ...)
   ↓
leadership_stability.collect(ctx)
   ├─ _search_press_releases(firecrawl, company)
   │     [3 per-action queries × limit=10] → list[SearchResult] (deduped by URL)
   ├─ _extract_exec_changes(results, extractor)
   │     [extractor.extract_exec_change per result] → list[ExecChange]
   ├─ _search_linkedin_incumbents(firecrawl, company)
   │     [7 per-role queries × limit=3] → dict[role, list[SearchResult]]
   ├─ _extract_current_incumbents(results_by_role, extractor)
   │     [extractor.extract_linkedin_role per result] → list[CurrentIncumbent]
   ├─ _infer_founder_tenure(firecrawl, wayback, domain)
   │     ├─ F1: scrape /about → FOUNDED_YEAR_PATTERNS regex → FounderTenure(source="about_page")
   │     └─ F2 fallback: wayback.snapshots(homepage, 12mo, 120mo) → earliest year → source="wayback_homepage"
   ├─ _build_name_registrations(exec_changes, incumbents, company)
   │     [press: whitelist=True; LinkedIn-only: whitelist=False; dedupe by name]
   ├─ _emit_findings(exec_changes, incumbents, founder_tenure)
   ├─ _write_evidence(...)
   ↓
LeadershipStabilityData (validated by pydantic)
   ↓
returned to pipeline → assigned to CollectorOutputs.leadership_stability
   ↓
pipeline post-collection loop:
   for reg in data.name_registrations:
       anonymizer.register_individual(reg.name, reg.role_descriptor)
       if reg.whitelist:
           anonymizer.whitelist_from_press(reg.name)
   ↓
observed_stability_trajectory.synthesize(synthesizer_ctx)
   ├─ _build_aggregates(leadership) → StabilityAggregates (no names)
   ├─ _render_user_message(domain, aggregates) → prompt text
   ├─ anthropic.complete_with_cached_system(...)
   ├─ voice post-processing (sanitize_llm_output → process_synthesizer_text per string)
   ↓
ObservedStabilityTrajectoryNarrative
   ↓
renderer:
   - includes Section B narrative (anonymized at render time)
   - includes Module Detail Appendix Leadership Stability subsection
   ↓
anonymizer.assert_no_unanonymized(rendered) — defense-in-depth at render time
```

---

## Error handling

| Failure | Behavior | Findings impact |
|---|---|---|
| Firecrawl `search()` raises `FirecrawlError` on a press-action query | Log warning, continue with other action queries | If all 3 fail: emit "Press-release search unavailable; leadership-change signal not recovered" |
| Firecrawl `search()` raises on a LinkedIn role query | Log warning, continue with other role queries | Per-role missing data is normal; no special finding |
| Firecrawl `scrape_url()` raises on `/about` page | Skip F1, fall through to F2 (Wayback fallback) | `FounderTenure.source="wayback_homepage"` |
| Wayback `snapshots()` returns empty list | `FounderTenure(source="unknown")` | Emit "Founder tenure not inferable from public record" |
| Extractor (Haiku/Gemini) raises on a single result | Treat as `None` (skip that result), continue | None — individual extraction failures are expected and logged at debug level |
| Extractor returns malformed structured output (pydantic validation fails) | Caught at extractor layer; returns `None` | Same as above |
| Extractor's API key missing (e.g., `GEMINI_API_KEY` unset when `--extractor=gemini-flash`) | Raise `ConfigError` at startup, before pipeline runs | N/A — preflight failure; user fixes config and re-runs |
| All collection paths fail (press + LinkedIn + founder all empty) | Return `LeadershipStabilityData(findings=[Finding(text="Leadership stability signal not recovered; all public sources returned empty")])` | Synthesizer emits a narrative explaining the absence as itself a signal |
| `asyncio.CancelledError` | Propagates per Phase 1 pattern | N/A |

The collector matches the Phase 1 contract: it must not raise `FirecrawlError` / `WaybackError` / `GeminiError` / Anthropic errors to the pipeline. All such errors are caught at the sub-step level and converted into findings or graceful degradation.

---

## Voice processing

- **Collector-emitted text** (findings, gaps, discovery_questions): each string runs through `voice.process_collector_text()`. Substitutes forbidden words; inserts `GTM Gap™` trademark on first mention.
- **Synthesizer LLM output**: each generated string runs through `voice.sanitize_llm_output()` → `voice.process_synthesizer_text()`. Mirrors `observed_gtm_motion.py` exactly.
- **Section B prompt** instructs the LLM to avoid forbidden words, em dashes, and to use `GTM Gap™` on first mention. Same instruction set as Section A.

---

## Anonymizer integration

### What's new in Phase 2.2

This is the first collector to populate the anonymizer name registry. The mechanism (per `rrxray/voice/anonymizer.py`) is `register_individual(name, role_descriptor)` plus `whitelist_from_press(name)`.

### Policy

- **Press-release names** (every name extracted from the press search path): registered AND whitelisted. Logic: press releases are public communications; quoting "Acme appoints Jane Doe as CRO" verbatim from a published press release is fact-of-record and shouldn't be scrubbed.
- **LinkedIn-only names** (names extracted from LinkedIn search path that did NOT also appear in press): registered but NOT whitelisted. They get replaced with role descriptors at render time.
- **Names appearing in both sources**: single registration record; press takes precedence (`whitelist=True` wins).

### Synthesizer-side discipline

Names never enter the synthesizer prompt. The pre-aggregation step strips them out: `StabilityAggregates` contains role-level counts and tenures only. The LLM cannot accidentally emit a name it never saw.

### Defense in depth

`Anonymizer.assert_no_unanonymized(rendered)` already runs at render time (`rrxray/rendering/markdown.py:69`). Phase 2.2 doesn't change that. A new test `test_render_anonymizes_linkedin_names` exercises the full pipeline with one whitelisted press name + one non-whitelisted LinkedIn name and verifies both behaviors.

---

## Testing

### Test file inventory

| File | Scope |
|---|---|
| `tests/test_leadership_stability.py` | Collector orchestration + sub-step behavior |
| `tests/test_leadership_stability_catalog.py` | Catalog integrity |
| `tests/test_leadership_stability_schemas.py` | Schema round-trip + validation |
| `tests/test_observed_stability_trajectory.py` | Synthesizer aggregation + voice + LLM mock |
| `tests/test_extraction.py` | Both extractor classes + factory |
| `tests/test_gemini_client.py` | Thin Gemini client tests with injected SDK factory |

### Fixtures (`tests/fixtures/synthetic/leadership_stability/`)

- `press_search_hires_response.json` — Firecrawl search response with 4 hire results
- `press_search_departures_response.json` — 2 departure results
- `press_search_promotions_response.json` — 1 promotion result
- `linkedin_cro_response.json` — 2 high-confidence profile results
- `linkedin_cmo_response.json` — 1 low-confidence post URL
- `linkedin_empty_response.json` — Zero-result fixture
- `about_page_with_founding_year.html`
- `about_page_no_founding_year.html`
- `wayback_oldest_homepage.html`
- `extracted_exec_change_hire.json` / `_departure.json` / `_promotion.json` — Captured Haiku output for mocking the extractor

### Test inventory (named, ~50 tests total)

**Collector (`test_leadership_stability.py`):**

- `test_collector_registered_in_pipeline`
- `test_search_press_releases_runs_three_action_queries`
- `test_search_press_releases_dedupes_by_url`
- `test_extract_exec_changes_filters_irrelevant`
- `test_extract_exec_changes_handles_extractor_none`
- `test_search_linkedin_incumbents_runs_seven_role_queries`
- `test_extract_current_incumbents_dedupes_by_role_name`
- `test_extract_current_incumbents_takes_top_match_per_role`
- `test_infer_founder_tenure_about_page_path`
- `test_infer_founder_tenure_wayback_fallback`
- `test_infer_founder_tenure_unknown`
- `test_build_name_registrations_press_whitelisted`
- `test_build_name_registrations_linkedin_not_whitelisted`
- `test_build_name_registrations_dedupes`
- `test_build_name_registrations_role_descriptor_format`
- `test_emit_findings_seat_turnover`
- `test_emit_findings_recent_change`
- `test_emit_findings_concurrent_revenue_marketing`
- `test_emit_findings_founder_led_long_tenure`
- `test_emit_findings_no_press_signal`
- `test_emit_findings_total_signal_loss`
- `test_collect_writes_evidence`
- `test_collect_handles_press_search_failure`
- `test_collect_handles_linkedin_search_failure`
- `test_collect_handles_total_failure`
- `test_collect_returns_full_happy_path`
- `test_collect_excludes_names_from_synthesizer_visible_data`

**Catalog (`test_leadership_stability_catalog.py`):**

- `test_seven_canonical_roles`
- `test_three_action_query_groups`
- `test_role_search_keywords_quoted_correctly`

**Schemas (`test_leadership_stability_schemas.py`):**

- `test_leadership_stability_data_round_trips`
- `test_exec_change_validates_canonical_role`
- `test_name_registration_default_whitelist_false`

**Extractor (`test_extraction.py`):**

- `test_haiku_extractor_extracts_hire_announcement`
- `test_haiku_extractor_returns_none_on_irrelevant`
- `test_haiku_extractor_returns_none_on_pydantic_error`
- `test_gemini_flash_extractor_extracts_hire_announcement`
- `test_gemini_flash_extractor_returns_none_on_irrelevant`
- `test_make_extractor_picks_haiku_by_default`
- `test_make_extractor_picks_gemini_with_flag`
- `test_make_extractor_raises_when_gemini_key_missing`

**Gemini client (`test_gemini_client.py`):**

- `test_gemini_complete_structured_returns_parsed_response`
- `test_gemini_complete_structured_raises_on_sdk_error`
- `test_gemini_complete_structured_uses_injected_factory`

**Synthesizer (`test_observed_stability_trajectory.py`):**

- `test_synth_skips_when_collector_absent`
- `test_synth_runs_with_full_data`
- `test_synth_aggregates_exclude_names`
- `test_synth_voice_post_processing_applied`
- `test_synth_emits_finding_with_source_citation`
- `test_synth_handles_minimal_data`

**Pipeline (in existing test files):**

- `test_pipeline_registers_leadership_stability_name_registrations`
- `test_pipeline_collector_outputs_includes_leadership_stability`

**Renderer (in existing or extended test files):**

- `test_leadership_stability_module_detail_renders`
- `test_leadership_stability_module_detail_omits_when_no_collector`
- `test_render_anonymizes_linkedin_names`
- `test_render_preserves_whitelisted_press_names`

---

## Acceptance criteria

| # | Criterion | Verified by |
|---|---|---|
| 1 | `leadership_stability` collector exists, registered in `pipeline.COLLECTORS` | `test_collector_registered_in_pipeline` |
| 2 | `observed_stability_trajectory` synthesizer registered in `pipeline.SYNTHESIZERS` | new test in `test_pipeline.py` |
| 3 | `GeminiClient` and the two extractor classes work against mocked SDKs | `test_gemini_client.py`, `test_extraction.py` |
| 4 | `--extractor=gemini-flash` CLI flag picks `GeminiFlashExtractor` | new CLI integration test |
| 5 | Press releases extracted via 3 per-action queries; deduped by URL | `test_search_press_releases_*` |
| 6 | LinkedIn current C-suite extracted via 7 per-role queries | `test_search_linkedin_incumbents_*` |
| 7 | Founder tenure inferred via `/about` then Wayback fallback | `test_infer_founder_tenure_*` |
| 8 | Names registered correctly (press whitelisted; LinkedIn not) | `test_build_name_registrations_*` |
| 9 | Pipeline calls anonymizer post-collection per `name_registrations` | `test_pipeline_registers_leadership_stability_name_registrations` |
| 10 | Synthesizer aggregates contain zero registered names | `test_synth_aggregates_exclude_names`, `test_collect_excludes_names_from_synthesizer_visible_data` |
| 11 | Rule-based findings emitted on the named patterns | `test_emit_findings_*` |
| 12 | Evidence files written with correct relative paths | `test_collect_writes_evidence` |
| 13 | `data.json` round-trips with `leadership_stability` populated | `test_pipeline_collector_outputs_includes_leadership_stability` |
| 14 | Module Detail Appendix renders Leadership Stability subsection | `test_leadership_stability_module_detail_renders` |
| 15 | LinkedIn names anonymized; press names preserved at render time | `test_render_anonymizes_linkedin_names`, `test_render_preserves_whitelisted_press_names` |
| 16 | Live smoke against Swayable / SQA / Linear / one leadership-rich domain produces Section B narrative referencing leadership signal | manual review (Dale-led quality gate) |
| 17 | Synthesizer commits to a stability-trajectory hypothesis (does not enumerate possibilities) | manual review |
| 18 | Quality gate signed off by Dale | manual review |

---

## Cost ceiling

Per-domain estimate when everything fires:

- Firecrawl: 3 press + 7 LinkedIn + 1 `/about` scrape = 11 calls × $0.002 ≈ $0.022
- Wayback (fallback only): 0-3 calls (free)
- Extractor: ~30 results × $0.0003 (Haiku) ≈ $0.009; ~30 × $0.00003 (Gemini Flash) ≈ $0.0009
- Synthesizer: ~$0.01 (Sonnet 4.6 with prompt caching)

**Total: ~$0.04 per domain** with Haiku extractor; ~$0.03 with Gemini Flash. Adds maybe $0.025 over the existing per-run cost. Within budget; will be reflected in the dynamic dry-run estimator (which already reads `pipeline.COLLECTORS` / `SYNTHESIZERS`).

---

## Risks and known limitations

- **Press-release Google indexing is patchy.** Some companies' press releases live on PR newswire surfaces (PRNewswire, Business Wire) that Google indexes well; others publish only to their own newsroom subdirectory which may be poorly indexed. Mitigation: 3 action-query-keyword variants give us reasonable coverage; quality gate's leadership-rich domain stress-tests this.
- **LLM extractor hallucinates roles for ambiguous snippets.** A search result like `"Acme welcomes a new Chief"` could be over-extracted. Mitigation: structured-output `is_relevant: bool` field with explicit prompt instruction "only set is_relevant=True if both name and role are clearly stated."
- **LinkedIn snippet quality varies wildly.** Google's caching of LinkedIn pages is inconsistent. Some queries return zero results even for active executives. Mitigation: `confidence="low"` filter at synthesizer aggregation; output frames absence as "leadership signal not recovered" rather than "no leadership."
- **Founder tenure is a coarse signal.** `/about` page parse is regex-based and misses prose like "started in late 2018" or non-English founding-date copy. Mitigation: defaulting to Wayback fallback; in-narrative framing acknowledges the signal is approximate.
- **Gemini Flash structured output reliability.** Gemini's JSON-schema enforcement is less strict than Anthropic's. Mitigation: extractor catches pydantic validation error and returns `None` so individual bad extractions don't break the run. Quality gate will surface if this is materially worse than Haiku.
- **Renamed-entity press coverage.** Companies that recently changed names will have press releases under the old name; our search uses the current name. Documented limitation; quality-gate iteration may surface it.
- **Multi-language press releases.** LLM extractor handles English well; non-English coverage is best-effort. Documented limitation.
- **Date precision on `ExecChange.occurred_at`.** Search result snippets don't always expose a clear date; we accept `occurred_at: date | None`.
- **`google-genai` is a new third-party dependency.** Listed here for explicit Dale sign-off before implementation begins.

---

## Out of scope but accommodated by the design

- Phase 2.4+ Section B widening (`funding_trajectory`, `customer_concentration`) adds additional conditional blocks in the prompt and additional collector outputs read by the synthesizer; no synthesizer-shape change. Same pattern Phase 2.1c used.
- Phase 3's `services/llm.py` provider abstraction will subsume `AnthropicClient` + `GeminiClient` together. Both clients refactor at that time.
- Phase 3's hook outreach generator will likely reuse `GeminiClient` for its own extraction tasks; the client is generic.

---

## Open questions

None at this time. All material decisions are locked in the table above.
