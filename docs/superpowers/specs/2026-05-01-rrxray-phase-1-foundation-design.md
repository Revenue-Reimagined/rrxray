# rrxray Phase 1 Foundation — Design

**Date:** 2026-05-01
**Status:** Approved (brainstorming complete)
**Phase:** 1 of 4 (Foundation)
**Next phase:** 2 (remaining 8 collectors + 3 synthesizers)
**Source spec:** GTM X-Ray Build Spec (Revenue Reimagined)

---

## Context

GTM X-Ray is an externally-sourced GTM diagnostic that augments Revenue Reimagined's Foundations Analysis with signals only an outside operator surfaces: hiring shape, tech stack, funding posture, pricing drift, customer concentration, content cadence, leadership tenure, positioning drift, and buyer sentiment. The full spec covers nine collectors, three synthesizers, four deliverable modes, four output formats, a voice/anonymizer post-processor, a CLI, and a static dashboard.

That scope is too large for one design → plan → implementation cycle. We've decomposed into four phases:

- **Phase 1 (this doc):** Foundation. Architecture, service clients, voice infrastructure, one collector end-to-end through synthesis and Markdown rendering.
- **Phase 2:** The remaining 8 collectors and 3 synthesizers, plugged into Phase 1 patterns.
- **Phase 3:** The four deliverable modes (internal/hook/leave-behind/qbr) and the PDF/Gamma/dashboard renderers.
- **Phase 4:** Polish, README, smoke runs against three real B2B SaaS domains.

The Phase 1 deliverable is a runnable CLI that produces a real Markdown report against a real domain, exercising every architectural surface that later collectors and renderers will plug into. If Phase 1 is right, Phase 2 is fill-in-the-blank.

---

## Scope

### In scope

- pyproject + CLI scaffolding (typer) + config loader (pydantic-settings)
- Firecrawl, Anthropic, Wayback service-client wrappers with on-disk caching
- `rr_voice` post-processor (tiered: substitute for collectors, raise for synthesizers)
- `anonymizer` (full implementation with name registry + press-release whitelist)
- `pricing_packaging` collector end-to-end
- `observed_gtm_motion` synthesizer (Phase 1 pricing-only variant; Phase 2 expands)
- Markdown renderer in `internal` mode, full seven-section skeleton; Section A and pricing's Module Detail filled with real content; other sections render `[Module not available for this domain]`
- pytest suite with cache-as-fixture pattern
- `--dry-run` cost estimator

### Out of scope (Phase 2+)

- 8 remaining collectors: `revenue_motion`, `tech_stack`, `funding_trajectory`, `customer_concentration`, `content_demand`, `leadership_stability`, `positioning_drift`, `buyer_sentiment`
- Section B (`stability_trajectory`) and Section C (`external_voice_vs_internal`) synthesizers; Executive Summary synthesizer
- Non-internal modes: `hook`, `leave-behind`, `qbr`, `all`
- PDF, Gamma, dashboard renderers
- `--diff` flag and QBR quarter-over-quarter logic
- HubSpot integration, `--watch` mode

The CLI surface declares Phase 2+ flags and modes but raises `NotImplementedError` with a helpful message when invoked. The CLI signature stays stable across phases.

---

## Decisions Locked During Brainstorming

| Decision | Choice | Rationale |
|---|---|---|
| Tool name | `rrxray` package; `rrxray` binary; "GTM X-Ray™" display name | Matches working dir; brand-forward |
| Python stack | Python 3.12+, uv, typer, ruff, pytest, pytest-asyncio | Modern; uv is the fastest install/lockfile path |
| Voice handling | Tiered: substitute for collector text, raise for synthesizer text | Matches actual failure modes |
| Test fixtures | Cache-as-fixture | One mechanism for cache + tests; no mock drift |
| Voice rules source | Static, checked-in `prompts/synthesizer_system.md` | rrxray must run without Claude Code installed |
| Phase 1 model | Sonnet 4.6 with prompt caching; Opus 4.7 via `--model` override | Best utility-per-dollar on factual narrative |
| Anonymizer scope | Full implementation in Phase 1 with synthetic-data tests | Architecture rests on it; cutting corners bites Phase 2 |
| Pipeline shape | Module-pattern with explicit COLLECTORS/SYNTHESIZERS lists | Simplest mental model; graceful degradation in one place |
| Phase 1 done-definition | Full report skeleton, Section A real content, other sections `[Module not available for this domain]` | Exercises full renderer surface; Phase 2 plugs in |

