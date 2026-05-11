# Briefing: Complete Phase 2.2-deep

> **Paste-able onboarding doc for a fresh Claude session picking up Phase 2.2-deep where the build left off. The implementation (T1-T9) is committed and pushed; what remains is `/review`, the live quality gate (T10), and merge.**

---

## What you're picking up

**Phase 2.2-deep of rrxray** is the PeopleDataLabs (PDL) leadership enrichment that closes the "tenure unconfirmed" narrative gap from Phase 2.2. The build is done — 9 commits across 9 TDD tasks, 378 tests passing, ruff clean. What's left:

1. **`/review`** the 9-commit Phase 2.2-deep diff against `main` to catch any bugs tests didn't surface (Phase 2.2's /review pass caught 5 real bugs; this is now standard practice per the saved memory `feedback_phase_review`)
2. **Fix anything `/review` finds**
3. **T10 live quality gate**: smoke against Swayable + aioapp + remote.com with PDL enabled
4. **Iterate prompts** if narratives need calibration (Phase 2.2 needed 5 iterations; budget for 1-2 here)
5. **Update the checkpoint + roadmap + PR description** to reflect quality-gate completion
6. **Merge to main**

You are NOT rebuilding anything. All build code is in place and tested.

---

## Read these in order (5 minutes)

1. [`CLAUDE.md`](../../CLAUDE.md) — project memory, model-selection matrix, brand voice, environment gotchas, architectural rules (incl. the Phase 2.2 amendments about LLM-in-collector-path and the "one approved data partner per signal area" rule that authorized PDL)
2. [`docs/checkpoints/2026-05-11-phase-2.2-deep-pdl-enrichment-checkpoint.md`](../checkpoints/2026-05-11-phase-2.2-deep-pdl-enrichment-checkpoint.md) — **this is the canonical handoff document**. It has the exact build state, the 5 implementer adaptations from the plan worth verifying, known issues, and the queue.
3. [`docs/superpowers/specs/2026-05-11-rrxray-phase-2.2-deep-pdl-enrichment-design.md`](../superpowers/specs/2026-05-11-rrxray-phase-2.2-deep-pdl-enrichment-design.md) — the design spec
4. [`docs/superpowers/plans/2026-05-11-rrxray-phase-2.2-deep-pdl-enrichment.md`](../superpowers/plans/2026-05-11-rrxray-phase-2.2-deep-pdl-enrichment.md) — the implementation plan that the 9 build commits executed against. Only useful for cross-referencing what the spec required vs what the code does.
5. [`docs/checkpoints/2026-05-10-phase-2.2-leadership-stability-checkpoint.md`](../checkpoints/2026-05-10-phase-2.2-leadership-stability-checkpoint.md) — for context on Phase 2.2's narrative quality (Phase 2.2-deep is supposed to improve on it)

After those, skip everything else.

---

## Prerequisites — confirm before doing live work

Without these you can do `/review` and code fixes, but T10's live smoke will fail.

1. **Anthropic credits funded.** Phase 2.2 sign-off flagged that credits ran out mid-quality-gate. Confirm with `curl https://api.anthropic.com/v1/messages -H "x-api-key: $ANTHROPIC_API_KEY" -H "anthropic-version: 2023-06-01" -H "content-type: application/json" -d '{"model":"claude-haiku-4-5-20251001","max_tokens":1,"messages":[{"role":"user","content":"hi"}]}'` — if this returns a 200 with content, credits are fine.

2. **PDL API key obtained.** Sign up at peopledatalabs.com if needed. Add to the parent repo's `.env` as `PDL_API_KEY=<your-key>`. PDL is approved as the one data partner for the leadership signal area per `CLAUDE.md` (see "Architectural rules" section).

3. **Worktree `.env` symlink.** If running from a git worktree (which is the current setup), the worktree needs its own `.env` symlink to the parent. From the worktree root:
   ```bash
   ln -sf /Users/dalezwizinski/Documents/Apps/rrxray/.env .env
   ```

4. **Always `cd` to worktree root** before any `uv run rrxray` invocation. The Bash tool's cwd persists across commands; a stray `cd` into an output sub-directory will break `.env` discovery. Memory `feedback_worktree_env` documents this.

---

## Step 1: Verify build state matches the checkpoint

