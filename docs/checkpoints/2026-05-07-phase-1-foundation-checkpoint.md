# Phase 1 Foundation Checkpoint — 2026-05-07

> **Purpose:** Self-contained handoff document. A fresh Claude session (or a different human) should be able to read this in 5 minutes and pick up where the prior session left off.

**Phase status:** Done
**Branch:** `feat/phase-1-foundation` (not yet merged to `main`)
**Last commit:** `a30a111` (Phase 2.1a implementation plan; Phase 1 work itself ends at `1023999`)
**Test status:** 126 passed, 1 skipped, ruff clean
**Total elapsed:** roughly 6 hours of subagent execution at full review depth, plus 3 follow-up fix commits surfaced by the first live runs

---

## What this phase shipped

The complete Phase 1 foundation as scoped in the original spec:

- Project scaffolding (pyproject + uv + ruff + pytest)
- Canonical pydantic schemas (`XrayData`, `CollectorOutputs`, `SynthesizerOutputs`, plus shared types `Finding`, `SourceCitation`, `ModuleFailure`, `VoiceEvent`)
- Service-client wrappers with disk-cache layer (`FirecrawlClient`, `AnthropicClient` with prompt caching, `WaybackClient` with retry-with-backoff)
- Tiered voice post-processor (substitute for collectors, raise for synthesizers) with `peek_log` / `flush_log` for renderer integration
- Anonymizer with name registry + press-release whitelist + render-time defense-in-depth check
- `pricing_packaging` collector end-to-end (URL discovery, tier extraction, contact-us detection, Wayback diff, evidence writing, source citations)
- Section A pricing-only synthesizer (Sonnet 4.6 with prompt caching, structured output via tool-use)
- Markdown renderer with seven-section skeleton; Jinja filters for `voice_collector`, `anonymize`; globals for `voice_events` and `collected_discovery_questions`
- Pipeline orchestrator with `asyncio.gather(return_exceptions=True)` graceful degradation, post-render voice flush, `validate_assignment=True` on output schemas, `CancelledError` propagation
- Typer CLI with `run`, `collect`, `synthesize`, `render` subcommands and Phase 1 mode validation
- Config (pydantic-settings) with `.env` support and empty-env-var filtering so a shell-shadowed empty key falls through to `.env`
- Dry-run cost estimator
- Cache-as-fixture testing pattern (`live` / `replay-only` / `refresh` modes; tests run fully offline)
- End-to-end smoke test (skipped until fixtures bootstrapped)
- Two real live runs against `sqaservices.com` and `swayable.com` produced clean reports

---

## Where the work lives

- **Spec:** `docs/superpowers/specs/2026-05-01-rrxray-phase-1-foundation-design.md`
- **Plan:** `docs/superpowers/plans/2026-05-01-rrxray-phase-1-foundation.md`
- **Roadmap:** `roadmap.md` (Phase 1-4 scope, decisions log)
- **New code:**
  - `rrxray/cli.py`, `rrxray/config.py`, `rrxray/pipeline.py`, `rrxray/context.py`
  - `rrxray/schemas/` (data.py, _shared.py, pricing_packaging.py)
  - `rrxray/services/` (cache.py, firecrawl_client.py, anthropic_client.py, wayback_client.py)
  - `rrxray/collectors/pricing_packaging.py`
  - `rrxray/synthesizers/observed_gtm_motion_pricing.py`
  - `rrxray/voice/rr_voice.py`, `rrxray/voice/anonymizer.py`
  - `rrxray/rendering/markdown.py`
  - `rrxray/prompts/synthesizer_system.md`, `rrxray/prompts/observed_gtm_motion_pricing.md`
  - `rrxray/modes/` (base.py, internal.py)
  - `templates/report_internal.md.jinja`, `templates/_pricing_detail.md.jinja`
