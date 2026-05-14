# rrxray Roadmap

**Last updated:** 2026-05-07

The Phase 1 foundation has shipped. This file tracks what's next, what's deferred, and the design decisions behind each.

> **Cross-session continuity:** every phase milestone produces a checkpoint document at `docs/checkpoints/<date>-<phase-id>-checkpoint.md`. See [`CLAUDE.md`](CLAUDE.md) for the mandatory checkpoint rule. Most recent checkpoint: [`2026-05-07-phase-1-foundation-checkpoint.md`](docs/checkpoints/2026-05-07-phase-1-foundation-checkpoint.md).

---

## Phase 1: Foundation (shipped)

23 tasks across 7 sub-phases on `feat/phase-1-foundation` (36 commits, 126 tests passing + 1 e2e smoke awaiting fixture bootstrap). Two real live runs against `sqaservices.com` and `swayable.com` produced clean reports.

**What works today:**

- `rrxray run --domain <example.com>` runs the full pipeline end-to-end
- `pricing_packaging` collector with Wayback snapshot diffing + evidence writing
- Section A pricing-only synthesizer (Sonnet 4.6 with prompt caching)
- Internal-mode Markdown renderer with seven-section skeleton
- Tiered voice post-processor (substitute for collectors, raise for synthesizers)
- Full anonymizer with name registry + press-release whitelist
- Pipeline orchestrator with `asyncio.gather(return_exceptions=True)` graceful degradation
- Typer CLI with `run`, `collect`, `synthesize`, `render` subcommands
- Cache layer doubles as test-fixture mechanism (live / replay-only / refresh modes)
- 122 tests, ruff-clean

**Spec:** `docs/superpowers/specs/2026-05-01-rrxray-phase-1-foundation-design.md`
**Plan:** `docs/superpowers/plans/2026-05-01-rrxray-phase-1-foundation.md`

---

## Phase 2: Remaining collectors and synthesizers

**Goal:** add the 8 remaining collectors and 2 remaining section synthesizers plus the Executive Summary synthesizer. Phase 1 plumbing means each collector is a module that appends to `COLLECTORS`, each synthesizer plugs into the existing pipeline.

**Collectors to add (each one its own module under `rrxray/collectors/`):**

- `revenue_motion`: scrape careers page, parse JD titles + comp ranges + locations. Infer AE-to-SDR ratio, motion type (PLG / outbound / inbound / hybrid), enterprise vs mid-market vs SMB signals
- `tech_stack`: scrape site source for analytics/martech tags (Segment, GTM, HubSpot, Marketo, Intercom, Drift, Pendo, etc.). Cross-reference public BuiltWith profile if available
- `funding_trajectory`: Crunchbase public profile + press release search. Last-raise date, total raised, implied stage. Headcount-from-LinkedIn estimated via Google cache snippets
- `customer_concentration`: scrape logo wall, case studies index, G2 listing. Cluster customers by vertical and segment
- `content_demand`: blog index crawl, count posts by month for last 12 months, detect cadence drops. Web search for podcast appearances
- `leadership_stability`: scrape `/about`, `/team`, `/leadership` pages. Web search for "[company] hires" press releases. Estimate tenure from public bios. Populates the anonymizer name registry
  - **2026-05-10:** Phase 2.2 shipped — leadership_stability collector + observed_stability_trajectory Section B synthesizer. Adds GeminiClient + extraction module (Haiku default; --extractor=gemini-flash flag). Pipeline-side anonymizer registration. Section B synthesizer escalated to Opus 4.7 for instruction-following on data-anchored timeframes. ~89 new tests; total 340 passing; ruff clean. Quality gate: 9 bug fixes across 5 iterations. Known limitation: tenure data still depends on press dates (LinkedIn-post URLs login-walled); Phase 2.2-deep adds PeopleDataLabs (~$0.20/record) to close the "tenure unconfirmed" gap.
  - **2026-05-12:** Phase 2.2-deep shipped — PeopleDataLabs enrichment. Quality gate signed off against Swayable + Healthicity (RR target ICP); remote.com as documented regression check. Per-X-Ray cost ~$2-3 in normal operation; cap $5. Closes the "tenure unconfirmed" narrative gap from Phase 2.2.