```bash
cd /Users/dalezwizinski/Documents/Apps/rrxray/.claude/worktrees/unruffled-chandrasekhar-93625c
git log --oneline -3
/Users/dalezwizinski/Library/Python/3.9/bin/uv run pytest 2>&1 | tail -3
/Users/dalezwizinski/Library/Python/3.9/bin/uv run ruff check rrxray/ tests/
```

Expected:
- HEAD at `657d301` (Phase 2.2-deep checkpoint)
- Pytest: `378 passed, 1 skipped`
- Ruff: clean

If anything differs, STOP and investigate — the world has shifted from the recorded state.

---

## Step 2: Run `/review` over the Phase 2.2-deep diff

Per the saved feedback memory `feedback_phase_review`, this runs after every phase build and before merge.

```
/review Review all code shipped in Phase 2.2-deep of rrxray (9 commits, a227c00 through 26b7d91). The phase added PeopleDataLabs (PDL) leadership enrichment via a new PDLClient + LeadershipEnrichment orchestrator, replaced the Phase 2.2 LinkedIn snippet path entirely, extended schemas + synthesizer aggregates, and added cost cap + circuit breaker with graceful degradation. Commits in order: a227c00 (PDLClient), 371ad58 (schemas), 63556cd (config + CLI), 7e42fb3 (LeadershipEnrichment orchestrator), e819578 (pipeline wire-up), b0581bb (collector integration — replaces LinkedIn path), 988616b (deletes extract_linkedin_role), 6e8b438 (synthesizer aggregates + prompt), 26b7d91 (renderer template). Spec: docs/superpowers/specs/2026-05-11-rrxray-phase-2.2-deep-pdl-enrichment-design.md. Plan: docs/superpowers/plans/2026-05-11-rrxray-phase-2.2-deep-pdl-enrichment.md. Five implementer adaptations from the plan are documented in the checkpoint and worth scrutinizing: (1) actual PyPI package is "peopledatalabs" not "peopledatalabs-python", (2) cost-cap uses soft semantics (current_spend < cap allows next op), (3) LEADERSHIP_ROLES catalog was reshaped from list[tuple[str, str]] to list[tuple[str, list[str]]], (4) external/internal hire heuristic in StabilityAggregates depends on the orchestrator's actual data shape and is verified at synthesis time via the test_aggregates_compute_internal_promotion_count loose-assertion pattern, (5) tenure_months preference is PDL > press-fallback. Adapt the /review skill to local commits via `git diff main..HEAD` instead of `gh pr diff` if needed.
```

The reviewer will surface bugs / risks / code quality issues. Triage by severity (Critical / High / Medium / Low) and fix High+ issues before T10. Phase 2.2's /review caught these patterns that tests had missed:
- Collector findings rendered raw (no voice processing, no anonymization)
- Synthesizer findings dropped at render time (rendered template missed them)
- Date-anchor logic picked first-in-list instead of latest
- Em dashes in rendered output (brand voice violation)

Watch for similar issues in Phase 2.2-deep.

If the reviewer flags bugs, dispatch a fix subagent with the specific findings:

```
Agent({
  description: "Phase 2.2-deep review fixes",
  subagent_type: "general-purpose",
  model: "opus",
  prompt: "<paste reviewer report; verbatim findings; ask for TDD-disciplined fix commits>"
})
```

---

## Step 3: T10 live quality gate

After fixes from Step 2 land (if any):

```bash
cd /Users/dalezwizinski/Documents/Apps/rrxray/.claude/worktrees/unruffled-chandrasekhar-93625c

# RR target ICP — sign-off bar
/Users/dalezwizinski/Library/Python/3.9/bin/uv run rrxray run --domain swayable.com --no-cache
/Users/dalezwizinski/Library/Python/3.9/bin/uv run rrxray run --domain aioapp.com --no-cache

# Generic-name stress test (replaces Linear from Phase 2.2)
/Users/dalezwizinski/Library/Python/3.9/bin/uv run rrxray run --domain remote.com --no-cache
```

`--no-cache` forces fresh PDL + Firecrawl + Anthropic calls. Expected duration: 2-5 minutes per domain. Expected cost: ~$3 per domain (~$1 PDL + ~$0.04 Firecrawl + ~$0.06 Opus synthesizer + small Haiku extractor + small Sonnet Section A synth).

For each report, verify against [the project ICP memory](../../~/.claude/projects/-Users-dalezwizinski-Documents-Apps-rrxray/memory/project_xray_icp.md) — Swayable and aioapp are the actual sign-off bar; remote.com is a regression check.

