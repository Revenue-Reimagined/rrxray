# Briefing: Phase 2.2 `leadership_stability` Collector

> **Paste-able onboarding prompt for a Claude Coder taking Phase 2.2 in parallel with Phase 2.1d (handled by another Coder). Hand this to a fresh session as the first user message.**

---

## You are taking ownership of Phase 2.2 of `rrxray`

`rrxray` is a Python CLI for Revenue Reimagined. It runs an externally-sourced GTM diagnostic against a B2B prospect's domain and produces a Markdown report — the "GTM X-Ray™" — that surfaces signals only an outside operator sees: pricing posture, tech stack, hiring shape, customer concentration, leadership stability, positioning drift, buyer sentiment.

**You are the owner of Phase 2.2: `leadership_stability` collector.** A second Coder owns Phase 2.1d (`content_demand`) in parallel. You will rarely touch the same files; coordination is light.

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
/Users/dalezwizinski/Library/Python/3.9/bin/uv run pytest -v 2>&1 | tail -3
```

Expected: `251 passed, 1 skipped`. If different, something has shifted from the recorded baseline; investigate before doing new work.

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

## What's already shipped that you build on

- `FirecrawlClient.search()` — async wrapper around `firecrawl-py` SDK's search. Returns `list[SearchResult]` with `url`, `title`, `description`, `metadata`. Cached, concurrency-capped. Built in Phase 2.1c. Reuse it; don't extend it.
- `WaybackClient` — already used by `pricing_packaging`. Has retry-with-backoff for 503s. Reuse it.
- The `CollectorContext` / `CollectorOutputs` pattern — your collector returns a `LeadershipStabilityData` object that gets assigned to `CollectorOutputs.leadership_stability`. Same shape as the existing three Section A collectors.
- `Finding` / `SourceCitation` / `voice/rr_voice.py` — emit findings with citations; voice processor sanitizes / raises on brand violations. Reuse them.
- `superpowers:subagent-driven-development` workflow — fresh subagent per task, two-stage review, TDD discipline. Use it.

You are NOT the first collector to do search-based work; you're the third. The patterns are well-worn.

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

## Coordination with the other Coder

Another Coder is building Phase 2.1d (`content_demand`) on a separate branch off the same `main`. You will rarely conflict because:

- Different collector module, different schema file, different tests, different fixtures, different renderer partial — separate phases means separate files.
- Three files DO carry coordination cost: `CLAUDE.md`, `roadmap.md`, `rrxray/pipeline.py`, `rrxray/schemas/data.py`. Edit these only via your phase's PR, not as drive-by commits, and rebase off `main` if the other Coder merges first.
- The Section A synthesizer prompt is owned by Phase 2.1d (it's a Section A signal). You touch the **Section B** synthesizer prompt — different file. Zero conflict.

If you ever feel like you're stepping on the other Coder's toes, write a partial-progress checkpoint immediately and surface it to Dale. Don't try to coordinate directly with the other Coder mid-flight.

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

## When in doubt

Read the most recent checkpoint at `docs/checkpoints/`. It has everything you need to pick up where the prior session left off. Phase 2.2 is your phase; Phase 2.1c (`revenue_motion`) is the closest analog. Phase 2.1d (`content_demand`) is happening in parallel; stay clear of its files unless coordinating with Dale.