- `positioning_drift`: Wayback snapshots of homepage at 6-month intervals over 18 months. Diff hero headline, sub-headline, primary nav. If competitors provided, scrape their current homepages
- `buyer_sentiment`: G2, Capterra, Trustpilot, Reddit, Glassdoor. Verbatim themes (positive and negative). Pay particular attention to ex-AE Glassdoor reviews. **Verbatim Quarantine rule applies: raw text lives only in `evidence/buyer_sentiment/raw/`, never rendered.**

**Synthesizers to upgrade:**

- `observed_gtm_motion`: replace Phase 1 pricing-only version with full version reading from `revenue_motion + tech_stack + pricing_packaging + content_demand` (Sonnet 4.6 stays)
- `stability_trajectory` (new): synthesizes from `funding_trajectory + leadership_stability + customer_concentration` (Sonnet 4.6)
- `external_voice_vs_internal` (new): synthesizes from `buyer_sentiment + positioning_drift + content_demand` (Opus 4.7 — multi-input reasoning earns the premium)
- `executive_summary` (new): cross-section synthesis across all three sections (Opus 4.7)

**Phase 2 scope decisions to make at brainstorm time:**

- Whether to add an LLM provider abstraction (Anthropic + Gemini) when Opus calls land. Decision: defer to Phase 3 (see below).
- Whether collectors should run with finer-grained concurrency (current cap is 5 simultaneous Firecrawl calls; 8 collectors fanning out may hit rate limits)
- How to handle press-release name extraction reliably (LLM-assisted vs heuristic)

**Phase 1 issues to resolve in Phase 2:**

- Voice log entries from a failed synthesizer persist in the flush — minor traceability concern
- Pricing tier extraction misses markdown tables, bold-pseudo-headings, locales using period-as-thousands (`$1.200,50`)
- Cache + semaphore thundering herd: N concurrent calls for the same uncached URL pay for N upstream calls. Add a per-key in-flight registry inside `DiskCache.get_or_call`
- `validate_assignment=True` on output schemas already lands in Phase 1 (T19 fix); confirm Phase 2 collector additions respect the contract

---

## Phase 3: Deliverable modes + LLM provider abstraction + alternative renderers

**Goal:** ship the four deliverable modes (`internal`, `hook`, `leave-behind`, `qbr`) and the PDF / Gamma / dashboard renderers. Add Gemini as a second LLM provider.

**Modes:**

- `internal` (already shipped, full passthrough)
- `hook`: extract one to three findings as a cold-outreach paragraph or LinkedIn DM. Source-cited, observable, NOT judgment-adjacent. Hook eligibility filter: tech stack inference, positioning drift, pricing gating signals are eligible. Tenure analysis, funding-runway framing, sentiment themes are NOT. Renderer must enforce.
- `leave-behind`: warm version sent after a discovery call. Full Section A and full Section C. Section B reframed (patterns described, never named). Verbatim sentiment turned into thematic clusters
- `qbr`: for actual clients in a quarterly review. Anything goes. Adds Section 0 quarter-over-quarter diff if `--prior-data` is provided

**Renderers:**

- PDF: WeasyPrint with RR brand styling (dark navy `#0B1A33`, orange `#E97B26`, gold `#D4A017`)
- Gamma: writes `gamma-input.{mode}.md` shaped for Gamma's `generate` endpoint. Optional auto-call to Gamma API
- Dashboard: static HTML with mode toggle, served via `localhost:4000`. Fully offline (no CDN dependencies). Renders all four mode views from a single `data.json`

**LLM provider abstraction (decided 2026-05-02, deferred to here):**

Phase 1 hard-codes the synthesizer to Anthropic. Phase 3 introduces `services/llm.py` that abstracts the Anthropic / Gemini interface behind one `complete_with_cached_system(system_prompt, user_message, model, response_schema)` method. The current `AnthropicClient` already has this shape; `GeminiClient` becomes a sibling.