- **Tests:** 126 in `tests/` covering schemas, cache, voice, anonymizer, contexts, three service clients, pricing collector (19 tests), synthesizer, render, pipeline graceful degradation, CLI, dry-run estimator, end-to-end smoke
- **Notable commits:**
  - `e7c3637` — initial scaffolding
  - `b55a220` / `cd83ce5` — voice post-processor + empty-string guard fix
  - `7d0dba9` / `db584d1` — anonymizer + critical substring-corruption fix
  - `e7dd313` / `9180c3a` — Firecrawl client + SDK signature fix (v2 `scrape()` migration)
  - `0709bfc` / `ea0e55c` — Wayback client + per-target failure tolerance
  - `75a5bdf` / `78f94ae` — pricing_packaging collector finalization + stale-evidence cleanup
  - `25a8454` / `bff554e` — Section A synthesizer + voice processing on findings/gaps/questions
  - `b688043` / `bf058dd` — Markdown renderer + render-time anonymity check
  - `ad9bd6f` / `c037ebd` — pipeline orchestrator + CancelledError + validate_assignment
  - `c7d7ea9` — Config (pydantic-settings)
  - `d415f83` — typer CLI
  - `fc052aa` — dry-run accuracy test
  - `98cbf8e` — e2e smoke test
  - `31d4051` — roadmap.md
  - `7f9403f` — empty-env-var filtering fix (post-live-run)
  - `4f2cfea` — doubled `evidence/evidence/` path fix (post-live-run)
  - `1023999` — Wayback retry-with-backoff (post-live-run)

---

## Test status

```
======================== 126 passed, 1 skipped in 0.66s ========================
```

`uv run ruff check rrxray/ tests/` — clean.

The 1 skipped is `tests/test_end_to_end.py::test_full_pipeline_against_smoke_domain`. It skips until fixtures are bootstrapped via `RRXRAY_FIXTURE_BOOTSTRAP=1 uv run pytest tests/test_end_to_end.py -v -s` against a real domain with real API keys.

---

## Known issues / limitations

These surfaced during Phase 1 but were intentionally deferred to later phases:

- **Cache thundering-herd race**: N concurrent calls for the same uncached URL will all hit upstream. Atomic file writes mean the cache stays consistent, but cost is multiplied. Deferred to Phase 2 (per `roadmap.md`).
- **Voice log entries from a failed synthesizer persist in the flush.** Minor traceability concern. Deferred.
- **Pricing tier extraction is heuristic.** Misses markdown tables, bold-pseudo-headings, FAQ pollution, locales using period-as-thousands (`$1.200,50`). Phase 1 acceptable; Phase 2 might tighten.
- **Templates packaging for wheel installs**: `_templates_dir()` resolves to repo-root `templates/`, which works in editable / dev mode but breaks under `pip install`. Deferred to Phase 4.
- **archive.org availability**: even with the new retry-with-backoff (1s, 2s), sustained outages produce zero snapshots. The graceful-degradation path turns this into a finding rather than a crash. Acceptable.

---

## Environment gotchas

Already covered in `CLAUDE.md`. Quick reference:

- Empty `ANTHROPIC_API_KEY=""` in shell shadows `.env`. Phase 1 fix `7f9403f` filters empty env vars, so this is now resolved at the Config layer. Still worth knowing about if a user reports auth errors.
- Python 3.14 + hatchling-editable: the auto-generated `.pth` file lacks a trailing newline; Python 3.14's site processor needs one. Fix: `printf '\n' >> .venv/lib/python*/site-packages/_editable_impl_rrxray.pth`.
- `firecrawl-py` v4.24.0 exposes `FirecrawlApp` as v2 `Firecrawl`. The `.scrape()` method (not `.scrape_url`) takes keyword-only args. Phase 1's Firecrawl client uses the v2 surface correctly.

---

## What's queued next

**Next phase:** Phase 2.1a — `tech_stack` collector

- **Spec:** `docs/superpowers/specs/2026-05-07-rrxray-phase-2.1a-tech-stack-design.md` (written, committed at `dd14b9f`)
- **Plan:** `docs/superpowers/plans/2026-05-07-rrxray-phase-2.1a-tech-stack.md` (written, committed at `a30a111`)
- **Why this is next:** Smallest possible cycle inside Phase 2 — adds ONE new collector (no synthesizer change) to validate the new-collector pattern works for non-pricing collectors before scaling up to add 7 more. After this lands, Phase 2.1b is the Section A synthesizer upgrade reading from pricing + tech_stack.
- **Roughly how big:** 8 TDD tasks across 4 sub-areas (schemas, catalog, collector logic, renderer + pipeline). ~2-3 hours of subagent execution at full review depth.

