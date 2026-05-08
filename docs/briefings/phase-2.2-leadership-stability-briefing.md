# Briefing: Phase 2.2 `leadership_stability` Collector

> **Paste-able onboarding prompt for a Claude Coder taking Phase 2.2 in parallel with Phase 2.1d (handled by another Coder). Hand this to a fresh session as the first user message.**

---

## You are taking ownership of Phase 2.2 of `rrxray`

`rrxray` is a Python CLI for Revenue Reimagined. It runs an externally-sourced GTM diagnostic against a B2B prospect's domain and produces a Markdown report — the "GTM X-Ray™" — that surfaces signals only an outside operator sees: pricing posture, tech stack, hiring shape, customer concentration, leadership stability, positioning drift, buyer sentiment.

**You are the owner of Phase 2.2: `leadership_stability` collector.** A second Coder owns Phase 2.1d (`content_demand`) in parallel. You will rarely touch the same files; coordination is light.

---

## Authority and decision rights — read this first

You are a **contributor**. You are not an admin or a project owner. The hierarchy:

| Role | Person / Account | Authority |
|---|---|---|
| Project owner + final approver | **Dale** (`dzwiziski`) | Approves specs, plans, prompt iterations, and merges all PRs to `main` |
| Co-administrator + parallel Coder | **`adamrevenuereimagined`** + the Coder owning Phase 2.1d | Builds Phase 2.1d in parallel; reviews PRs that touch shared files |
| You | **`gtmgapsoftware`** (this Coder) | Builds Phase 2.2 only; opens PRs; does NOT merge to `main` |

**Decisions you make alone:**

- TDD task ordering inside your plan
- Internal collector implementation details (helper function names, regex patterns, error-handling shape) as long as they conform to the patterns below
- Test fixture content
- Subagent dispatch + model selection per the matrix

**Decisions you do NOT make alone — Dale signs off before you proceed:**

- Phase scope (in/out of scope items in your spec)
- Public schema shape (`LeadershipStabilityData` field names + types)
- Synthesizer prompt content (Section B is new territory; the prompt design matters)
- Any change to a file outside your phase's owned files (see "Files you own" below)
- Any new third-party dependency
- Any new top-level abstraction (a new client class, a new shared utility module, a new directory under `rrxray/`)

**If you're not sure whether a decision is yours or Dale's, it's Dale's.** Surface it as a question in the spec or PR before acting.

**You do not coordinate directly with the parallel Coder.** All cross-Coder coordination goes through Dale. If Phase 2.1d's work conflicts with yours, you flag it to Dale; Dale resolves the order. This avoids two Coders independently deciding the same shared-file change.

---

## Step 0: Get the code

The repo lives on GitHub at `https://github.com/Revenue-Reimagined/rrxray` (private). Dale will have invited your GitHub account as a collaborator before you read this. If you can't access the repo, that invite is the blocker — surface it to Dale.

Clone it:

```bash
gh repo clone Revenue-Reimagined/rrxray
# or, if you prefer SSH or don't have gh:
# git clone https://github.com/Revenue-Reimagined/rrxray.git
cd rrxray
```

Verify environment health before doing any work:

```bash
uv run pytest -v 2>&1 | tail -3
```

Expected: `251 passed, 1 skipped`. If different, something has shifted from the recorded baseline; investigate before doing new work.

You'll need a `.env` file at the repo root with `ANTHROPIC_API_KEY` and `FIRECRAWL_API_KEY` for live runs (Dale will provide these out-of-band; do not commit them, they are gitignored). Synthetic-fixture tests do not require keys; the dry-run command does not require keys; only live `rrxray run` calls do.

---

## Read these in order before doing anything

1. `CLAUDE.md` — project memory. Mandatory checkpoint rule, workflow conventions, model-selection matrix, brand voice rules, environment gotchas. **Non-negotiable.**
2. `~/.claude/projects/-Users-dalezwizinski-Documents-Apps-rrxray/memory/MEMORY.md` (and the files it links to) — auto-loaded user memory, including the model-selection rule.
3. The most recent checkpoint at `docs/checkpoints/` (sort by date) — current state of `main`, last commit, what just shipped, what's queued.
4. The most recent **completed-phase** checkpoint — gives you the canonical pattern this project uses for shipping a phase. As of writing, that's Phase 2.1c (`revenue_motion`). Read its spec at `docs/superpowers/specs/` and its plan at `docs/superpowers/plans/`. Phase 2.1c is the closest analog to what you're about to build — same shape (new collector + schema + prompt block + pipeline registration), just for a different signal area.
5. `roadmap.md` — phased roadmap with decisions log.