---

## Architecture

### Directory layout

```
rrxray/
  pyproject.toml                      [uv-managed; project.scripts.rrxray = "rrxray.cli:app"]
  uv.lock
  ruff.toml
  README.md
  .gitignore
  rrxray/
    __init__.py
    cli.py                            [typer app: run, collect, synthesize, render]
    config.py                         [pydantic-settings; env + CLI flag merging]
    pipeline.py                       [orchestrator; COLLECTORS/SYNTHESIZERS lists]
    context.py                        [CollectorContext, SynthesizerContext dataclasses]
    schemas/
      __init__.py
      data.py                         [XrayData, CollectorOutputs, SynthesizerOutputs, ModuleFailure, VoiceEvent]
      pricing_packaging.py            [PricingPackagingData + nested types]
    services/
      __init__.py
      cache.py                        [DiskCache: live | replay-only | refresh]
      firecrawl_client.py             [async wrapper; cache + 5-concurrent semaphore]
      anthropic_client.py             [async wrapper; prompt caching baked in]
      wayback_client.py               [snapshots() at N-month over M-month span]
    collectors/
      __init__.py
      pricing_packaging.py            [Phase 1 only collector]
    synthesizers/
      __init__.py
      observed_gtm_motion_pricing.py  [Phase 1 pricing-only Section A synthesizer]
    rendering/
      __init__.py
      markdown.py                     [Jinja env + filters; XrayData -> str]
    voice/
      __init__.py
      rr_voice.py                     [tiered post-processor]
      anonymizer.py                   [name registry + press-release whitelist]
    prompts/
      __init__.py
      synthesizer_system.md           [static; voice + quarantine + anonymity + framework]
      observed_gtm_motion_pricing.md  [Phase 1 user-message Jinja template]
    modes/
      __init__.py
      base.py                         [Mode enum; eligibility-filter API surface]
      internal.py                     [near-empty passthrough; Phase 1 only mode honored]
  templates/
    report_internal.md.jinja          [seven-section skeleton]
    _pricing_detail.md.jinja          [Module Detail Appendix partial for pricing]
  tests/
    conftest.py
    fixtures/
      cache/
        firecrawl/
        anthropic/
        wayback/
      synthetic/
        press_releases/
        pricing/
        anonymity/
        voice/
    test_voice.py
    test_anonymizer.py
    test_pricing_packaging.py
    test_synthesizer_pricing.py
    test_render_internal.py
    test_pipeline_graceful_degradation.py
    test_cli.py
    test_dry_run_estimator.py
  docs/
    superpowers/
      specs/
        2026-05-01-rrxray-phase-1-foundation-design.md   [this doc]
```

### Pipeline shape (module-pattern)

Each collector is a module with `NAME: str` constant and `async def collect(ctx: CollectorContext) -> <CollectorData>` function. Each synthesizer mirrors that pattern. The orchestrator imports them by name, builds a list, and runs them concurrently.

```python
# rrxray/pipeline.py
from rrxray.collectors import pricing_packaging
from rrxray.synthesizers import observed_gtm_motion_pricing

COLLECTORS = [pricing_packaging]
SYNTHESIZERS = [observed_gtm_motion_pricing]

async def run_pipeline(config: Config) -> XrayData:
    collector_ctx = build_collector_context(config)
    collector_outputs, collector_failures = await run_collectors(collector_ctx)

    synth_ctx = build_synthesizer_context(config, collector_outputs)
    synth_outputs, synth_failures = await run_synthesizers(synth_ctx)

    return XrayData(
        domain=config.domain,
        collectors=collector_outputs,
        synthesizers=synth_outputs,
        failures=collector_failures + synth_failures,
        sources=flatten_sources(collector_outputs),
        voice_log=synth_ctx.voice.flush_log(),
        run_metadata=build_run_metadata(config),
        inputs=config.to_input_params(),
    )

async def run_collectors(ctx) -> tuple[CollectorOutputs, list[ModuleFailure]]:
    coros = [(c.NAME, c.collect(ctx)) for c in COLLECTORS]
    results = await asyncio.gather(*[coro for _, coro in coros], return_exceptions=True)
    outputs = CollectorOutputs()
    failures = []
    for (name, _), result in zip(coros, results):
        if isinstance(result, Exception):
            failures.append(ModuleFailure(module=name, kind="collector", error=str(result), traceback=...))
            log.warning(f"Collector {name} failed: {result}")
        else:
            setattr(outputs, name, result)
    return outputs, failures
```

