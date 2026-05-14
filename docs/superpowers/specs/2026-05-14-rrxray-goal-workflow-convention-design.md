# rrxray /goal Workflow Convention Design

**Date:** 2026-05-14
**Status:** Approved (brainstorming complete)
**Scope:** Process / workflow convention (no code)
**Touches:** `CLAUDE.md`, new `docs/workflow/goal-usage.md`

---

## Context

Claude Code shipped `/goal` ([docs](https://code.claude.com/docs/en/goal)) — a session-scoped autonomous loop. The operator sets a completion condition; after every controller turn a small fast model (Haiku by default) judges whether the condition holds against the in-transcript evidence. If not, the next turn fires automatically. The goal clears when the condition is met or the operator runs `/goal clear`.

`/goal` is a natural fit for this project's sub-phase execution step. Sub-phases (2.1a → 2.2-deep) already have a clear shape: a small set of build tasks dispatched to fresh subagents under an Opus controller, gated by `pytest` + `ruff` + voice-check + checkpoint. Today the operator manually re-prompts the controller between subagent dispatches. `/goal` removes that per-turn prompting once auto-mode is on, while preserving the existing human checkpoint at sub-phase boundaries.

This spec defines when and how `/goal` is used on rrxray, what a standard condition looks like, and where the convention is documented.

---

## Scope

### In scope

- Project convention: when `/goal` is used (per sub-phase, not per full phase), what preconditions must hold (auto-mode on, plan exists, worktree root, Opus controller), and what the standard condition looks like (evidence-anchored, 25-turn cap).
- New documentation file `docs/workflow/goal-usage.md` containing the full convention, the condition template, two worked examples (one Phase-2.1-shaped sub-phase, one Phase-2.2-shaped sub-phase), and a failure-modes section.
- Addendum to `CLAUDE.md` — short "## /goal usage" section with the headline rule and a pointer to the standalone doc. Mirrors the existing pattern for checkpoints (mandate in CLAUDE.md, template/details in a sibling doc).
- This design document.

### Out of scope (future cycles)

- Writing a custom Stop hook to replace the default Haiku evaluator with a deterministic check (could be useful if Haiku judgements drift; not needed now).
- Headless / `claude -p "/goal …"` usage. One-line mention in the standalone doc, not a designed flow.
- Retrofitting completed phases. Convention applies forward from Phase 2.1d onward.
- Changing the existing brainstorming / writing-plans / subagent-driven-development workflow. `/goal` slots into the controller-execution step only.
- A new skill file. The convention lives as project docs, not a superpowers skill.

---

## Decisions Locked During Brainstorming

| # | Decision | Choice | Rationale |
|---|---|---|---|
| Q1 | Target use case | General workflow primitive for this project (option A) | A pilot-then-codify path (option C) doubles the work; the convention is small enough to write directly. Phase 2.1d can be the first natural application. |
| Q2 | Integration model | One `/goal` per sub-phase, not per full phase (option B) | Preserves the human checkpoint at sub-phase boundaries where course-correction already happens. A goal that wraps a whole phase gives up the natural review points; a goal that only wraps the "finishing" tail captures too little of the value. |
| Q3 | Condition shape | Evidence-anchored — literal commands whose output must appear in-transcript (option B) | The Haiku evaluator can only judge what Claude surfaces. Plan-anchored conditions ("all tasks complete") depend on plan-file hygiene; evidence-anchored conditions name the proof directly (`pytest` exit 0, `ruff` clean, commit visible in `git log -1`). Robust against plan drift. |
| Q4 | Turn cap | 25 turns | Matches observed sub-phase shape: 3–8 build tasks (one controller turn per subagent dispatch) plus checkpoint plus retry slack for BLOCKED dispatches. 15 is too tight given how often a subagent comes back BLOCKED; 40 stops being a real safety net. Past 25 turns, something off-plan happened and the operator should re-engage. |
| Q5 | Auto-mode posture | Required for `/goal` sessions | Without auto-mode each tool call still prompts, so the operator sits at the keyboard either way — most of the `/goal` win is lost for ~0 safety gain (the 25-turn cap is the real backstop). Bounded by the plan and the evidence-anchored condition, auto-mode is acceptable for the work `/goal` drives here. |
| Q6 | When NOT to use | Phases hitting paid third-party APIs in a loop, brainstorming/spec/plan steps, phases without independent build tasks | Paid APIs in an auto-mode loop are a runaway-cost risk (PDL specifically — Phase 2.2 caught one such bug already). Taste tasks aren't condition-verifiable. Plans without independent tasks have nothing for the evaluator to wait on. |
| Q7 | Documentation surface | One-line pointer in `CLAUDE.md`, full convention in `docs/workflow/goal-usage.md` (option C) | Mirrors the established checkpoint pattern. `CLAUDE.md` stays scannable; the full convention has room to breathe and grow. |

---

## Convention summary (what goes in the docs)

### Headline rule (CLAUDE.md addendum)

> `/goal` is used per sub-phase execution, not per full phase. Auto-mode must be on. Conditions are evidence-anchored (`pytest`, `ruff`, voice check, checkpoint commit) with an explicit 25-turn cap. Full convention and condition template: `docs/workflow/goal-usage.md`.

### Preconditions checklist (operator runs before typing `/goal …`)

1. Auto-mode is on.
2. Plan file referenced in the condition exists and is the current target.
3. Working directory is the worktree root for this phase (matches existing worktree convention — symlink parent `.env` first).
4. Opus 4.7 is the controller model (per the model-selection matrix in CLAUDE.md).
5. The sub-phase is not in the "do not use" list (paid-API-in-loop, taste work, plans without independent tasks).

### Standard condition template

```
Implementation plan docs/superpowers/plans/<plan-file>.md is fully executed.
Proof required in transcript:
  - Last `uv run pytest -v` run shows 0 failures, 0 errors.
  - Last `uv run ruff check rrxray/ tests/` run exits clean.
  - For any task that renders customer-facing text: the voice/brand
    post-processor was applied and produced no forbidden-word hits.
  - A checkpoint file at docs/checkpoints/<YYYY-MM-DD>-<phase-id>-checkpoint.md
    has been committed (visible in the last `git log -1`).
Or stop after 25 turns.
```

### What the controller must do for the condition to be judgeable

The Haiku evaluator only sees what's in the conversation. The controller must:

- Actually run `uv run pytest -v` and `uv run ruff check rrxray/ tests/` toward the end of the sub-phase (not just dispatch a subagent that runs them — the *output* has to land in the controller transcript).
- Surface the voice-check output the same way for any rendered customer-facing text.
- Run `git log -1` after committing the checkpoint, so the commit hash + message appear in-transcript.

If any of those outputs is missing from the transcript, the evaluator will judge "no" even when the work is actually done. The condition template above bakes this in by naming each artifact explicitly.

### Failure modes the doc must call out

- **Goal runs to the 25-turn cap.** Default response: do not re-set the same goal. Read the last few turns + checkpoint risks in CLAUDE.md, decide whether to escalate the controller model, split the sub-phase, or fix the plan. Re-setting blindly burns turns.
- **Subagent comes back BLOCKED repeatedly.** The controller should escalate the implementer model per the matrix (Sonnet → Opus). `/goal` does not paper over this — three BLOCKED dispatches on the same task means the operator re-engages.
- **Evaluator returns "yes" but the work isn't really done.** Rare but possible if the condition is poorly written. The doc names this risk and points to the evidence-anchored template as the mitigation.
- **`/clear` mid-session.** Wipes the active goal. Convention: don't `/clear` while a `/goal` is active unless intentionally aborting.

### When NOT to use /goal (codified)

- Phases that hit paid third-party APIs in a loop. Paid APIs in an auto-mode loop are runaway-cost territory; manual dispatch only.
- Brainstorming, spec writing, plan writing. These are taste tasks. Condition-verification doesn't apply.
- Sub-phases where the plan isn't decomposed into independent build tasks. Without independent tasks the evaluator has nothing to wait on; just run it manually.
- Final quality-gate iteration on customer-facing narrative output where the operator wants to read every diff. Manual.

---

## Files changed by this work

| Path | Change | Notes |
|---|---|---|
| `CLAUDE.md` | New section "## /goal usage" near the existing "Workflow conventions" block | Headline rule + pointer to standalone doc. ~6 lines. |
| `docs/workflow/goal-usage.md` | New file | Full convention. Sections: when to use, preconditions, condition template, controller responsibilities, failure modes, when NOT to use, worked examples (Phase 2.1d, Phase 2.2-style). |
| `docs/superpowers/specs/2026-05-14-rrxray-goal-workflow-convention-design.md` | This file | Approved spec. |

No code, no tests, no schema changes.

---

## Risks

- **Evaluator drift.** Haiku judgements aren't deterministic. The evidence-anchored template minimizes this (the evaluator is looking for specific strings, not making taste calls), but a sufficiently weird condition could still get judged inconsistently. Mitigation: stick to the template; if a condition needs more flexibility, fall back to manual dispatch.
- **Auto-mode + 25-turn cap is the only safety net.** Convention assumes the operator is at the machine and can interrupt. If `/goal` is used unattended (e.g. `claude -p`), the cap is the only thing stopping a stuck loop. The doc will flag this; headless use is out of scope.
- **Convention staleness.** If the underlying workflow evolves (new model in the matrix, new checkpoint requirement, etc.) the standalone doc + the CLAUDE.md pointer can drift apart. Mitigation: the pointer is one short paragraph that names the canonical doc; keep details in one place only.

---

## Success criteria

- `CLAUDE.md` has a "## /goal usage" section pointing to `docs/workflow/goal-usage.md`.
- `docs/workflow/goal-usage.md` exists with: convention summary, preconditions, condition template, controller responsibilities, failure modes, when-not-to-use, and at least one worked example.
- A first real `/goal` invocation (Phase 2.1d is the natural candidate) runs cleanly using the documented condition template, hits its evaluator "yes" before 25 turns, and produces a checkpoint. (This validation step happens during Phase 2.1d execution, not as part of writing the docs.)
