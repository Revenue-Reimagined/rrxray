# rrxray /goal Workflow Convention Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Document a project-wide convention for using Claude Code's `/goal` command on rrxray — per-sub-phase, auto-mode required, evidence-anchored condition with a 25-turn cap.

**Architecture:** Documentation only, no code. Mirrors the existing checkpoint pattern: a short headline rule in `CLAUDE.md` (always loaded into context) plus a standalone reference doc with the full convention, condition template, controller responsibilities, failure modes, and worked examples.

**Tech Stack:** Markdown. No tests, no build steps.

**Spec:** [docs/superpowers/specs/2026-05-14-rrxray-goal-workflow-convention-design.md](../specs/2026-05-14-rrxray-goal-workflow-convention-design.md)

---

## File Structure

| Path | Status | Responsibility |
|---|---|---|
| `docs/workflow/goal-usage.md` | Create | Full convention: when to use, preconditions, condition template, controller responsibilities, failure modes, when NOT to use, two worked examples. Canonical source of truth. |
| `CLAUDE.md` | Modify (insert section between line 56 "Workflow conventions" block and line 72 "MANDATORY: Model selection") | One-paragraph "## /goal usage" pointer. Headline rule + link to the standalone doc. |
| `docs/superpowers/plans/2026-05-14-rrxray-goal-workflow-convention.md` | This file | Tracking. |

Because there is no code, "verification" for each task means reading the file back and confirming the named sections / strings are present. The TDD analog here is: name the required content in the spec, write it, then check it landed.

---

### Task 1: Create the standalone convention doc

**Files:**
- Create: `docs/workflow/goal-usage.md`

- [ ] **Step 1: Create the directory**

Run: `mkdir -p /Users/dalezwizinski/Documents/Apps/rrxray/docs/workflow`
Expected: directory now exists, no output.

- [ ] **Step 2: Write the full convention doc**

Write this exact content to `docs/workflow/goal-usage.md`:

````markdown
# Using `/goal` on rrxray

Claude Code's [`/goal`](https://code.claude.com/docs/en/goal) sets a session-scoped completion condition. After every controller turn, a small fast model (Haiku) judges whether the condition holds against the in-transcript evidence. If not, the next turn fires automatically. The goal clears when the condition is met or the operator runs `/goal clear`.

This doc is the canonical convention for using `/goal` on rrxray. The headline rule is also in `CLAUDE.md`; the details live here.

---

## Headline rule

`/goal` is used per **sub-phase execution**, not per full phase. **Auto-mode must be on.** Conditions are **evidence-anchored** (`pytest`, `ruff`, voice check, checkpoint commit) with an explicit **25-turn cap**.

---

## Where `/goal` fits in the workflow

```
brainstorming → spec → writing-plans → /goal-driven sub-phase execution → checkpoint → merge
```

The operator stays in the loop at sub-phase boundaries (2.1a, 2.1b, 2.1c, 2.1d, 2.2, 2.2-deep, ...). `/goal` removes the per-turn re-prompting *inside* a sub-phase; it does not replace the human checkpoint *between* sub-phases.

---

## Preconditions (run through before typing `/goal …`)

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
  - Last `uv run pytest -v` run shows 0 failures, 0 errors.
  - Last `uv run ruff check rrxray/ tests/` run exits clean.
  - For any task that renders customer-facing text: the voice/brand
    post-processor was applied and produced no forbidden-word hits.
  - A checkpoint file at docs/checkpoints/<YYYY-MM-DD>-<phase-id>-checkpoint.md
    has been committed (visible in the last `git log -1`).