`return_exceptions=True` is the lynchpin of graceful degradation. One collector blowing up doesn't take down the others; the failure becomes a `ModuleFailure` row; the renderer treats the absent field as `[Module not available for this domain]`.

---

## Components

### Service clients (`rrxray/services/`)

#### `cache.py` — DiskCache (the cache-as-fixture core)

Three modes:

- **`live`** (default): try cache hit on disk; on miss, call upstream; write response to disk; return.
- **`replay-only`**: try cache hit; on miss, raise `CacheMissError`. Used in tests so a missing fixture loudly fails instead of silently calling the real API.
- **`refresh`**: ignore cache; always call upstream; overwrite. For `--use-cache=false` and fixture bootstrap.

Cache key = `sha256(method_name + canonical_json(args))[:16]`. Cache value = `{"timestamp": iso8601, "response": <serialized response>}`. TTL default 24h. Stored at `~/.rrxray/cache/<service>/<key>.json` for live runs and `tests/fixtures/cache/<service>/<key>.json` for tests. Tests select `replay-only` and point `cache_dir` at the fixtures directory via a pytest fixture (no monkeypatching, no mock library).

#### `firecrawl_client.py` — FirecrawlClient

Async wrapper around `firecrawl-py`. Phase 1 uses one method; the other two interfaces exist for Phase 2:

- `scrape_url(url: str, only_main_content: bool = True) -> ScrapedPage` (Phase 1)
- `crawl_url(url: str, max_pages: int = 25) -> list[ScrapedPage]` (Phase 2)
- `search(query: str, limit: int = 10) -> list[SearchResult]` (Phase 2)

Each method goes through `DiskCache`. Concurrency capped at 5 simultaneous calls via an `asyncio.Semaphore` bound on the client instance.

#### `anthropic_client.py` — AnthropicClient

Async wrapper with prompt caching baked in from day one. The `complete_with_cached_system()` method accepts `(system_prompt: str, user_message: str, model: str = "claude-sonnet-4-6", response_schema: type[BaseModel] | None = None)` and constructs the request with `cache_control: {"type": "ephemeral"}` on the system prompt. Cache hit telemetry is logged.

The synthesizer system prompt is roughly 3-4K tokens of static content (voice rules + quarantine + anonymity + framework). Within a 5-minute window, every iteration on the user message reuses the cached system prompt at 10% of normal input cost, cutting cost 5-8× during prompt-tuning sessions.

The disk cache key for Anthropic includes `model + system_prompt + user_message` so prompt-content changes invalidate correctly.

`response_schema` enforces a JSON shape via Anthropic tool-use, killing the "Claude returned a paragraph instead of JSON" failure mode.

#### `wayback_client.py` — WaybackClient

Single method: `async def snapshots(url: str, interval_months: int = 6, span_months: int = 18) -> list[Snapshot]`. Returns up to four `Snapshot(timestamp, archive_url, html)` objects. Internally generates target timestamps; hits `https://archive.org/wayback/available?url=...&timestamp=...` for each; fetches snapshot HTML via Firecrawl scrape (so it goes through the same cache layer + concurrency cap).

### Schemas (`rrxray/schemas/`)

#### `data.py` — XrayData (canonical top-level)

```python
class XrayData(BaseModel):
    schema_version: Literal["1"] = "1"
    domain: str
    company_name: str | None = None
    run_metadata: RunMetadata
    inputs: InputParams
    collectors: CollectorOutputs
    synthesizers: SynthesizerOutputs
    sources: list[SourceCitation] = []
    voice_log: list[VoiceEvent] = []
    failures: list[ModuleFailure] = []

class CollectorOutputs(BaseModel):
    pricing_packaging: PricingPackagingData | None = None
    # Phase 2: revenue_motion, tech_stack, funding_trajectory, customer_concentration,
    #          content_demand, leadership_stability, positioning_drift, buyer_sentiment

class SynthesizerOutputs(BaseModel):
    observed_gtm_motion: ObservedGtmMotionNarrative | None = None
    # Phase 2: stability_trajectory, external_voice_vs_internal, executive_summary
```