After those five files you have full context. Skip everything else.

---

## What you're building (Phase 2.2 scope, subject to your brainstorming)

`leadership_stability` is a **Section B** collector (Stability and Trajectory Signals). It surfaces whether the prospect's revenue leadership is stable, in transition, or recently turned over — a real signal for outside-in GTM diagnosis because leadership churn precedes motion changes by 3-9 months.

**Probable in-scope signals (validate during brainstorming):**

- Press release / news search via `FirecrawlClient.search()` for executive hires, departures, promotions
- Wayback comparison of `/team`, `/about`, `/leadership` pages to detect roster changes over time
- LinkedIn snippet search for current C-suite via `FirecrawlClient.search()` (same pattern Phase 2.1c uses for LinkedIn job postings)
- Founder tenure inferred from earliest reachable mention

**Probable out of scope:**

- Per-person LinkedIn profile scraping (login-walled, paid-API territory)
- Glassdoor employee sentiment (Phase 2.3 `buyer_sentiment` territory)
- Per-employee Wayback diffing (too noisy)

**Hard rule:** No paid third-party APIs (Coresignal, PeopleDataLabs, Apollo). Public sources only.

---

## Patterns you must mirror (compatibility + mergeability)

You are the **fourth** collector to ship in this codebase. Three patterns are now well-worn (`pricing_packaging`, `tech_stack`, `revenue_motion`); your work must mirror them so the merged result is internally consistent. Pick the closest analog (Phase 2.1c `revenue_motion` — also search-based, also catalog-driven) and follow its shape.

### Mandatory patterns to copy

| Pattern | Where to copy from | Notes |
|---|---|---|
| Collector module structure | `rrxray/collectors/revenue_motion.py` | Exposes `NAME` constant, `async def collect(ctx)`, internal helpers prefixed `_`. Returns a fully-validated pydantic model. |
| Schema file location + shape | `rrxray/schemas/revenue_motion.py` | One file per collector. Pydantic v2. Optional fields default to `None` or `[]`. Uses `Finding` + `SourceCitation` from `rrxray/schemas/_shared.py`. |
| Catalog file (if you need one) | `rrxray/collectors/_revenue_motion_catalog.py` | Underscore-prefixed module name, lives next to the collector, hardcoded data (no LLM in collector path). |
| Forward-ref registration in `data.py` | Phase 2.1c diff on `rrxray/schemas/data.py` | One line in `CollectorOutputs` + one import + one `model_rebuild()` call. That's it. |
| Pipeline registration | Phase 2.1c diff on `rrxray/pipeline.py` | One line in `COLLECTORS` list. |
| Renderer Module Detail partial | `templates/_revenue_motion_detail.md.jinja` | New file at `templates/_leadership_stability_detail.md.jinja`. Same shape: heading + table + findings/gaps/questions. Included via `{% include %}` in the main report template. |
| Test layout | `tests/test_revenue_motion*.py` | Three files: `tests/test_leadership_stability.py` (collector behavior), `tests/test_leadership_stability_catalog.py` (if you have a catalog), `tests/test_leadership_stability_schemas.py` (round-trip + validation). |
| Synthetic test fixtures | `tests/fixtures/synthetic/revenue_motion/` | Static HTML / JSON files, no live API calls in unit tests. New dir at `tests/fixtures/synthetic/leadership_stability/`. |
| Naming conventions | All existing files | `snake_case` for files + functions + module-level constants when they're data; `PascalCase` for pydantic models + classes; `UPPER_SNAKE` only for true constants like `NAME` and catalog lists. Lowercase string literals for category enums. |
| Commit message style | `git log --oneline -20` | Short imperative subject (under 70 chars), body explains *why*, no Claude Code attribution unless explicitly asked. |

### Patterns to reuse — do not re-implement