Quality gate checklist per report:

1. **Tenure data populated.** `data.json` → `collectors.leadership_stability.current_incumbents` should have `tenure_months` set on multiple incumbents (was almost always `None` in Phase 2.2).
2. **Prior employer populated.** Same field set should have `prior_employer` + `prior_role` for most incumbents.
3. **Section B narrative cites the new aggregates.** Look for phrases like "X of Y current incumbents have tenure data confirmed" or "the incoming CRO came from [employer], suggesting [motion lens]."
4. **"Tenure unconfirmed" gaps reduced.** Compare against the Phase 2.2 Swayable narrative (commit `56857a8`-era output retained at `xray-swayable-com-20260509/report.internal.md` if not deleted). Phase 2.2-deep should materially close those gaps.
5. **Voice clean.** No em dashes; no forbidden words (leverage, synergies, holistic, streamline, impactful); GTM Gap™ on first use.
6. **Anonymizer correct.** PDL-found names replaced with role descriptors at render time. Press-whitelisted names preserved.
7. **Cost reasonable.** `data.json` → `collectors.leadership_stability.enrichment_metadata.spend_dollars` ≤ $5 (default cap). ~$2-3 in normal operation per the spec's cost ceiling.
8. **Aborted_reason completed.** Should read "completed" not "cost_cap" or "circuit_breaker" in normal runs.

Also run one `--no-pdl` smoke to verify graceful fallback:

```bash
/Users/dalezwizinski/Library/Python/3.9/bin/uv run rrxray run --domain swayable.com --no-cache --no-pdl
```

Expected: completes; report falls through to "Signal Not Recovered" hypothesis for incumbents; press change names lack enrichment.

---

## Step 4: Iterate prompts if quality gate flags issues

Phase 2.2 needed 5 iterations on the synthesizer prompt to nail Swayable. Phase 2.2-deep should need 1-2 at most because the data is richer.

Common iteration patterns:

- **LLM doesn't cite tenure_confirmed_count even when it's available** → tighten the "Tenure confirmation" block in `rrxray/prompts/observed_stability_trajectory.md`
- **Motion-lens inferences over-speculative** → tighten the "do not speculate on unknown employers" guard in the same prompt
- **External/internal hire counts skew wrong** → check `_build_aggregates` in `rrxray/synthesizers/observed_stability_trajectory.py` against actual PDL data shapes; the heuristic was deliberately loose per the implementer notes

For each prompt change, re-run the affected domain with `--no-cache` and inspect Section B in the report.

---

## Step 5: Sign off — checkpoint update + roadmap + PR description

When the trio of smokes produces narratives you'd hand a client:

1. **Write a completion entry** appended to `docs/checkpoints/2026-05-11-phase-2.2-deep-pdl-enrichment-checkpoint.md` (under a new section "## Quality gate (T10) — completed"). Include: the four domain smokes' summary (hypotheses committed, tenure_confirmed counts, voice log clean / dirty, any iteration commits), final test status, final PR commit count.

2. **Update `roadmap.md`** — find the existing Phase 2.2 entry under `leadership_stability` and append a Phase 2.2-deep line:
   ```
   - 2026-05-XX: Phase 2.2-deep shipped — PeopleDataLabs enrichment. Per-X-Ray cost ~$2.91; default cap $5. Closes the "tenure unconfirmed" narrative gap. Quality gate signed off against [domains].
   ```