Or stop after 25 turns.
```

---

## Controller responsibilities

The Haiku evaluator only judges what's in the conversation. The controller must:

- Actually run `uv run pytest -v` and `uv run ruff check rrxray/ tests/` toward the end of the sub-phase. Not just dispatch a subagent that runs them — the **output** must land in the controller transcript.
- Surface voice-check output the same way for any task that renders customer-facing text.
- Run `git log -1` after committing the checkpoint, so the commit hash + message appear in-transcript.

If any of those outputs is missing from the transcript, the evaluator will judge "no" even when the work is actually done.

---

## Failure modes

**Goal hits the 25-turn cap.** Default response: **do not re-set the same goal.** Read the last few turns. Decide whether to escalate the controller model (per the matrix in CLAUDE.md), split the sub-phase, or fix the plan. Re-setting blindly burns turns and budget.

**Subagent comes back BLOCKED repeatedly.** The controller escalates the implementer model (Sonnet → Opus) per the matrix. `/goal` does not paper over BLOCKED dispatches — three BLOCKED dispatches on the same task means the operator re-engages.

**Evaluator returns "yes" but the work isn't really done.** Rare with the evidence-anchored template, but possible if the condition was rewritten loosely. Mitigation: stick to the template above; if a condition needs more flexibility, fall back to manual dispatch.

**`/clear` mid-session.** Wipes the active goal. Convention: don't `/clear` while a `/goal` is active unless intentionally aborting.

---

## When NOT to use `/goal`

- **Phases that hit paid third-party APIs in a loop.** PDL enrichment (Phase 2.2-deep) is the standing example — an auto-mode loop with a bug can drain budget fast. Manual dispatch only for paid-API-heavy work.
- **Brainstorming, spec writing, plan writing.** Taste tasks. Condition-verification doesn't apply.
- **Sub-phases without independent build tasks.** No build tasks = nothing for the evaluator to wait on. Just run it manually.
- **Final quality-gate iteration on customer-facing narrative.** When the operator wants to read every diff, dispatch manually.

A note on headless / `claude -p "/goal …"`: works in principle, but unattended `/goal` on rrxray is out of scope for this convention. The 25-turn cap is the only backstop without an operator at the keyboard.

---

## Worked example 1: Phase 2.1d content_demand sub-phase

Plan: `docs/superpowers/plans/2026-05-13-rrxray-phase-2.1d-content-demand.md`.

Operator setup:
1. `git worktree add ../rrxray-2.1d phase-2.1d` (or equivalent).
2. `cd ../rrxray-2.1d && ln -s ../rrxray/.env .env`.
3. Open Claude Code in the worktree; verify Opus 4.7 is selected; enable auto-mode.

Goal command:

```
/goal Implementation plan docs/superpowers/plans/2026-05-13-rrxray-phase-2.1d-content-demand.md is fully executed.
Proof required in transcript:
  - Last `uv run pytest -v` run shows 0 failures, 0 errors.
  - Last `uv run ruff check rrxray/ tests/` run exits clean.
  - For any task that renders customer-facing text: the voice/brand
    post-processor was applied and produced no forbidden-word hits.
  - A checkpoint file at docs/checkpoints/<YYYY-MM-DD>-phase-2.1d-content-demand-checkpoint.md
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

- Claude Code `/goal` docs: https://code.claude.com/docs/en/goal
- Project model-selection matrix: `CLAUDE.md` § "MANDATORY: Model selection per task"
- Checkpoint mandate: `CLAUDE.md` § "MANDATORY: Checkpoint after every phase"
- Worktree env handling: auto-memory `feedback_worktree_env.md`
````

- [ ] **Step 3: Verify all required sections exist**

Run: `grep -n "^## " /Users/dalezwizinski/Documents/Apps/rrxray/docs/workflow/goal-usage.md`
Expected output (in order):
```
## Headline rule
## Where `/goal` fits in the workflow
## Preconditions (run through before typing `/goal …`)
## Standard condition template
## Controller responsibilities
## Failure modes
## When NOT to use `/goal`
## Worked example 1: Phase 2.1d content_demand sub-phase
## Worked example 2: a Phase-2.2-style collector sub-phase
## See also
```
If any header is missing, re-open the file and add the missing section using the spec as the source of truth, then re-run the grep.

- [ ] **Step 4: Voice check the doc for forbidden words**