Reasoning for deferral to Phase 3 rather than adding now:

- Phase 1 Section A is already optimized at Sonnet 4.6 with prompt caching (~$0.012 per cached call). Switching to Gemini saves negligible cost on Phase 1
- Phase 2 Section C and Executive Summary use Opus 4.7. Gemini 2.5 Pro is roughly 10x cheaper at competitive quality on multi-input reasoning tasks. Phase 2's bigger-ticket calls are the right place to introduce the abstraction
- Phase 3 hook outreach is voice-critical. Anthropic models hold tight constraint sets (no em-dash, forbidden words, GTM Gap™ trademark) more reliably than Gemini today. The provider toggle gives us A/B benchmarking on real prospects
- A `--llm-provider anthropic|gemini` flag plus a `--model` extension (covers Sonnet, Opus, Haiku, Gemini 2.5 Pro / Flash, Gemini 2.0 Flash) gives full per-task cost/quality tuning

By-task LLM recommendation table (lock in at Phase 3 brainstorm):

| Task | Recommended | Why |
|---|---|---|
| Section A pricing synthesizer | Sonnet 4.6 | Voice-critical, already cheap at ~$0.012 cached |
| Section B trajectory synthesizer | Sonnet 4.6 | Voice-critical |
| Section C voice-gap synthesizer | Opus 4.7 OR Gemini 2.5 Pro | Multi-input reasoning; benchmark cost vs quality |
| Executive Summary | Opus 4.7 | Top-level synthesis everyone reads first |
| Hook outreach generator | Sonnet 4.6 | Voice-critical, low volume, high stakes |
| Mechanical extraction (if needed) | Haiku 4.5 OR Gemini 2.0 Flash | Cheap; voice tolerance not required |

---

## Phase 4: Polish, packaging, smoke runs

- Templates packaging for wheel installs: move `templates/` into the package as `rrxray/rendering/templates/` so `pip install rrxray` works (currently relies on dev-mode editable install path)
- README expansion: explain the four modes, when to use each, how to interpret each section
- Smoke runs against three real B2B SaaS domains, capture sample reports, tune prompts based on real output
- Cost model refinement in `_print_dry_run_plan`: replace static numbers with real cost data accumulated across Phases 1-3
- Optional: refactor `schemas/data.py` re-exports if forward-ref pattern becomes painful as more collectors land (Phase 2 review point)

---

## Stretch features (not yet scheduled)

- `--diff` flag for ad-hoc comparison of two `data.json` files (powers QBR mode quarter-over-quarter logic; also useful standalone)
- `--watch` mode: re-run monthly for active prospects, Slack alert on meaningful signal change (new CRO hire, pricing page change, case study cluster shift)
- HubSpot integration: attach the report to the deal record. `internal` mode goes on the deal; nothing client-facing auto-attaches
- Multi-provider report comparison mode: render Side-by-Side from Anthropic and Gemini in one run for high-stakes prospects where you want both readings

---

## Decisions log

| Date | Decision | Rationale |
|---|---|---|
| 2026-05-01 | Phase 1 ships pricing_packaging only, no other collectors | Prove the architecture end-to-end on one collector before scaling |
| 2026-05-01 | Sonnet 4.6 with prompt caching for Phase 1 synthesizer | Best utility-per-dollar on factual narrative; Opus reserved for multi-section |
| 2026-05-01 | Module-pattern pipeline (not class-based ABC) | Simplest mental model; graceful degradation lives in one orchestrator |
| 2026-05-01 | Cache-as-fixture for tests | One mechanism for cache + tests; no mock drift |
| 2026-05-01 | Tiered voice post-processor (substitute for collectors, raise for synthesizers) | Matches actual failure modes |
| 2026-05-01 | Anonymizer ships fully-implemented in Phase 1 with synthetic-data tests | Architecture rests on it; cutting corners bites Phase 2 |
| 2026-05-02 | Gemini integration deferred to Phase 3 | Phase 1 already cost-optimized; abstraction earns its keep when Opus calls land in Phase 2/3 |