3. **Update the existing PR description** ([rrxray#1](https://github.com/Revenue-Reimagined/rrxray/pull/1)) to cover both Phase 2.2 AND Phase 2.2-deep — they're stacked on the same branch. Or split into two PRs at merge time if cleaner.

4. **Commit + push** these updates.

5. **Merge** the PR (you have merge authority).

---

## What's queued AFTER Phase 2.2-deep merges

Per the existing roadmap:

- **Phase 2.1d `content_demand` collector** — completes Section A (4 collectors). Spec/plan not written; brainstorm at start.
- **Phase 2.4 Section B widening** — adds `funding_trajectory` + `customer_concentration` collectors to complete Section B. Each adds a conditional block to the `observed_stability_trajectory` synthesizer; no synthesizer-shape change.

Either could run in parallel with each other on separate branches per the existing two-Coder coordination protocol.

---

## Workflow you must follow

This project uses the `superpowers` skill family:

- **`/review`** for the Phase 2.2-deep diff scrutiny in Step 2
- **`superpowers:subagent-driven-development`** if Step 2 surfaces multiple distinct fixes that warrant fresh subagents per fix
- **One-off `Agent` dispatches** for single-issue fixes (with verification-proof requirement: implementer must paste `git log --oneline -1`, `pytest 2>&1 | tail -3`, and `ruff check` output in the report. Phase 2.2's T6 caught a Haiku hallucination this way.)
- **`superpowers:finishing-a-development-branch`** at the end (Step 5) for the merge

The CLAUDE.md model matrix governs subagent dispatches:

| Task | Model |
|---|---|
| `/review` (whole-branch analysis) | Opus 4.7 (inherent to the skill) |
| Single-file bug fix on real logic | Opus 4.7 |
| Mechanical fix (rename, docstring, import) | Haiku 4.5 |
| Live smoke commits + checkpoint writing | Sonnet 4.6 or Haiku 4.5 |
| Prompt iteration after quality-gate finding | Opus 4.7 (taste work) |

---

## Anti-patterns from prior phases

Specific things prior sessions almost did or did do once:

- **Running live smokes from the parent repo (on `main`) instead of the worktree.** Phase 2.2 wasted two smoke runs (~$0.08 + debugging time) because the Bash tool `cd` left cwd in `/Users/dalezwizinski/Documents/Apps/rrxray` (parent, on `main`) instead of the worktree which had Phase 2.2 code. ALWAYS `cd /Users/dalezwizinski/Documents/Apps/rrxray/.claude/worktrees/unruffled-chandrasekhar-93625c` before any `uv run rrxray`.
- **Working from a stale checkpoint.** Phase 2.2 nearly redid Phase 2.1c because the stale checkpoint said "Phase 2.1c execution pending." Verify state matches checkpoint via `git log` BEFORE starting work.
- **Letting an "implementer" subagent decide schema field names mid-task.** Schema names go in spec / plan / checkpoint before implementation. Renaming after merge is expensive.
- **Skipping `/review` because tests passed.** Tests passing ≠ correctness. Phase 2.2 caught 5 real bugs via `/review` after tests + ruff were green.
- **Iterating prompts more than 2 cycles.** If the third iteration doesn't fix the calibration, the issue is data-side, not prompt-side. Look at what's actually in `data.json` rather than rephrasing the prompt.
- **Marking T10 complete unilaterally.** T10 is Dale-led by design. The session pauses for human review before declaring done.

---

## Environment quick-reference

- Working dir: `/Users/dalezwizinski/Documents/Apps/rrxray/.claude/worktrees/unruffled-chandrasekhar-93625c`
- Python: 3.14 in `.venv/`
- uv: `/Users/dalezwizinski/Library/Python/3.9/bin/uv` (full path; not on standard PATH)
- API keys in `.env` (gitignored, symlinked from parent)
- Test runner: `/Users/dalezwizinski/Library/Python/3.9/bin/uv run pytest`
- Lint: `/Users/dalezwizinski/Library/Python/3.9/bin/uv run ruff check rrxray/ tests/`

---

## When in doubt

Read the checkpoint at `docs/checkpoints/2026-05-11-phase-2.2-deep-pdl-enrichment-checkpoint.md`. It has everything needed to resume cleanly.

---

## The paste-able first-message prompt

Copy this and paste it as the first message of a fresh Claude session, after Claude finishes loading skills:

```
I'm resuming Phase 2.2-deep of rrxray. The build is complete (T1-T9, 9 commits, 378 tests passing, ruff clean) and pushed to PR #1. What remains is /review of the Phase 2.2-deep diff, fixing anything it flags, the T10 live quality gate (Swayable + aioapp + remote.com), then merge.

Read `docs/briefings/phase-2.2-deep-completion-briefing.md` for the full picture. Start by verifying build state matches the checkpoint per Step 1 of the briefing, then proceed through Steps 2-5.

Prerequisites I'll need to confirm before T10 fires:
- Anthropic credits funded (carry-over concern from Phase 2.2 sign-off)
- PDL_API_KEY set in worktree .env (peopledatalabs.com account required)
- Worktree .env symlinked from parent (per feedback_worktree_env memory)

Treat the briefing as canonical. If something contradicts the checkpoint, the checkpoint wins (it's the most recent record).
```