| Capability | Class / function | Where it lives |
|---|---|---|
| Web scrape with cache + concurrency cap | `FirecrawlClient.scrape_url()` | `rrxray/services/firecrawl_client.py` |
| Web search with cache + concurrency cap | `FirecrawlClient.search()` | `rrxray/services/firecrawl_client.py` |
| Wayback availability + retry | `WaybackClient.snapshots()` | `rrxray/services/wayback_client.py` |
| Anthropic LLM call with prompt caching | `AnthropicClient.complete_with_cached_system()` | `rrxray/services/anthropic_client.py` |
| Brand-voice sanitization (em-dash + forbidden-word substitution) | `VoicePostProcessor` | `rrxray/voice/rr_voice.py` |
| Findings + source citations | `Finding`, `SourceCitation` | `rrxray/schemas/_shared.py` |

If you find yourself wanting to add a method to any of those classes, **stop and ask Dale.** Phase 2.1c added `FirecrawlClient.search()` because three downstream phases needed it; that scope decision was explicit. Drive-by additions to shared services break compatibility for the parallel Coder.

### Voice / brand discipline

- Apply `process_collector_text()` to any text your collector emits (findings, gaps, discovery questions). It substitutes forbidden words and inserts the GTM Gap™ trademark.
- Apply `sanitize_llm_output()` then `process_synthesizer_text()` to LLM-generated text in your synthesizer (mirrors the pattern in `rrxray/synthesizers/observed_gtm_motion.py`).
- Forbidden words: `leverage`, `leveraging`, `leveraged`, `leverages`, `synergies`, `synergy`, `holistic`, `streamline` (+ inflections), `impactful`. Sanitizer auto-substitutes; do not work around this. If your prompt produces a new forbidden-word pattern, propose adding it to the substitution table via your PR with a sentence of rationale.
- Use `→` (not a hyphen, not an em-dash) for recommendation bullets — see existing collector findings for examples.

You are NOT the first collector to do search-based work; you're the third. The patterns are well-worn.

---

## Files you own / files you do not touch

### Files you OWN — create these as part of Phase 2.2

```
rrxray/collectors/leadership_stability.py             [new — your collector]
rrxray/collectors/_leadership_stability_catalog.py    [new — your catalog, if needed]
rrxray/schemas/leadership_stability.py                [new — your schema]
rrxray/synthesizers/observed_stability_trajectory.py  [new — Section B synthesizer; name TBD via brainstorming]
rrxray/prompts/observed_stability_trajectory.md       [new — Section B prompt; name TBD]
templates/_leadership_stability_detail.md.jinja       [new — Module Detail partial]
tests/test_leadership_stability.py                    [new]
tests/test_leadership_stability_catalog.py            [new, if applicable]
tests/test_leadership_stability_schemas.py            [new]
tests/test_synthesizer_observed_stability_trajectory.py  [new]
tests/fixtures/synthetic/leadership_stability/        [new directory]
```

### Files you MAY MODIFY — but only via your phase's PR, with a single focused diff

```
rrxray/schemas/data.py            [add ONE field to CollectorOutputs + ONE import + extend model_rebuild]
rrxray/pipeline.py                [add ONE entry to COLLECTORS list, ONE entry to SYNTHESIZERS list]
templates/report_internal.md.jinja [include your new partial in the Module Detail Appendix]
roadmap.md                        [add a single line under the Phase 2.2 entry recording what shipped]
docs/checkpoints/<date>-phase-2.2-checkpoint.md  [new — write this BEFORE opening the PR]
```

### Files you MUST NOT modify without explicit Dale approval

```
CLAUDE.md                                          [project-wide rules; cross-phase impact]
rrxray/services/firecrawl_client.py                [shared client; reuse as-is]
rrxray/services/wayback_client.py                  [shared client; reuse as-is]
rrxray/services/anthropic_client.py                [shared client; reuse as-is]
rrxray/voice/rr_voice.py                           [shared voice processor; propose changes via PR comment, not code]
rrxray/schemas/_shared.py                          [shared types: Finding, SourceCitation, VoiceEvent]
rrxray/schemas/data.py [beyond the one-line addition above]
rrxray/cli.py                                      [shared CLI; dynamic dry-run already reads pipeline.COLLECTORS]
rrxray/config.py                                   [shared config; ENV-var handling already correct]
rrxray/pipeline.py [beyond the registrations above]
```