After Phase 2.1a:
- 2.1b: Section A synthesizer upgrade (multi-collector)
- 2.1c: `revenue_motion` collector
- 2.1d: `content_demand` collector
- 2.2: Section B (`stability_trajectory`) — funding_trajectory + leadership_stability + customer_concentration + synthesizer
- 2.3: Section C (`external_voice_vs_internal`) — buyer_sentiment + positioning_drift + synthesizer
- 2.4: Executive Summary synthesizer
- Phase 3: Modes (hook / leave-behind / qbr) + PDF / Gamma / dashboard renderers + Gemini integration
- Phase 4: Polish, packaging for wheel installs, smoke runs against more real domains

See `roadmap.md` for full Phase 2-4 scope and the decisions log.

---

## Open todos / in-flight work

Phase 1 ended cleanly. No partial work.

Phase 2.1a was approved and the user chose **Subagent-Driven** as the execution mode. The next action is to invoke `superpowers:subagent-driven-development` and start dispatching task implementers, beginning with Task 1 (TechStackData + DetectedTool schemas).

---

## Process notes

**Workflow that worked:**

- `superpowers:brainstorming` → spec → user review → `superpowers:writing-plans` → plan → `superpowers:subagent-driven-development` → fresh subagent per task with two-stage review (spec compliance + code quality) → live smoke runs.
- TDD discipline (test first → fail → implement → pass → commit) caught real bugs across Phase 1.
- Subagent-driven execution with full reviews ran ~15-25 minutes per task. Phase 1's 23 tasks took roughly 6 hours of subagent execution. Phase 2.1a's 8 tasks should take 2-3 hours.
- Splitting Phase 1 into 7 sub-phases (1A foundation, 1B service clients, 1C pricing collector, 1D synthesizer, 1E renderer, 1F pipeline+CLI, 1G smoke) made the long execution tractable.
- Code-quality reviewer caught two CRITICAL bugs (anonymizer substring corruption, Firecrawl SDK signature mismatch) that would have shipped silently otherwise. The review loop is earning its keep.

**What didn't work / lessons:**

- The plan's prescribed code occasionally didn't match the prescribed tests (e.g., T11 had `_extract_tiers` skip no-$ sections but the test asserted Enterprise-with-no-$ should be a tier). Implementers handled this by satisfying the tests and noting the deviation.
- The `firecrawl-py` SDK had drifted significantly between when the plan was written and when it was implemented. The implementer SDK-introspected the actual installed version and adapted. Plan a similar introspection step for any future LLM SDK or scraping client.
- Live runs surfaced three real bugs (env-var shadowing, doubled-evidence-path, Wayback 503 propagation) that unit tests didn't catch. Live smoke runs against a real domain are mandatory before declaring a phase done.

**Pacing observations:**

- Total Phase 1: 36 commits over a single session. Branch hasn't merged to main yet.
- Single-session token consumption was significant. The volume of subagent dispatches + reports adds up. For Phase 2 the user requested checkpointing for cross-session handoff (this document).

---

## Pointers

- [`CLAUDE.md`](../../CLAUDE.md) — project memory (this is what every Claude session reads on entry)
- [`roadmap.md`](../../roadmap.md) — phased roadmap with decisions log
- [`docs/checkpoints/TEMPLATE.md`](TEMPLATE.md) — checkpoint format
- [Phase 1 design spec](../superpowers/specs/2026-05-01-rrxray-phase-1-foundation-design.md)
- [Phase 1 implementation plan](../superpowers/plans/2026-05-01-rrxray-phase-1-foundation.md)
- [Phase 2.1a design spec](../superpowers/specs/2026-05-07-rrxray-phase-2.1a-tech-stack-design.md)
- [Phase 2.1a implementation plan](../superpowers/plans/2026-05-07-rrxray-phase-2.1a-tech-stack.md)
