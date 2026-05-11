# rrxray Phase 2.2-deep: PeopleDataLabs Leadership Enrichment Design

**Date:** 2026-05-11
**Status:** Approved (brainstorming complete)
**Phase:** 2.2-deep (follow-up to Phase 2.2 `leadership_stability`)
**Builds on:** Phase 2.2 (commits `0088e42` through `56857a8`, plus `1aad506` CLAUDE.md rule amendments)

---

## Context

Phase 2.2 shipped the `leadership_stability` collector and `observed_stability_trajectory` Section B synthesizer. The collector finds press release exec changes and current C-suite via LinkedIn snippet search, then synthesizes a Section B narrative. The single largest narrative quality gap surfaced in T16's quality gate: tenure data on current incumbents is rarely recoverable from LinkedIn search snippets, so the synthesizer punts to "tenure unconfirmed" gaps and discovery questions for information that other GTM intelligence tools routinely surface.

Dale explicitly called this out during Phase 2.2 sign-off: questions like "VP Sales tenure unconfirmed" should not appear as gaps because AI can answer them given the right data source. The "right data source" is a licensed leadership-data provider. After cost / accuracy / ToS-posture review, PeopleDataLabs (PDL) was approved as the one data partner for the leadership signal area, per the now-canonical "one approved data partner per signal area" rule in CLAUDE.md.

Phase 2.2-deep integrates PDL to close the tenure gap. The Phase 2.2 LinkedIn snippet path is removed (per Q2); PDL Person Search + Enrichment replaces it. Press change names also get PDL enrichment to surface prior employer / prior role / years-at-company context. Cost cap + circuit breaker keep PDL spend bounded.

After this phase: Section B incumbents have confirmed tenure data; the synthesizer cites "X of Y leaders have confirmed tenure" with specific months; prior-employer motion-lens reasoning produces diagnostic findings like "the incoming CRO came from Salesforce, suggesting motion may shift toward enterprise outbound." The "tenure unconfirmed" gap that motivated this phase is closed.

---

## Scope

### In scope