Every collector and synthesizer field is `| None`. Missing = "not run" or "failed gracefully". This is how graceful degradation flows through the system: failure becomes an absent field, never an exception at render time.

`ModuleFailure(module: str, kind: Literal["collector", "synthesizer"], error: str, traceback: str)` and `VoiceEvent(rule: str, original: str, replacement: str | None, context: str, action: Literal["substitute", "raise"])` are the audit-trail rows.

#### `pricing_packaging.py` — PricingPackagingData

```python
class PricingPackagingData(BaseModel):
    has_public_pricing: bool
    is_contact_us_gated: bool
    current_pricing_url: str | None
    current_tiers: list[PricingTier] = []
    historical_snapshots: list[HistoricalSnapshot] = []
    detected_changes: list[PricingChange] = []
    findings: list[Finding] = []
    gaps: list[str] = []
    discovery_questions: list[str] = []
    sources: list[SourceCitation] = []

class PricingChange(BaseModel):
    date_observed: date
    kind: Literal["tier_added", "tier_removed", "price_increased", "price_decreased",
                  "gating_added", "gating_removed", "cta_changed"]
    before: str
    after: str
```

### Contexts (`rrxray/context.py`)

```python
@dataclass(frozen=True)
class CollectorContext:
    domain: str
    company_name: str | None
    firecrawl: FirecrawlClient
    wayback: WaybackClient
    evidence_dir: Path
    config: Config

@dataclass(frozen=True)
class SynthesizerContext:
    collector_outputs: CollectorOutputs
    anthropic: AnthropicClient
    voice: VoicePostProcessor
    anonymizer: Anonymizer
    config: Config
```

Collectors get scraping + evidence-write capability but no LLM. Synthesizers get LLM + voice/anonymizer but no scraping. The type system enforces this separation: a collector can never accidentally call Claude.

### Voice post-processor (`rrxray/voice/rr_voice.py`)

```python
class VoicePostProcessor:
    def __init__(self):
        self._log: list[VoiceEvent] = []

    def process_collector_text(self, text: str, context: str) -> str:
        return self._apply(text, context, on_violation="substitute")

    def process_synthesizer_text(self, text: str, context: str) -> str:
        return self._apply(text, context, on_violation="raise")

    def flush_log(self) -> list[VoiceEvent]:
        events, self._log = self._log, []
        return events
```

`_apply()` runs three checks:

1. **Em dash check** — regex `—`. Substitute mode: `;` if next non-whitespace char is lowercase, else `:`. Synthesizer mode: raise.
2. **Forbidden word check** — case-insensitive boundary-matched regex against `{leverage, synergies, holistic, streamline, impactful}` plus inflections (`leveraging`, `streamlined`, etc.). Substitution map preserves capitalization on the replacement (`Leverage` → `Use`):
   ```python
   SUBSTITUTIONS = {
       "leverage": "use", "leveraging": "using", "leveraged": "used",
       "synergies": "overlap", "synergy": "overlap",
       "holistic": "end-to-end",
       "streamline": "simplify", "streamlined": "simplified", "streamlining": "simplifying",
       "impactful": "meaningful",
   }
   ```
3. **Trademark check** — `GTM Gap` not followed by `™` becomes `GTM Gap™` on first occurrence per render. Always substitute, never raise.

Every violation produces a `VoiceEvent(rule, original, replacement, context, action)` row in `_log`. Pipeline calls `flush_log()` and embeds events in `XrayData.voice_log`. Markdown renderer surfaces these in the Sources/Methodology section under "Voice Adjustments".

`VoiceViolationError` (raised in synthesizer mode) carries the original text, the violation, and the synthesizer name. Pipeline catches at the synthesizer level, treats synthesizer as failed (`ModuleFailure` row), continues.

### Anonymizer (`rrxray/voice/anonymizer.py`)

