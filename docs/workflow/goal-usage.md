# Using `/goal` on rrxray

Claude Code's `/goal` sets a session-scoped completion condition. After every controller turn, a small fast model (Haiku) judges whether the condition holds against the in-transcript evidence. If not, the next turn fires automatically. The goal clears when the condition is met or the operator runs `/goal clear`.

This doc is the canonical convention for using `/goal` on rrxray. The headline rule is also in `CLAUDE.md`; the details live here.

---

## Headline rule

`/goal` is used per **sub-phase execution**, not per full phase. **Auto-mode must be on.** Conditions are **evidence-anchored** (`pytest`, `ruff`, voice check, checkpoint commit) with an explicit **25-turn cap**.

---

## Where `/goal` fits in the workflow

```
brainstorming -> spec -> writing-plans -> /goal-driven sub-phase execution -> checkpoint -> merge
```

The operator stays in the loop at sub-phase boundaries (2.1a, 2.1b, 2.1c, 2.1d, 2.2, 2.2-deep, ...). `/goal` removes the per-turn re-prompting *inside* a sub-phase; it does not replace the human checkpoint *between* sub-phases.

---

## Preconditions (run through before typing `/goal ...`)

1. Auto-mode is on.
2. The plan file referenced in the condition exists at `docs/superpowers/plans/<plan-file>.md` and is the current target.
3. Working directory is the worktree root for this sub-phase. If a worktree was just created, the parent `.env` is symlinked in (per the existing worktree convention).
4. The controller is Opus 4.7 (`claude-opus-4-7`) per the model-selection matrix in CLAUDE.md.
5. The sub-phase is not in the "do not use" list below.

---

## Standard condition template

Copy this and edit the plan path. Do not change the evidence list without a reason — these are the artifacts the Haiku evaluator can actually see.

```
Implementation plan docs/superpowers/plans/<plan-file>.md is fully executed.
Proof required in transcript:
  - Last `PYTHONPATH=. .venv/bin/python -m pytest tests/ -v` run shows 0 failures, 0 errors.
  - Last `PYTHONPATH=. .venv/bin/python -m ruff check rrxray/ tests/` run exits clean.
  - For any task that renders customer-facing text: the voice/brand
    post-processor was applied and produced no forbidden-word hits.
  - A checkpoint file at docs/checkpoints/<YYYY-MM-DD>-<phase-id>-checkpoint.md
    has been committed (visible in the last `git log -1`).
Or stop after 25 turns.
```

---

## Controller responsibilities

The Haiku evaluator only judges what's in the conversation. The controller must:

- Actually run `PYTHONPATH=. .venv/bin/python -m pytest tests/ -v` and `PYTHONPATH=. .venv/bin/python -m ruff check rrxray/ tests/` toward the end of the sub-phase. Not just dispatch a subagent that runs them — the **output** must land in the controller transcript.
- Surface voice-check output the same way for any task that renders customer-facing text.
- Run `git log -1` after committing the checkpoint, so the commit hash + message appear in-transcript.

If any of those outputs is missing from the transcript, the evaluator will judge "no" even when the work is actually done.

---

## Failure modes

**Goal hits the 25-turn cap.** Default response: **do not re-set the same goal.** Read the last few turns. Decide whether to escalate the controller model (per the matrix in CLAUDE.md), split the sub-phase, or fix the plan. Re-setting blindly burns turns and budget.

**Subagent comes back BLOCKED repeatedly.** The controller escalates the implementer model (Sonnet -> Opus) per the matrix. `/goal` does not paper over BLOCKED dispatches — three BLOCKED dispatches on the same task means the operator re-engages.

**Evaluator returns "yes" but the work is not really done.** Rare with the evidence-anchored template, but possible if the condition was rewritten loosely. Mitigation: stick to the template above; if a condition needs more flexibility, fall back to manual dispatch.

**`/clear` mid-session.** Wipes the active goal. Convention: don't `/clear` while a `/goal` is active unless intentionally aborting.

---

## When NOT to use `/goal`

- **Phases that hit paid third-party APIs in a loop.** PDL enrichment (Phase 2.2-deep) is the standing example — an auto-mode loop with a bug can drain budget fast. Manual dispatch only for paid-API-heavy work.
- **Brainstorming, spec writing, plan writing.** Taste tasks. Condition-verification does not apply.
- **Sub-phases without independent build tasks.** No build tasks = nothing for the evaluator to wait on. Just run it manually.
- **Final quality-gate iteration on customer-facing narrative.** When the operator wants to read every diff, dispatch manually.

A note on headless / `claude -p "/goal ..."`: works in principle, but unattended `/goal` on rrxray is out of scope for this convention. The 25-turn cap is the only backstop without an operator at the keyboard.

---

## Worked example 1: Phase 2.5b buyer_sentiment collector

Plan: `docs/superpowers/plans/2026-05-19-rrxray-phase-2.5b-buyer-sentiment.md`

Operator setup:
1. Create worktree: `git worktree add .claude/worktrees/phase-2.5b-buyer-sentiment feat/phase-2.5b-buyer-sentiment`
2. Symlink env: `ln -s "$(pwd)/.env" .claude/worktrees/phase-2.5b-buyer-sentiment/.env`
3. Open Claude Code in the worktree root; select Opus 4.7; enable auto-mode.

Goal command:

```
/goal Implementation plan docs/superpowers/plans/2026-05-19-rrxray-phase-2.5b-buyer-sentiment.md is fully executed.
Proof required in transcript:
  - Last `PYTHONPATH=. .venv/bin/python -m pytest tests/ -v` run shows 0 failures, 0 errors.
  - Last `PYTHONPATH=. .venv/bin/python -m ruff check rrxray/ tests/` run exits clean.
  - A checkpoint file at docs/checkpoints/2026-05-19-phase-2.5b-buyer-sentiment-checkpoint.md
    has been committed (visible in the last `git log -1`).
Or stop after 25 turns.
```

Operator re-engages when: goal clears (success), the 25-turn cap fires, or any failure mode above triggers.

---

## Worked example 2: a Phase-2.2-style collector sub-phase

Same shape as Example 1, with two differences worth calling out for collector phases:

- If the collector renders any synthesizer output (Section A or B narrative), the voice/brand post-processor line in the condition is **load-bearing**, not optional. Make sure the controller actually invokes the post-processor and surfaces its output.
- If the collector talks to a paid API in any loop (e.g. PDL Person Search inside a per-role loop), this sub-phase is in the "do not use" list — dispatch manually.

---

## See also

- Project model-selection matrix: `CLAUDE.md` section "MANDATORY: Model selection per task"
- Checkpoint mandate: `CLAUDE.md` section "MANDATORY: Checkpoint after every phase"
- Worktree env handling: auto-memory `feedback_worktree_env.md`