- New `PDLClient` at `rrxray/services/pdl_client.py` — sibling to `FirecrawlClient` / `AnthropicClient` / `GeminiClient`. Exposes `search_people(company_domain, role_titles)` → `list[PDLSearchResult]` and `enrich_person(linkedin_url | name+company)` → `PDLEnrichment | None`. Wraps the `peopledatalabs-python` SDK with the standard disk-cache + injectable factory test seam.
- New `LeadershipEnrichment` orchestrator at `rrxray/services/leadership_enrichment.py` — owns Search → Enrich chaining per role, dedup across roles, cost cap counter, circuit breaker, and graceful degradation. Two public methods: `find_and_enrich_incumbents(...)` (for current_incumbents) and `enrich_press_change_names(...)` (for press-detected exec changes).
- Schema extensions to `CurrentIncumbent` and `ExecChange`: `tenure_months`, `years_at_company`, `prior_employer`, `prior_role` (all optional). New `LeadershipEnrichmentMetadata` carrying `spend_dollars` + `aborted_reason`.
- `StabilityAggregates` extensions: `tenure_confirmed_count`, `tenure_confirmed_total`, `external_hire_count`, `internal_promotion_count`, `prior_employer_signals: dict[role, str | None]`.
- Synthesizer prompt template gets a new "Tenure confirmation" block + "Hire-origin pattern" block + "Prior employer per role" block + "Prior-employer motion lens" instruction block.
- Collector replaces LinkedIn snippet path with PDL incumbent path; press-name enrichment runs second; founder tenure path unchanged.
- `Config.pdl_api_key: SecretStr | None` and `Config.pdl_cost_cap_dollars: float = 5.0`. CLI `--pdl-cost-cap` and `--no-pdl` flags. `PDL_API_KEY` env var.
- Renderer Module Detail Appendix surfaces tenure_months + prior_employer per incumbent.
- Pipeline instantiates `PDLClient` + `LeadershipEnrichment` when `PDL_API_KEY` set; passes the orchestrator to `CollectorContext`.
- Existing `extraction.py` methods `extract_linkedin_role` deleted (now unused after LinkedIn snippet removal); `extract_exec_change` retained (press path still needs it).
- Existing LinkedIn fixtures (`linkedin_cro_response.json`, `linkedin_cmo_response.json`, `linkedin_empty_response.json`) deleted; PDL response fixtures added.
- Quality gate: Swayable + aioapp + remote.com, A/B comparison vs Phase 2.2 narratives. (Linear dropped; remote.com is closer to RR's actual customer profile and its generic-name pattern also stress-tests PDL Search disambiguation.)

### Out of scope (future cycles)

- Per-employee Wayback /team page diffing — deferred from Phase 2.2; not in scope for 2.2-deep
- Glassdoor / employee sentiment — Phase 2.3 buyer_sentiment territory
- Additional paid data partners (Coresignal, Proxycurl, Apollo) — rejected per CLAUDE.md "one approved data partner per signal area"
- LLM-based reasoning over education / seniority fields — deferred unless a future signal warrants
- Daily / weekly cache invalidation strategies — 30-day TTL is sufficient; tune later if signal drifts mid-cache become an issue
- PDL company-enrichment API for headcount / revenue band — separate signal area; out of scope here
- Per-record PDL cost surfaced to the user-facing report (only operational visibility in evidence/data.json)
- Synthesizer hardcoded model change — stays on Opus 4.7 per Phase 2.2 escalation

---

## Decisions Locked During Brainstorming

| # | Decision | Choice | Rationale |
|---|---|---|---|
| Q1 | PDL endpoints | Person Search + Person Enrichment combined | Search finds incumbents we'd miss with snippet-only; Enrichment fills tenure data on found incumbents. Search-only misses tenure; Enrichment-only misses incumbents PDL has but LinkedIn snippet didn't surface. |
| Q2 | LinkedIn snippet retention | Replaced entirely by PDL Search | Maintaining dual paths is dead code; PDL is approved infrastructure now. Fallback for missing PDL key is "no incumbents recovered" → "Signal Not Recovered" hypothesis (Phase 2.2 already handles this gracefully). |
| Q3 | Enrichment field set on schema | GTM-relevant: `tenure_months`, `years_at_company`, `prior_employer`, `prior_role` | Tenure closes the main gap; prior employer + role unlock motion-lens reasoning ("came from Salesforce" diagnostic). Education / seniority / raw experience deferred (interesting evidence but rarely move the narrative). |
| Q4 | Reliability + cost guardrails | Per-record graceful continue + 3-consecutive-failure circuit breaker + $5 hard cost cap, all preserving data already gathered | Cap defends against bug-induced runaway calls (Phase 2.2 caught one with Linear's common-name disambiguator). Circuit breaker defends against PDL outage mid-run. Graceful degradation means the X-Ray still ships partial data when PDL exhaustion hits — preserves work already paid for. |
| Q5 | Cache policy | 30-day disk cache by `(linkedin_url)` for Enrichment and `(company_domain, role_titles)` for Search; bypass via `--no-cache` | Matches existing Firecrawl/Anthropic disk-cache pattern. Re-renders of an X-Ray (e.g., prompt iteration on the synthesizer) are ~free. Tenure drift over 30 days is one month — acceptable. |
| Q6 | Enrichment scope | Both current incumbents AND press change names | Press names get prior_employer / years_at_company too — catches "incoming CRO came from PLG company → motion may shift toward product-led pipeline" diagnostic. Adds ~$1.00 to per-X-Ray ceiling for material narrative lift. |
| Q7 | Synthesizer aggregates | Raw fields + derived counts (tenure_confirmed_count, external_hire_count, internal_promotion_count, prior_employer_signals) | Matches Phase 2.2 `StabilityAggregates` pattern. LLM gets specific numbers to cite without recounting raw lists; interpretation (motion-shape inference) stays in the LLM where prompt iteration can refine it. |
| Q8 | Quality gate domains | Swayable + aioapp + remote.com | A/B continuity with Phase 2.2 on Swayable + aioapp (ICP-aligned). Remote.com replaces Linear: closer to RR target customer profile AND its generic name stress-tests PDL Search disambiguation. |

---

## Architecture

### File layout (changes only)

```
NEW:
  rrxray/services/pdl_client.py                      [PDLClient + PDLSearchResult + PDLEnrichment + PDLError]
  rrxray/services/leadership_enrichment.py           [LeadershipEnrichment orchestrator + EnrichedLeadership]
  tests/test_pdl_client.py                           [client tests against mocked SDK]
  tests/test_leadership_enrichment.py                [orchestrator tests: cost cap, circuit breaker, dedup, partial-data return]
  tests/fixtures/synthetic/leadership_stability/
    pdl_search_cro_response.json
    pdl_search_no_match_response.json
    pdl_enrich_external_hire.json
    pdl_enrich_internal_promotion.json
    pdl_enrich_long_tenure.json
    pdl_enrich_minimal.json

MODIFIED:
  pyproject.toml                                     [add peopledatalabs-python dependency]
  rrxray/config.py                                   [add pdl_api_key + pdl_cost_cap_dollars]
  rrxray/cli.py                                      [add --pdl-cost-cap + --no-pdl flags]
  rrxray/context.py                                  [add leadership_enrichment field on CollectorContext]
  rrxray/schemas/leadership_stability.py             [extend CurrentIncumbent + ExecChange + add LeadershipEnrichmentMetadata]
  rrxray/collectors/leadership_stability.py          [DELETE _search_linkedin_incumbents + _extract_current_incumbents + _confidence_for_linkedin_url; REPLACE with leadership_enrichment.find_and_enrich_incumbents call; ADD press-change enrichment after _extract_exec_changes]
  rrxray/services/extraction.py                      [DELETE extract_linkedin_role on both extractors + _LINKEDIN_INCUMBENT_SYSTEM_PROMPT; KEEP extract_exec_change]
  rrxray/synthesizers/observed_stability_trajectory.py [extend StabilityAggregates + _build_aggregates to compute new derived fields]
  rrxray/prompts/observed_stability_trajectory.md    [add Tenure confirmation block + Hire-origin block + Prior employer signals block + Prior-employer motion-lens instruction]
  rrxray/pipeline.py                                 [instantiate PDLClient + LeadershipEnrichment when PDL_API_KEY set; pass to CollectorContext]
  templates/_leadership_stability_detail.md.jinja    [render new tenure / prior_employer / prior_role / years_at_company per-incumbent]
  roadmap.md                                         [one-line Phase 2.2-deep entry post-quality-gate]

DELETED:
  tests/fixtures/synthetic/leadership_stability/linkedin_cro_response.json
  tests/fixtures/synthetic/leadership_stability/linkedin_cmo_response.json
  tests/fixtures/synthetic/leadership_stability/linkedin_empty_response.json
```

### Architectural notes

- **`PDLClient` matches existing service pattern.** Constructor takes `api_key`, `cache: DiskCache`, optional `_sdk_factory` test seam. Two async methods (`search_people`, `enrich_person`). Production wraps the `peopledatalabs-python` SDK; tests inject a fake. Same shape as `GeminiClient`.
- **`LeadershipEnrichment` is the orchestration helper.** Collector calls one method per phase (incumbent path + press-name path). The orchestrator owns the cost-cap counter, circuit breaker state, and the Search → Enrich chain. The collector stays simple.
- **No new abstraction layer.** PDL is a sibling service, not part of a generic data-partner provider abstraction. Phase 3+ may unify multiple paid providers under one interface; until then, single concrete class.
- **LinkedIn snippet code is removed entirely** (per Q2). The `extract_linkedin_role` extractor methods + `_LINKEDIN_INCUMBENT_SYSTEM_PROMPT` are deleted because they have no remaining caller. `extract_exec_change` stays — press path unchanged.
- **`peopledatalabs-python` is a new third-party dependency.** Approved by Dale at spec time per the canonical "one approved data partner per signal area" rule in CLAUDE.md.

---

## Components

### `PDLClient` (`rrxray/services/pdl_client.py`)

```python
class PDLError(Exception):
    pass


class PDLSearchResult(BaseModel):
    full_name: str
    linkedin_url: str | None
    current_title: str
    job_company_name: str | None
    job_start_date: str | None         # YYYY-MM-DD when available
    match_score: float                  # PDL's relevance score


class PDLEnrichment(BaseModel):
    full_name: str
    linkedin_url: str | None
    current_title: str
    job_company_name: str | None
    job_start_date: str | None
    job_company_size: str | None        # PDL band, e.g., "1001-5000"
    previous_companies: list[str] = []  # company names, reverse chrono
    previous_titles: list[str] = []     # titles, reverse chrono
    experience: list[dict] = []         # full raw position history (preserved for evidence)


class PDLClient:
    def __init__(
        self,
        api_key: str,
        cache: DiskCache,
        _sdk_factory: Callable[[], Any] | None = None,
    ): ...

    async def search_people(
        self, company_domain: str, role_titles: list[str], size: int = 3,
    ) -> list[PDLSearchResult]:
        """Person Search by (company_domain, role_titles). Returns ranked matches.
        Caches by (company_domain, role_titles_sorted, size); 30-day TTL.
        Raises PDLError on terminal SDK failure.
        """
        ...

    async def enrich_person(
        self,
        linkedin_url: str | None = None,
        name: str | None = None,
        company_domain: str | None = None,
    ) -> PDLEnrichment | None:
        """Person Enrichment. Prefers linkedin_url; falls back to (name, company_domain).
        Returns None on PDL "no match" (200 with empty data, NOT an error).
        Raises PDLError on terminal SDK failure.
        Caches by linkedin_url (preferred) or (name, company_domain).
        """
        ...
```

SDK return-shape verification at implementation time matches the Phase 2.1a "inspect-then-adapt" discipline.

### `LeadershipEnrichment` orchestrator (`rrxray/services/leadership_enrichment.py`)

```python
PDL_COST_PER_SEARCH = 0.20
PDL_COST_PER_ENRICHMENT = 0.20
CIRCUIT_BREAKER_CONSECUTIVE_FAILURES = 3


class EnrichedLeadership(BaseModel):
    incumbents: list[CurrentIncumbent]
    spend_dollars: float
    aborted_reason: Literal["completed", "cost_cap", "circuit_breaker"] = "completed"


class LeadershipEnrichment:
    def __init__(self, pdl: PDLClient, cost_cap_dollars: float):
        self.pdl = pdl
        self.cost_cap_dollars = cost_cap_dollars
        self._spend = 0.0
        self._consecutive_failures = 0
        self._circuit_open = False

    def _can_spend(self, cost: float) -> bool: ...
    def _record_success(self, cost: float) -> None: ...
    def _record_failure(self) -> None: ...

    async def find_and_enrich_incumbents(
        self,
        company_name: str,
        company_domain: str,
        role_canonicals: list[tuple[str, list[str]]],
    ) -> EnrichedLeadership:
        """Per role: PDL Search for matches → take top match by score → PDL Enrich by linkedin_url.
        Dedup across roles by linkedin_url (founder appearing as CEO + Founder is one Enrich call).
        Per-role failure isolated (logged, continues with next role).
        Returns whatever data was gathered before cap / circuit breaker fired."""
        ...

    async def enrich_press_change_names(
        self,
        exec_changes: list[ExecChange],
        company_domain: str,
    ) -> list[ExecChange]:
        """Per ExecChange: PDL Enrich by (name, company_domain).
        Returns the input list with prior_employer / prior_role / years_at_company filled where PDL had matches.
        Shares cost-cap state with find_and_enrich_incumbents (which runs first)."""
        ...

    @property
    def metadata(self) -> LeadershipEnrichmentMetadata:
        """Snapshot of current orchestrator state for evidence + reporting."""
        ...
```

The orchestrator is constructed once per pipeline run; both methods share the same cost cap + circuit-breaker state.

### Schema extensions (`rrxray/schemas/leadership_stability.py`)

```python
class CurrentIncumbent(BaseModel):
    name: str
    role_canonical: RoleCanonical
    role_raw: str
    linkedin_url: str | None = None
    confidence: Literal["high", "low"] = "high"
    # NEW Phase 2.2-deep enrichment fields
    tenure_months: int | None = None
    years_at_company: int | None = None
    prior_employer: str | None = None
    prior_role: str | None = None


class ExecChange(BaseModel):
    name: str
    role_canonical: RoleCanonical
    role_raw: str
    action: ExecAction
    occurred_at: date | None = None
    press_url: str
    press_title: str
    # NEW Phase 2.2-deep enrichment fields (populated for press-name enrichment)
    prior_employer: str | None = None
    prior_role: str | None = None
    years_at_company: int | None = None


class LeadershipEnrichmentMetadata(BaseModel):
    spend_dollars: float = 0.0
    aborted_reason: Literal["completed", "cost_cap", "circuit_breaker", "disabled"] = "disabled"


class LeadershipStabilityData(BaseModel):
    # ... existing fields ...
    enrichment_metadata: LeadershipEnrichmentMetadata = Field(default_factory=LeadershipEnrichmentMetadata)
```

### Synthesizer aggregates additions (`rrxray/synthesizers/observed_stability_trajectory.py`)

```python
class StabilityAggregates(BaseModel):
    # ... existing fields ...
    # NEW Phase 2.2-deep
    tenure_confirmed_count: int                  # incumbents with non-None tenure_months
    tenure_confirmed_total: int                  # total high-confidence incumbents (denominator for "X of Y")
    external_hire_count: int                     # prior_employer set AND ≠ current company
    internal_promotion_count: int                # prior role at the same company
    prior_employer_signals: dict[str, str | None]  # {role_canonical: prior_employer | None}
```

The `_build_aggregates` function computes the new derived fields by iterating over `data.current_incumbents` once with `confidence == "high"` filter. Algorithm in Section 3 of brainstorming notes; copied verbatim into the implementer task.

### Synthesizer prompt additions (`rrxray/prompts/observed_stability_trajectory.md`)

Three new data blocks rendered in the user message:

```jinja
**Tenure confirmation:** {{ aggregates.tenure_confirmed_count }} of {{ aggregates.tenure_confirmed_total }} current incumbents have tenure data confirmed via PeopleDataLabs.

**Hire-origin pattern:**
- External hires (incumbents who came from outside the company): {{ aggregates.external_hire_count }}
- Internal promotions (incumbents promoted from within): {{ aggregates.internal_promotion_count }}

**Prior employer per role (where confirmed):**
{% for role, prior in aggregates.prior_employer_signals.items() %}
{% if prior %}
- {{ role }}: came from {{ prior }}
{% else %}
- {{ role }}: prior employer not recovered
{% endif %}
{% endfor %}
```

One new instruction block after the diagnostic-posture section:

```
**Prior-employer motion lens:** When you see a prior_employer for a revenue or marketing role, infer the motion shape that incumbent likely brings:
- Came from an enterprise SaaS (Salesforce, Oracle, etc.) → likely enterprise outbound motion bias
- Came from a PLG company (Figma, Notion, etc.) → likely product-led pipeline bias
- Came from a smaller startup / unknown → bias unclear; do not speculate
- Came from the same vertical → motion stays domain-aligned; market expertise > motion shift
This is a working hypothesis only — state it as such ("the incoming CRO came from X, suggesting...") rather than as a confirmed fact.
```

### CLI additions (`rrxray/cli.py`)

```python
@app.command()
def run(
    ...,
    pdl_cost_cap: float = typer.Option(
        5.0, "--pdl-cost-cap",
        help="Hard ceiling on PDL spend per X-Ray, in USD."
    ),
    no_pdl: bool = typer.Option(
        False, "--no-pdl",
        help="Disable PDL enrichment entirely for this run. Falls through to 'Signal Not Recovered' for current incumbents."
    ),
):
    ...
```

### Pipeline wiring (`rrxray/pipeline.py`)

```python
from rrxray.services.leadership_enrichment import LeadershipEnrichment
from rrxray.services.pdl_client import PDLClient

def build_collector_context(config) -> CollectorContext:
    # ... existing firecrawl + wayback + anthropic + gemini construction ...

    leadership_enrichment = None
    if not config.no_pdl and config.pdl_api_key is not None:
        pdl = PDLClient(
            api_key=config.pdl_api_key.get_secret_value(),
            cache=DiskCache(dir=cache_root / "pdl", mode="live" if config.use_cache else "refresh"),
        )
        leadership_enrichment = LeadershipEnrichment(
            pdl=pdl,
            cost_cap_dollars=config.pdl_cost_cap_dollars,
        )

    return CollectorContext(
        # ... existing fields ...
        leadership_enrichment=leadership_enrichment,
    )
```

`CollectorContext` gets one new optional field `leadership_enrichment: LeadershipEnrichment | None = None`.

### Renderer template additions (`templates/_leadership_stability_detail.md.jinja`)

The "Current incumbents" table grows two columns:

```jinja
| Role | Name | Tenure | Prior | LinkedIn |
|---|---|---|---|---|
{% for inc in ls.current_incumbents %}
| {{ inc.role_canonical }} | {{ inc.name | anonymize | voice_collector }} | {% if inc.tenure_months %}~{{ inc.tenure_months }} months{% else %}unconfirmed{% endif %} | {% if inc.prior_employer %}{{ inc.prior_employer }} ({{ inc.prior_role or "unspecified role" }}){% else %}-{% endif %} | {% if inc.linkedin_url %}[link]({{ inc.linkedin_url }}){% else %}-{% endif %} |
{% endfor %}
```

The "Exec changes" table gets a "Background" column for press-enriched names:

```jinja
| Role | Action | Name | Date | Background | Source |
{% for change in ls.exec_changes %}
| {{ change.role_canonical }} | {{ change.action }} | {{ change.name | anonymize | voice_collector }} | {{ change.occurred_at or "-" }} | {% if change.prior_employer %}from {{ change.prior_employer }}{% else %}-{% endif %} | [press]({{ change.press_url }}) |
{% endfor %}
```

A new "Enrichment status" line below the tables:

```jinja
**Enrichment:** ${{ "%.2f"|format(ls.enrichment_metadata.spend_dollars) }} spent; status: {{ ls.enrichment_metadata.aborted_reason }}.
```

---

## Data flow

```
CollectorContext (now includes leadership_enrichment: LeadershipEnrichment | None)
   ↓
leadership_stability.collect(ctx)
   │
   ├─ Press path (UNCHANGED from Phase 2.2)
   │     ├─ _search_press_releases(firecrawl, company)
   │     ├─ _extract_exec_changes(results, extractor, company, domain, firecrawl)
   │     └─ → list[ExecChange] with occurred_at when extractable
   │
   ├─ PDL incumbent path (NEW — replaces LinkedIn snippet path)
   │     ├─ if ctx.leadership_enrichment is None: incumbents = [], metadata.aborted_reason = "disabled"
   │     ├─ else:
   │     │     enriched = await ctx.leadership_enrichment.find_and_enrich_incumbents(
   │     │         company_name=company, company_domain=ctx.domain,
   │     │         role_canonicals=LEADERSHIP_ROLES,
   │     │     )
   │     │     incumbents = enriched.incumbents
   │     │     metadata = LeadershipEnrichmentMetadata(
   │     │         spend_dollars=enriched.spend_dollars,
   │     │         aborted_reason=enriched.aborted_reason,
   │     │     )
   │     └─ → list[CurrentIncumbent] with tenure_months / years_at_company / prior_employer / prior_role
   │
   ├─ PDL press-name enrichment (NEW)
   │     ├─ if ctx.leadership_enrichment is None OR exec_changes empty: pass
   │     ├─ else:
   │     │     exec_changes = await ctx.leadership_enrichment.enrich_press_change_names(
   │     │         exec_changes=exec_changes, company_domain=ctx.domain,
   │     │     )
   │     │     # Mutated copies with prior_employer / prior_role / years_at_company
   │     │     # Shared cost-cap with incumbent path; incumbent budget already deducted
   │     └─ → list[ExecChange] possibly enriched
   │
   ├─ Founder tenure path (UNCHANGED)
   ├─ _build_name_registrations(exec_changes, incumbents, company)
   ├─ _emit_findings(exec_changes, incumbents, founder_tenure)
   ├─ _write_evidence(...)  # NEW: also writes pdl_search.json + pdl_enrichment.json
   ↓
LeadershipStabilityData (with enrichment_metadata field populated)
   ↓
pipeline post-collection (UNCHANGED):
   - _register_collector_names → anonymizer.register_individual + whitelist_from_press
   ↓
observed_stability_trajectory.synthesize(ctx)
   ├─ _build_aggregates(data)
   │     - existing logic
   │     - PLUS: tenure_confirmed_count, external_hire_count, internal_promotion_count, prior_employer_signals
   ├─ _render_user_message(domain, aggregates, enrichment_status)
   │     # Prompt now includes: tenure confirmation block, hire-origin block,
   │     # prior employer signals block, motion-lens instruction
   ├─ anthropic.complete_with_cached_system (model: claude-opus-4-7)
   ├─ voice post-processing (unchanged)
   ↓
ObservedStabilityTrajectoryNarrative (richer; LLM cites tenure_confirmed_count, motion-lens inferences)
   ↓
renderer:
   - Module Detail Appendix: tables now show tenure + prior_employer
   - Enrichment metadata line shows spend + aborted_reason
   - anonymizer.assert_no_unanonymized() at render time (UNCHANGED defense-in-depth)
```

---

## Error handling

| Failure | Behavior | Findings impact |
|---|---|---|
| `PDLError` on a single search call | `_record_failure()`; return `None` for that role; continue | Per-role incumbent stays unrecovered |
| `PDLError` on a single enrichment call | Same; return the un-enriched `CurrentIncumbent` (name + linkedin_url, tenure fields None) | Synthesizer cites tenure_confirmed_count < total |
| 3+ consecutive failures | Circuit breaker opens; remaining PDL calls short-circuit to `None` | Narrative notes "leadership enrichment partial — PDL unavailable mid-run" |
| Cost cap reached | Further calls short-circuit; preserved data preserved; `aborted_reason = "cost_cap"` | Synthesizer notes partial enrichment |
| `PDL_API_KEY` missing at startup | Pipeline doesn't instantiate `LeadershipEnrichment`; `ctx.leadership_enrichment is None` | Collector skips PDL entirely; "Signal Not Recovered" hypothesis |
| `--no-pdl` flag set | Same as missing API key | Same |
| PDL returns empty match (no error) | Return `None` for that role; do NOT increment failure counter | Per-role gap; expected when PDL has no record |
| `asyncio.CancelledError` | Propagates per project pattern | N/A |
| Pydantic validation error on PDL response | Caught at `PDLClient`; logged; raises `PDLError` to orchestrator | Per-role failure path engages |

---

## Voice processing

Same pattern as Phase 2.2:

- **Collector findings**: run through `voice.process_collector_text()` (unchanged Phase 2.2 wiring)
- **Synthesizer LLM output**: `voice.sanitize_llm_output()` → `voice.process_synthesizer_text()` (unchanged)
- **Section B prompt**: same forbidden-word list, em-dash policy, GTM Gap™ trademark instructions (unchanged)
- **Anonymizer**: PDL-found names are anonymized to role descriptors at render time (NOT whitelisted; same policy as Phase 2.2's LinkedIn-only names). Press-found names remain whitelisted via the press path.

No new voice processing logic. PDL is just another upstream data source; the existing voice + anonymizer chain handles its output.

---

## Anonymizer integration

Unchanged from Phase 2.2 conceptually. The name registration policy:

- Names found via the **press path** → registered with `whitelist=True` (already public via press release)
- Names found via **PDL Search/Enrichment but NOT in press** → registered with `whitelist=False` (anonymized to role descriptor at render time)
- Same name in both → press wins (whitelist=True)

`_build_name_registrations(exec_changes, current_incumbents, company)` logic is unchanged. The data sources are different (PDL replaces LinkedIn snippet for current_incumbents) but the anonymizer interaction is the same.

---

## Testing

### New test files

| File | Scope |
|---|---|
| `tests/test_pdl_client.py` | PDLClient search + enrich + cache + error paths against mocked SDK |
| `tests/test_leadership_enrichment.py` | Orchestrator: search→enrich chain, cost cap, circuit breaker, dedup, partial-data return |

### Modified test files

| File | Change |
|---|---|
| `tests/test_leadership_stability.py` | Remove LinkedIn-snippet path tests (4-5 tests deleted); add PDL incumbent-path + press-enrichment tests |
| `tests/test_extraction.py` | Remove `extract_linkedin_role` tests (method deleted) |
| `tests/test_observed_stability_trajectory.py` | Add tests for new aggregate fields |
| `tests/test_render_internal.py` | Render new tenure / prior_employer columns + enrichment metadata line |
| `tests/test_pipeline.py` | PDLClient + orchestrator instantiation conditional on PDL_API_KEY |
| `tests/test_config.py` | New `pdl_api_key` + `pdl_cost_cap_dollars` fields |
| `tests/test_cli.py` | New `--pdl-cost-cap` + `--no-pdl` flags |

### Fixtures

New PDL response fixtures (6 files) listed in "File layout" above. Old LinkedIn fixtures (3 files) deleted.

### Test inventory (~40 new tests)

**PDLClient (`test_pdl_client.py`):**

- `test_search_people_returns_search_results`
- `test_search_people_caches_by_company_and_role`
- `test_search_people_raises_on_sdk_error`
- `test_search_people_handles_empty_match`
- `test_enrich_person_by_linkedin_url`
- `test_enrich_person_by_name_and_company_fallback`
- `test_enrich_person_returns_none_on_no_match`
- `test_enrich_person_raises_on_sdk_error`
- `test_enrich_person_caches_by_linkedin_url`

**LeadershipEnrichment (`test_leadership_enrichment.py`):**

- `test_find_and_enrich_incumbents_runs_search_then_enrich_per_role`
- `test_find_and_enrich_incumbents_dedupes_same_person_across_roles`
- `test_find_and_enrich_incumbents_continues_on_per_role_failure`
- `test_cost_cap_halts_further_calls_preserves_prior_data`
- `test_cost_cap_returns_aborted_reason_cost_cap`
- `test_circuit_breaker_opens_after_three_consecutive_failures`
- `test_circuit_breaker_returns_aborted_reason_circuit_breaker`
- `test_empty_match_does_not_increment_failure_counter`
- `test_enrich_press_change_names_shares_cost_cap_with_incumbent_path`
- `test_enrich_press_change_names_returns_unmutated_on_no_pdl_match`
- `test_enrichment_metadata_records_spend_dollars`

**Collector (`test_leadership_stability.py` modifications):**

- `test_collect_calls_leadership_enrichment_when_available`
- `test_collect_skips_enrichment_when_ctx_leadership_enrichment_is_none`
- `test_collect_enriches_press_change_names_when_orchestrator_available`
- `test_collect_returns_partial_data_when_cost_cap_hit`
- DELETE: `test_search_linkedin_incumbents_*` (4 existing tests)
- DELETE: `test_extract_current_incumbents_*` (3 existing tests)

**Synthesizer (`test_observed_stability_trajectory.py`):**

- `test_aggregates_compute_tenure_confirmed_count`
- `test_aggregates_compute_external_hire_count`
- `test_aggregates_compute_internal_promotion_count`
- `test_aggregates_compute_prior_employer_signals_per_role`
- `test_aggregates_handle_missing_enrichment_data_gracefully`
- `test_synth_renders_enrichment_metadata_when_partial`

**Renderer + Pipeline + Config + CLI:**

- `test_leadership_stability_module_detail_renders_tenure_and_prior_employer`
- `test_module_detail_renders_enrichment_metadata_line`
- `test_pipeline_instantiates_pdl_client_when_key_present`
- `test_pipeline_skips_pdl_when_no_api_key`
- `test_pipeline_skips_pdl_when_no_pdl_flag_set`
- `test_config_pdl_cost_cap_dollars_default`
- `test_cli_no_pdl_flag_disables_enrichment`
- `test_cli_pdl_cost_cap_flag_overrides_default`

---

## Phase 2.2-deep acceptance criteria

| # | Criterion | Verified by |
|---|---|---|
| 1 | `PDLClient` works against mocked SDK | `test_pdl_client.py` |
| 2 | `LeadershipEnrichment` orchestrator runs Search → Enrich with per-role failure isolation | `test_find_and_enrich_incumbents_*` |
| 3 | Cost cap halts further PDL calls; preserves data already gathered | `test_cost_cap_halts_further_calls_preserves_prior_data` |
| 4 | Circuit breaker opens after 3+ consecutive failures | `test_circuit_breaker_opens_after_three_consecutive_failures` |
| 5 | LinkedIn snippet path removed; collector uses PDL exclusively | absence of `_search_linkedin_incumbents`; new collector tests pass |
| 6 | Press change names enriched with prior_employer / prior_role where PDL has data | `test_collect_enriches_press_change_names_when_orchestrator_available` |
| 7 | `--no-pdl` and missing API key both disable enrichment gracefully | `test_pipeline_skips_pdl_*`, `test_cli_no_pdl_flag_*` |
| 8 | Synthesizer aggregates include new derived fields | `test_aggregates_compute_*` |
| 9 | Module Detail Appendix renders tenure_months and prior_employer per incumbent | `test_leadership_stability_module_detail_renders_*` |
| 10 | Anonymizer behavior unchanged (press whitelisted; PDL-found names anonymized) | existing tests still pass |
| 11 | `data.json` round-trips with all new fields populated | extended round-trip test |
| 12 | Live smoke against Swayable / aioapp / remote.com produces narrative citing tenure_confirmed_count + motion-lens inferences where applicable | manual review (Dale-led quality gate) |
| 13 | Synthesizer commits to a hypothesis on each domain; "tenure unconfirmed" gaps reduced relative to Phase 2.2 | manual review |
| 14 | Quality gate signed off by Dale | manual review |

---

## Cost ceiling

Per-X-Ray maximum under normal operation:

- PDL Search: 7 role searches × $0.20 = **$1.40**
- PDL Enrichment for current incumbents: ~5 × $0.20 = **$1.00** (after dedup; founder + CEO collapse)
- PDL Enrichment for press change names: ~2 × $0.20 = **$0.40**
- Existing Phase 2.2 cost (Firecrawl + Anthropic + Haiku extractor): **~$0.04**
- Section B synthesizer on Opus 4.7: **~$0.07** (was $0.012 on Sonnet pre-escalation)
- **Total: ~$2.91 per domain run** (well under $5 cap)

A/B vs Phase 2.2:

- Phase 2.2: ~$0.05 per domain (Section B on Sonnet)
- Phase 2.2-deep: ~$2.91 per domain
- **Cost increase: ~$2.86** (≈ 58x). Justified by closing the tenure gap that motivates the entire phase.

Re-renders within 30-day disk cache window: ~$0.07 (just the Opus synthesizer call; PDL calls cached). Cheap to iterate prompts post-quality-gate.

---

## Risks and known limitations

- **PDL coverage varies by company size and region.** Best on US-based mid-large companies; thinner on early-stage / international. Mitigation: per-role failure isolation continues the run; absence framed as "PDL had no record" in narrative.
- **30-day cache TTL drift.** Tenure ticks up one month per cache window — acceptable. Prior_employer rarely changes — also acceptable. Manual `--no-cache` for full refresh.
- **PDL Search by company_domain may miss companies indexed under variant domains** (acme.com vs acme.co vs acme.ai). Mitigation: orchestrator falls back to free-text company name when domain search yields zero.
- **Synthesizer prompt expansion adds tokens** (~400-600 new). Section B per-call cost goes ~$0.06 → ~$0.07 on Opus. Acceptable.
- **`peopledatalabs-python` is a new third-party dependency.** Approved by Dale at spec time per the canonical "one approved data partner per signal area" rule.
- **Prior-employer motion-lens inferences are LLM judgment, not fact.** Synthesizer prompt explicitly frames these as working hypotheses. Quality-gate review should confirm the LLM is hedging appropriately, not over-claiming.
- **PDL data drift inside a single run is not handled.** If PDL's underlying source updates a profile between Search and Enrich for the same person, we may see inconsistent fields. Cache is per-call, so this is rare. Not worth fixing in 2.2-deep.
- **Cost cap is per-run, not per-day.** A flaky pipeline crash + restart could re-spend. Mitigation: 30-day disk cache catches re-runs.

---

## Out of scope but accommodated by the design

- Phase 2.3 `buyer_sentiment` collector reuses the `LeadershipEnrichmentMetadata` pattern for tracking PDL-style budget if a future data partner uses similar cost model.
- Phase 3's `services/llm.py` provider abstraction does NOT affect this phase. `PDLClient` is a data-partner client, not an LLM client; lives in its own lane.
- Phase 2.1d `content_demand` collector is independent; can ship in parallel via the second-Coder track.

---

## Open questions

None at this time. All material decisions are locked in the brainstorming decisions table above.