```python
class Anonymizer:
    def __init__(self):
        self.name_to_role: dict[str, str] = {}
        self.whitelisted_names: set[str] = set()

    def register_individual(self, name: str, role_descriptor: str): ...
    def whitelist_from_press(self, name: str): ...
    def anonymize(self, text: str) -> str: ...
```

Two-stage flow:

- **Stage 1: harvest names.** Phase 1 has no organic name source (pricing collector doesn't surface them). For tests, registry is seeded from synthetic fixtures (`tests/fixtures/synthetic/anonymity/`). Phase 2's `leadership_stability` collector populates it.
- **Stage 2: anonymize on render.** Markdown renderer pipes every paragraph through `anonymizer.anonymize()` before writing. Even if a synthesizer hallucinates a name (which the system prompt forbids), the anonymizer strips it. Defense in depth.

Press release whitelist mechanism: `evidence/press_releases/` subfolder is the whitelist source. Phase 2's `leadership_stability` collector writes scraped press release HTML there, then iterates extracted names through `whitelist_from_press()`. Phase 1 builds the API surface and tests it with synthetic data.

The renderer raises `AnonymityViolationError` if it encounters a name in `name_to_role` that is neither replaced nor whitelisted. Catches a class of bug where the anonymizer forgets to run on a code path.

### `pricing_packaging` collector (`rrxray/collectors/pricing_packaging.py`)

```python
NAME = "pricing_packaging"

async def collect(ctx: CollectorContext) -> PricingPackagingData:
    pricing_url = await _discover_pricing_url(ctx)
    if pricing_url is None:
        return PricingPackagingData(
            has_public_pricing=False,
            is_contact_us_gated=True,
            ...,
            findings=[Finding(text="No public pricing page found...", source=...)],
        )

    current = await ctx.firecrawl.scrape_url(pricing_url, only_main_content=True)
    snapshots = await ctx.wayback.snapshots(pricing_url, interval_months=6, span_months=18)

    current_tiers = _extract_tiers(current.markdown)
    historical = [_extract_tiers(s.markdown) for s in snapshots]
    changes = _diff_snapshots([current_tiers, *historical])

    is_gated = _detect_contact_us(current.markdown)
    findings, gaps, questions = _interpret(current_tiers, changes, is_gated)

    _write_evidence(ctx.evidence_dir / NAME, current, snapshots)

    return PricingPackagingData(
        has_public_pricing=True, is_contact_us_gated=is_gated, current_pricing_url=pricing_url,
        current_tiers=current_tiers,
        historical_snapshots=[HistoricalSnapshot.from_wayback(s, _extract_tiers(s.markdown)) for s in snapshots],
        detected_changes=changes, findings=findings, gaps=gaps, discovery_questions=questions,
        sources=[...]
    )
```

Tier extraction is heuristic, not LLM-based. Regex/markdown-parse the scraped pricing page for dollar amounts, tier names, and per-seat/per-month indicators. Collectors are mechanical; the LLM budget is reserved for synthesis.

Diff logic compares snapshots chronologically and emits `PricingChange` rows. This is the diagnostic gold; pricing churn is a strong motion signal.

Evidence written to `evidence/pricing_packaging/`:
- `current.html` and `current.md`
- `wayback_<timestamp>.md` per snapshot
- `extracted_tiers.json`

### Section A pricing-only synthesizer (`rrxray/synthesizers/observed_gtm_motion_pricing.py`)

```python
NAME = "observed_gtm_motion"

async def synthesize(ctx: SynthesizerContext) -> ObservedGtmMotionNarrative | None:
    pricing = ctx.collector_outputs.pricing_packaging
    if pricing is None:
        return None

    system_prompt = _load_system_prompt()
    user_message = _render_user_message(pricing)

    response = await ctx.anthropic.complete_with_cached_system(
        system_prompt=system_prompt,
        user_message=user_message,
        model=ctx.config.model,
        response_schema=NarrativeResponse,
    )

    paragraphs = [ctx.voice.process_synthesizer_text(p, context=f"Section A para {i}")
                  for i, p in enumerate(response.narrative_paragraphs)]
    gap_bullets = [ctx.voice.process_synthesizer_text(g, context=f"Section A gap {i}")
                   for i, g in enumerate(response.gap_bullets)]

    return ObservedGtmMotionNarrative(
        narrative_paragraphs=paragraphs, gap_bullets=gap_bullets,
        findings=response.findings, gaps=response.gaps, discovery_questions=response.discovery_questions,
        model_used=ctx.config.model, cache_hit=response.cache_hit,
    )
```

System prompt structure (`prompts/synthesizer_system.md`):

- Header: pointer back to `rr-brand-voice` skill as the design source-of-truth
- Universal Rules: Verbatim Quarantine, Individual Anonymity, Brand Voice
- Section-Specific Framework: appended at runtime by the synthesizer module from its own template

Phase 1's user message template (`prompts/observed_gtm_motion_pricing.md`) takes `PricingPackagingData` and produces the section-specific framework + structured pricing facts. Phase 2's full Section A synthesizer replaces this template with one that takes input from `revenue_motion + tech_stack + pricing_packaging + content_demand`.

### Markdown renderer (`rrxray/rendering/markdown.py`)

```python
def render_internal(data: XrayData, output_path: Path, anonymizer: Anonymizer, voice: VoicePostProcessor) -> None:
    env = Environment(loader=FileSystemLoader("templates"), trim_blocks=True, lstrip_blocks=True)
    env.filters["anonymize"] = anonymizer.anonymize
    env.filters["voice_collector"] = voice.process_collector_text
    env.filters["bullet_list"] = lambda items: "\n".join(f"- {it}" for it in items)
    env.globals["collected_discovery_questions"] = _collect_questions

    template = env.get_template("report_internal.md.jinja")
    rendered = template.render(data=data)
    output_path.write_text(rendered)
```

Anonymization happens at render via Jinja filter. Every paragraph passes through `anonymizer.anonymize` before hitting disk. If the anonymizer registry contains a name and the renderer doesn't pipe through the filter on some code path, the test suite catches it.

Voice post-processing also happens at render via the `voice_collector` filter. Synthesizer text already went through `process_synthesizer_text` (which raises). The filter applies a second pass in *collector mode* to catch anything mechanical that slipped through. Cheap belt-and-suspenders.

The renderer is otherwise pure: `XrayData → str`, no I/O except the final `write_text`. Trivial to test (golden-file tests against fixture XrayData inputs).

### Report template (`templates/report_internal.md.jinja`)

The seven-section internal-mode skeleton:

1. Executive Summary (Phase 2+; renders `[Module not available...]` in Phase 1)
2. Section A — Observed GTM Motion (Phase 1: real, pricing-only narrative)
3. Section B — Stability and Trajectory Signals (Phase 2)
4. Section C — External Voice vs. Internal Voice (Phase 2)
5. Module Detail Appendix (Phase 1: pricing's `_pricing_detail.md.jinja` partial)
6. Discovery Questions (compiled from collectors + synthesizers)
7. Sources & Methodology (every URL, timestamp, evidence path; Voice Adjustments subsection from `data.voice_log`; Module Failures subsection from `data.failures`; Known Limitations static block)

### CLI surface (`rrxray/cli.py`)

Four subcommands via typer:

- `run` — full pipeline (collect → synthesize → render)
- `collect` — collectors only; writes data.json with synthesizers section empty
- `synthesize` — synthesizers only; reads data.json, fills synthesizers section, writes back
- `render` — renderers only; reads data.json, writes `report.{mode}.md`

Phase 1 CLI flags exposed:

- `--domain` (required)
- `--company-name`
- `--output-dir`
- `--skip-modules` (no-op in Phase 1; honored in Phase 2)
- `--mode` (Phase 1: only `internal` is valid; others raise `NotImplementedError` with helpful message)
- `--use-cache` / `--no-cache`
- `--dry-run`
- `--model` (default `claude-sonnet-4-6`)

`--prior-data` (Phase 3 QBR diff) and `--competitors` (Phase 2 positioning_drift) are NOT exposed in the Phase 1 CLI; added in their respective phases.

### Config (`rrxray/config.py`)

```python
class Config(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RRXRAY_", env_file=".env", extra="ignore")

    anthropic_api_key: SecretStr | None = None
    firecrawl_api_key: SecretStr | None = None
    gamma_api_key: SecretStr | None = None             # Phase 1 unused; declared for forward compat

    domain: str
    company_name: str | None = None
    output_dir: Path | None = None
    skip_modules: list[str] = []
    mode: Literal["internal"] = "internal"
    use_cache: bool = True
    dry_run: bool = False
    model: str = "claude-sonnet-4-6"

    cache_dir: Path = Path.home() / ".rrxray" / "cache"
    cache_ttl_hours: int = 24

    firecrawl_max_concurrent: int = 5
```

API keys load from env. Both `ANTHROPIC_API_KEY` (bare) and `RRXRAY_ANTHROPIC_API_KEY` (prefixed) work via aliasing. `.env` file support is built in. Output directory default: `./xray-{domain-slug}-{YYYYMMDD}/` if `--output-dir` not set.

---

## Data flow

```
CLI invocation
   ↓
Config (env + flags merged)
   ↓
build_collector_context(config) → CollectorContext
   ↓
asyncio.gather(c.collect(ctx) for c in COLLECTORS, return_exceptions=True)
   ↓
CollectorOutputs (with None for failed collectors) + list[ModuleFailure]
   ↓
build_synthesizer_context(config, collector_outputs) → SynthesizerContext
   ↓
asyncio.gather(s.synthesize(ctx) for s in SYNTHESIZERS, return_exceptions=True)
   ↓
SynthesizerOutputs (with None for failed) + list[ModuleFailure]
   ↓
XrayData (validated by pydantic)
   ↓
data.json written to output_dir
   ↓
render_internal(data, ..., anonymizer, voice) → report.internal.md
   ↓
voice_log + failures surfaced in report Sources/Methodology section
```

---

## Error handling

Three layers, each with a clear policy:

1. **Service clients** raise typed errors: `FirecrawlError`, `AnthropicError`, `WaybackError`, `CacheMissError`, `RateLimitError`. They do NOT swallow exceptions or return `None` on failure; they let them propagate.
2. **Collectors and synthesizers** are allowed to raise. The pipeline orchestrator catches via `asyncio.gather(return_exceptions=True)` and converts to `ModuleFailure` rows. This is the only place exceptions are converted to data.
3. **Renderers** must not raise on missing data; they produce `[Module not available for this domain]` strings instead. Exception: voice violations during synthesizer text post-processing raise. That happens before render; by the time render runs, the violation is already a `ModuleFailure` and the section is `None`.

The CLI catches all `RrxrayError` subclasses at the top level, prints a clean message, exits with code 1. Unexpected exceptions print a stack trace and exit 2.

---

## Testing

### `conftest.py` — cache-as-fixture wiring

```python
@pytest.fixture
def fixture_cache_dir() -> Path:
    return Path(__file__).parent / "fixtures" / "cache"

@pytest.fixture
def replay_firecrawl(fixture_cache_dir) -> FirecrawlClient:
    return FirecrawlClient(
        api_key="test-key-not-used",
        cache=DiskCache(dir=fixture_cache_dir / "firecrawl", mode="replay-only"),
    )

@pytest.fixture
def replay_anthropic(fixture_cache_dir) -> AnthropicClient:
    return AnthropicClient(
        api_key="test-key-not-used",
        cache=DiskCache(dir=fixture_cache_dir / "anthropic", mode="replay-only"),
    )

@pytest.fixture
def frozen_now():
    with freeze_time("2026-05-01T12:00:00Z"):
        yield
```

`replay-only` raises `CacheMissError` on miss. If a test inadvertently introduces a code path needing an unrecorded API call, the test fails loudly with the missing cache key. Fix: bootstrap the missing key, check it in.

### Test files and what each verifies

| File | Verifies |
|---|---|
| `test_voice.py` | em dash detection (substitute + raise modes), each forbidden word with inflections + capitalization, trademark insertion, `flush_log` returns events |
| `test_anonymizer.py` | unwhitelisted name replaced with role descriptor; whitelisted name preserved; longest-name-first matching; renderer raises `AnonymityViolationError` if a registered name reaches output unanonymized |
| `test_pricing_packaging.py` | tier extraction from synthetic markdown; contact-us gating detection; diff logic across synthetic snapshots covering every `PricingChange.kind` |
| `test_synthesizer_pricing.py` | system prompt loaded; user message template renders correctly from `PricingPackagingData`; Anthropic client called with cache_control; voice post-processing applied to every paragraph |
| `test_render_internal.py` | seven-section skeleton present; `[Module not available for this domain]` appears in B/C/exec-summary; voice log surfaces in Sources/Methodology; golden-file diff against fixture |
| `test_pipeline_graceful_degradation.py` | injecting a collector that raises produces `ModuleFailure` row; `data.collectors.pricing_packaging is None`; render still produces complete file; `XrayData.model_validate(json.loads(written_path.read_text()))` succeeds |
| `test_cli.py` | typer subcommands wired; `--mode hook` / `--mode leave-behind` / `--mode qbr` raise `NotImplementedError` with helpful message; `--mode internal` proceeds |
| `test_dry_run_estimator.py` | dry-run prints expected plan; cost estimate within ±20% of actual cost from fixture run |

### Fixture bootstrap path

```bash
RRXRAY_CACHE_DIR=tests/fixtures/cache uv run rrxray run --domain example.com
```

The cache layer writes JSON files keyed by request hash. Commit those files. Tests run offline against the same data.

---

## Phase 1 acceptance criteria

| # | Criterion | Test |
|---|---|---|
| 1 | `rrxray run --domain example.com` produces `data.json`, `report.internal.md`, `evidence/` in under 8 minutes | manual smoke test |
| 2 | `data.json` validates against `XrayData` pydantic schema | `test_pipeline_graceful_degradation::test_data_json_round_trips` |
| 3 | Every finding in the report has source URL + scrape timestamp | `test_render_internal::test_findings_have_sources` |
| 4 | Voice post-processor catches em dashes and forbidden words on every render | `test_voice` |
| 5 | Sections A/B/C present and labeled in the rendered report | `test_render_internal::test_full_skeleton_present` |
| 8 | Collector failure produces `[Module not available for this domain]`, no crash | `test_pipeline_graceful_degradation` |
| 9 | `--dry-run` predicts cost within ±20% | `test_dry_run_estimator` |
| 11 | Anonymity test: registered name → role descriptor; whitelisted name preserved | `test_anonymizer` |

The full spec's ACs #6 (dashboard), #7 (Gamma), #10 (Verbatim Quarantine), #12 (hook eligibility) are deferred to Phase 2/3. AC #10 ships a placeholder check in Phase 1: the renderer raises if `data.json` contains a `verbatim_sentiment` field, which Phase 1 schemas don't have, but the Phase-2-ready check lives in the renderer now.

---

## Risks and known limitations

- **Firecrawl SDK async behavior is not fully tested by us yet.** The cache wrapper assumes `httpx`-style async. If the SDK uses sync internals wrapped in a thread pool, our concurrency cap may not behave as designed. Mitigation: a `test_services` integration test runs against a single mocked HTTP server before we lock the design.
- **Wayback availability is best-effort.** Some snapshots may not exist or fail to load. The Wayback client tolerates missing snapshots (returns fewer than 4 if some are unavailable). Pricing collector handles `historical_snapshots=[]` gracefully.
- **Heuristic tier extraction will fail on non-standard pricing pages.** When extraction returns empty `current_tiers`, the collector still produces a useful `PricingPackagingData` with `has_public_pricing=True` and a finding noting parse failure. The synthesizer will reflect this in narrative.
- **Sonnet 4.6 voice consistency is good but not perfect.** The synthesizer occasionally produces forbidden words. The tiered voice handler raises in this case, marking the synthesizer as failed. Phase 1 ships without auto-retry; if this proves annoying we add `--retry-voice` in Phase 2.
- **Press-release whitelist in Phase 1 has no organic data source.** Tested with synthetic fixtures only. First real-world test happens in Phase 2 when `leadership_stability` collector lands.

---

## Out-of-scope items the design intentionally accommodates

- The CLI surface is stable; Phase 2 adds `--competitors`, Phase 3 adds `--prior-data`. No CLI rework.
- The pipeline module-pattern means Phase 2 collectors append to `COLLECTORS`. No orchestrator rework.
- The renderer treats every collector field as `| None`. Phase 2 fills in fields without changing the renderer.
- The mode interface (`modes/base.py`) is stable; Phase 3 adds eligibility filters and reframing logic without changing internal mode.

---

## Open questions

None at this time. All material decisions are locked.