Run: `grep -niE "leverage|synergies|holistic|streamline|impactful|—" /Users/dalezwizinski/Documents/Apps/rrxray/docs/workflow/goal-usage.md || echo "VOICE OK"`
Expected: `VOICE OK` (the post-processor's banned vocabulary plus em-dash check; the convention doc is internal but the brand discipline still applies loosely).
If any match returns, rewrite the offending line.

- [ ] **Step 5: Commit**

```bash
git add docs/workflow/goal-usage.md
git commit -m "$(cat <<'EOF'
docs: add /goal workflow convention reference

Canonical convention for using Claude Code's /goal on rrxray: per
sub-phase only, auto-mode required, evidence-anchored condition with
a 25-turn cap. Includes condition template, controller responsibilities,
failure modes, and two worked examples (Phase 2.1d + collector-style).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Add the `/goal usage` section to CLAUDE.md

**Files:**
- Modify: `/Users/dalezwizinski/Documents/Apps/rrxray/CLAUDE.md` (insert between line 70 — the end of the "Workflow conventions" section — and line 72 "## MANDATORY: Model selection per task")

- [ ] **Step 1: Confirm the insertion point**

Run: `sed -n '68,74p' /Users/dalezwizinski/Documents/Apps/rrxray/CLAUDE.md`
Expected: line ~70 ends the "Voice and brand discipline" paragraph of the Workflow conventions section, line 71 is blank, line 72 begins `## MANDATORY: Model selection per task — Balance Quality, Cost, Speed`.
If the surrounding text has drifted, locate the same boundary by finding the line containing `## MANDATORY: Model selection per task` and inserting the new section immediately before it (preserving the blank line above the existing header).

- [ ] **Step 2: Insert the new section**

Use Edit to insert the new section. Match this `old_string` (the start of the Model-selection section header plus the preceding blank line):

```
---

## MANDATORY: Model selection per task — Balance Quality, Cost, Speed
```

Replace with:

```
---

## `/goal` usage

`/goal` is used per **sub-phase execution**, not per full phase. **Auto-mode must be on.** Conditions are **evidence-anchored** (`pytest`, `ruff`, voice check, checkpoint commit) with an explicit **25-turn cap**.

Full convention, condition template, and worked examples: `docs/workflow/goal-usage.md`. Do not run `/goal` for paid-API-in-loop phases (e.g. PDL enrichment) — manual dispatch only.

---

## MANDATORY: Model selection per task — Balance Quality, Cost, Speed
```

- [ ] **Step 3: Verify the section landed in the right place**

Run: `grep -n "^## " /Users/dalezwizinski/Documents/Apps/rrxray/CLAUDE.md`
Expected: the new `## ` /goal usage` ` header appears between `## Workflow conventions` and `## MANDATORY: Model selection per task — Balance Quality, Cost, Speed`.
If the ordering is wrong, re-do the Edit.

- [ ] **Step 4: Voice check the CLAUDE.md addendum**

Run: `sed -n '/^## .goal. usage/,/^---$/p' /Users/dalezwizinski/Documents/Apps/rrxray/CLAUDE.md | grep -niE "leverage|synergies|holistic|streamline|impactful|—" || echo "VOICE OK"`
Expected: `VOICE OK`.
If any match returns, rewrite the offending line.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md
git commit -m "$(cat <<'EOF'
docs(CLAUDE.md): add /goal usage section pointing to workflow doc

Headline rule lives in CLAUDE.md (always in context); full convention
is in docs/workflow/goal-usage.md. Mirrors the checkpoint pattern.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Final cross-link and spec-coverage verification

**Files:**
- Read-only: `CLAUDE.md`, `docs/workflow/goal-usage.md`, `docs/superpowers/specs/2026-05-14-rrxray-goal-workflow-convention-design.md`

- [ ] **Step 1: Confirm the CLAUDE.md pointer resolves**

Run: `grep -n "docs/workflow/goal-usage.md" /Users/dalezwizinski/Documents/Apps/rrxray/CLAUDE.md && ls /Users/dalezwizinski/Documents/Apps/rrxray/docs/workflow/goal-usage.md`
Expected: at least one match in CLAUDE.md, file exists.
If either fails: the pointer or the file is missing — fix Task 1 or Task 2 output.

- [ ] **Step 2: Confirm the CLAUDE.md headline matches the standalone doc headline**

Read both: CLAUDE.md "## `/goal` usage" paragraph and `docs/workflow/goal-usage.md` "## Headline rule" paragraph.
Both must say the same three things: (a) per sub-phase, not per full phase; (b) auto-mode required; (c) evidence-anchored, 25-turn cap.
If they drift, update CLAUDE.md to match the standalone doc (the standalone doc is canonical).

- [ ] **Step 3: Spec-coverage check**

Open the spec at `docs/superpowers/specs/2026-05-14-rrxray-goal-workflow-convention-design.md` and walk the "Convention summary" section. Confirm each of the following appears in `docs/workflow/goal-usage.md`:

- [ ] Headline rule (matches CLAUDE.md addendum)
- [ ] Preconditions checklist with all 5 items (auto-mode, plan exists, worktree root, Opus controller, not-in-do-not-use-list)
- [ ] Standard condition template (with pytest, ruff, voice check, checkpoint commit, 25-turn cap)
- [ ] Controller responsibilities (the "must surface output in-transcript" rules)
- [ ] All four failure modes (cap hit, BLOCKED dispatches, false-yes, /clear mid-session)
- [ ] All four when-not-to-use cases (paid APIs in loop, taste tasks, no independent tasks, narrative iteration)
- [ ] Two worked examples (Phase 2.1d, collector-style)

If anything is missing, add it now and amend the previous commit on `docs/workflow/goal-usage.md` (or make a follow-up commit — operator's call based on whether Task 1 is already pushed).

- [ ] **Step 4: Done — no separate commit unless Step 3 surfaced issues**

If Step 3 surfaced no issues, this task closes cleanly. The two prior commits already cover the work.
If Step 3 surfaced fixes, run:

```bash
git add docs/workflow/goal-usage.md CLAUDE.md
git commit -m "$(cat <<'EOF'
docs: fill spec-coverage gaps in /goal workflow docs

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Success criteria (whole plan)

- `docs/workflow/goal-usage.md` exists with all 10 named sections.
- `CLAUDE.md` has a "## `/goal` usage" section that names the headline rule and links to the standalone doc.
- The standalone doc passes a voice check (no forbidden words, no em dashes).
- Spec coverage check in Task 3 passes with no missing items.
- Two commits land cleanly on the working branch (`docs: add /goal workflow convention reference`, `docs(CLAUDE.md): add /goal usage section pointing to workflow doc`); optional third commit only if Task 3 surfaces fixes.

No code changes, no test suite invocation, no pipeline runs. Validation of the convention end-to-end happens on the first real `/goal` invocation (Phase 2.1d is the natural candidate) and is tracked there, not here.