### Files owned by Phase 2.1d — KEEP OUT

```
rrxray/collectors/content_demand.py                [Phase 2.1d's collector]
rrxray/schemas/content_demand.py                   [Phase 2.1d's schema]
rrxray/synthesizers/observed_gtm_motion.py         [Section A synthesizer; Phase 2.1d adds the fourth signal]
rrxray/prompts/observed_gtm_motion.md              [Section A prompt; Phase 2.1d updates this]
templates/_content_demand_detail.md.jinja          [Phase 2.1d's renderer partial]
tests/test_content_demand*.py                      [Phase 2.1d's tests]
tests/fixtures/synthetic/content_demand/           [Phase 2.1d's fixtures]
```

If you find yourself opening any of those Phase 2.1d files, **stop**. You're outside your lane.

---

## Workflow you must follow

This project uses the `superpowers` skill family. Non-negotiable:

1. **`superpowers:brainstorming`** → produces a design spec at `docs/superpowers/specs/<date>-rrxray-phase-2.2-leadership-stability-design.md`. STOP for Dale's review before moving to the plan.
2. **`superpowers:writing-plans`** → produces an implementation plan at `docs/superpowers/plans/<date>-rrxray-phase-2.2-leadership-stability.md` with tasks in TDD checklist form.
3. **`superpowers:subagent-driven-development`** → execute the plan, dispatching one subagent per task. Two-stage review (spec compliance + code quality) after each non-mechanical task. Push your branch to GitHub regularly (`git push -u origin feat/phase-2.2-leadership-stability`) so progress is visible to Dale and the other Coder.
4. **Quality gate** — Dale-led live smoke against three real domains (typically Swayable, SQA Services, Linear; same as Phase 2.1b/2.1c so we get apples-to-apples comparison). Iterate the synthesizer prompt 1-2 times if needed.
5. **Checkpoint** — write `docs/checkpoints/<date>-phase-2.2-checkpoint.md` BEFORE opening the PR. Use `docs/checkpoints/TEMPLATE.md`. Read at least one prior checkpoint first to match the format.
6. **Open a PR** against `main` on GitHub (`gh pr create`). Dale reviews, merges, and closes the loop. Do NOT merge to `main` yourself; Dale gates the merge after validation.

---

## Model-selection matrix (loaded from CLAUDE.md, summarized here)

| Task | Model |
|---|---|
| Real-logic implementer (multi-function code, parsing, integration glue) | **Opus 4.7** |
| Mechanical implementer (schema, fixtures, registration) | **Haiku 4.5** |
| Spec / code-quality reviewer | **Haiku 4.5** |
| Brainstorming, spec writing, plan writing, prompt tuning | **Opus 4.7** |
| Final whole-branch review | **Opus 4.7** |

Dispatch subagents accordingly. This is Dale's explicit ask: pay the premium where logic-writing matters, save where it's mechanical.

---

## Coordination with the other Coder (rules of engagement)

The parallel Coder is building Phase 2.1d (`content_demand`) on a separate branch off the same `main`. Your work is structurally independent — see the Files lists above. The remaining coordination rules:

1. **Pull `main` daily** to stay in sync with whatever Phase 2.1d (or Dale) merges. Use `git pull --rebase origin main` from your branch; do **not** merge `main` into your branch (creates messy history that's hard to review).
2. **If `main` advances during your work,** rebase your feature branch off the new `main` at a clean checkpoint (e.g., between TDD tasks, not mid-task). Resolve conflicts surgically; if a conflict touches `pipeline.py` or `schemas/data.py`, both phases will have added entries — keep both, don't discard.
3. **Push your branch frequently** so Dale and the parallel Coder can see what you're building. A pushed branch is the only signal of progress they have.
4. **Open a draft PR early** (`gh pr create --draft`). It surfaces your scope to Dale and the parallel Coder before you've finished. They can comment on the spec/plan even before code lands.
5. **No direct coordination with the parallel Coder.** All cross-phase signaling goes through Dale. If you think the parallel Coder's work is going to break yours, comment on Dale's review thread or your own PR — don't @-mention or message the other Coder.
6. **Conflict-resolution trumps speed.** If you're rebasing and uncertain about a merge conflict, push a partial-rebase commit to a temp branch and ask Dale. Don't guess and force-push.

**If you ever feel like you're stepping on the other Coder's toes, write a partial-progress checkpoint immediately and surface it to Dale.** Don't try to coordinate directly with the other Coder mid-flight.

---

## Environment

- Working dir: `/Users/dalezwizinski/Documents/Apps/rrxray` (use a worktree via `superpowers:using-git-worktrees`)
- Python 3.14 in `.venv/`
- `uv` at `/Users/dalezwizinski/Library/Python/3.9/bin/uv` (not on standard PATH — use full path or alias it)
- API keys in `.env` (gitignored). `ANTHROPIC_API_KEY`, `FIRECRAWL_API_KEY`. Empty env vars in shell shadow `.env`; the Phase 1 fix at `rrxray/config.py` filters them out.
- Test runner: `uv run pytest -v`
- Lint: `uv run ruff check rrxray/ tests/`
- Live run: `uv run rrxray run --domain example.com`
- Dry-run (no API calls): `uv run rrxray run --domain example.com --dry-run`

After picking up, verify env health:

```bash
cd /Users/dalezwizinski/Documents/Apps/rrxray
/Users/dalezwizinski/Library/Python/3.9/bin/uv run pytest -v 2>&1 | tail -3
```

If the test count is wrong vs. what the latest checkpoint records, something has shifted; investigate before doing new work.

---

## Your first action

After reading the five orientation files above, **invoke `superpowers:using-git-worktrees`** to create your isolated workspace, then **invoke `superpowers:brainstorming`** to scope Phase 2.2. Brainstorming will produce questions for Dale. Get those answers before writing the spec.

Do not start implementation until the spec is reviewed by Dale and you've moved through `superpowers:writing-plans`.

---

## Anti-patterns: ways this can go wrong

These are things prior sessions almost did or did do once. Don't repeat them.

- **Adding a method to `FirecrawlClient` / `WaybackClient` / `AnthropicClient` to handle "your" use case.** Stop and ask Dale. Phase 2.1c added `FirecrawlClient.search()` because three downstream phases needed it; that decision was explicit, not drive-by. Drive-by additions to shared services break the parallel Coder.
- **Touching the Section A synthesizer (`rrxray/synthesizers/observed_gtm_motion.py`) or its prompt.** That's Phase 2.1d's territory. You build a new Section B synthesizer in a new file.
- **Letting an "implementer" subagent decide schema field names without surfacing them to Dale.** Schema names go in the spec for review BEFORE implementation. Renaming fields after merge is expensive.
- **Skipping the spec → Dale review → plan → Dale review pattern** because the work feels obvious. The pattern caught real bugs in Phase 2.1a (substring matching corruption), 2.1b (doubled-evidence path), 2.1c (firecrawl-py SDK signature drift). Stay disciplined.
- **Using a model below the matrix's recommendation** to save tokens. Real-logic implementer = Opus 4.7 per Dale's explicit ask. Saving on the wrong tier produces shallow code that has to be redone.
- **Force-pushing your feature branch after Dale has commented on the PR.** Append commits, don't rewrite history once review is in flight.
- **Adding a paid third-party API** to gather "richer" leadership data. The "no paid third-party APIs" rule is a project constraint, not a default you can override.
- **Skipping the voice processor** on text your collector emits. Findings, gaps, and discovery questions all run through `process_collector_text()`. LLM output runs through `sanitize_llm_output()` then `process_synthesizer_text()`. Do not bypass either layer.
- **Writing live API calls into your unit tests.** Synthetic fixtures only. The Phase 2.1c plan's fixture files are the model — copy that pattern.
- **Editing `CLAUDE.md` to add your own preferences.** That file is project-wide doctrine. Propose changes via PR with explicit rationale; don't drive-by edit.

---

## When in doubt

Read the most recent checkpoint at `docs/checkpoints/`. It has everything you need to pick up where the prior session left off. Phase 2.2 is your phase; Phase 2.1c (`revenue_motion`) is the closest analog. Phase 2.1d (`content_demand`) is happening in parallel; stay clear of its files unless coordinating with Dale.

**Final rule:** if a decision feels like it has impact beyond your phase's owned files, surface it to Dale before acting. Asking is cheap; an unauthorized cross-phase change is expensive to unwind.
