# rrxray Project Memory (Claude reads this on session start)

This file is the project-level memory for any Claude Code session working in this repository. Read it before doing anything else.

---

## MANDATORY: Checkpoint after every phase

This is non-negotiable. Cannot be skipped under any circumstances.

**You must write a checkpoint document to `docs/checkpoints/<date>-<phase-id>-checkpoint.md` and commit it BEFORE moving on whenever any of these triggers fire:**

1. **A phase milestone completes** (e.g., Phase 1 foundation, Phase 2.1a tech_stack collector, Phase 2.1b Section A synthesizer upgrade). The phase is not "done" until the checkpoint is written and committed.
2. **Before merging a feature branch into `main`**. The checkpoint is the handoff document for whoever reads the merged work.
3. **Any session-continuity risk.** If there's any chance the current session may end before the next natural milestone, write a partial-progress checkpoint immediately. Do not wait for the next user message. The checkpoint must include in-flight work, the current task, what was just attempted, and what the next session should pick up. Triggers include but are not limited to:
   - **Context-window pressure** — the conversation is approaching the model's context limit
   - **5-hour session rate limit** — Claude's per-session token budget is depleting
   - **Weekly usage cap** — approaching the user's plan-level weekly quota
   - **User flags it** — if the user mentions they're worried about running out of tokens, hours, or weekly capacity, treat that as a hard trigger and checkpoint right away
   - **Long-running execution sessions** — if you're dispatching many subagents in a row (Phase-style execution), checkpoint at sub-phase boundaries even if the full phase isn't done

   When in doubt, checkpoint. A partial-progress checkpoint that captures in-flight work is far cheaper than losing context on hand-off.

The format is fixed: use `docs/checkpoints/TEMPLATE.md` as the structure. Read at least one prior checkpoint before writing a new one.

The checkpoint must be self-contained. A fresh Claude session (or a different human picking the project up cold) should be able to read the most recent checkpoint and know:

- What the project is and what was just shipped
- The current state of the repo (branch, last commit, test status)
- What's queued next and where the design spec / implementation plan lives
- Known issues, gotchas, and environment quirks
- How to run the tool
- Process notes (workflow being used, decisions made about pacing)

If a Claude session ends without a checkpoint when one was due, the next session must write one retroactively before doing any new work.

---

## Project orientation

**rrxray** is a Python CLI tool for Revenue Reimagined. It runs an externally-sourced GTM diagnostic against a B2B prospect's domain, producing a Markdown report ("GTM X-Ray™") that surfaces signals only an outside operator sees: pricing posture, tech stack, hiring shape, customer concentration, leadership stability, positioning drift, buyer sentiment.

**Status:** Phase 1 foundation shipped. Phase 2 in progress (collector-by-collector buildout). See `roadmap.md` and the most recent checkpoint at `docs/checkpoints/`.

**Key paths:**

- `roadmap.md` — phased roadmap with decisions log
- `docs/superpowers/specs/` — design docs, one per phase or sub-phase
- `docs/superpowers/plans/` — implementation plans, one per spec
- `docs/checkpoints/` — phase handoff documents (write one after every phase)
- `rrxray/` — source code
- `tests/` — pytest suite

---

## Workflow conventions

We use the `superpowers` skill family on this project:

- **brainstorming** → spec doc → user review
- **writing-plans** → implementation plan
- **subagent-driven-development** → one fresh subagent per task, two-stage review (spec compliance + code quality), TDD discipline

This workflow has caught real bugs across Phase 1 (substring matching corruption in the anonymizer, firecrawl-py SDK signature drift, doubled-evidence path bug, env-var shadowing issue). Stay disciplined.

**Sub-phases over mega-phases.** Phase 1 was 23 tasks across 7 sub-phases. Phase 2 is being built one collector at a time (2.1a, 2.1b, ...) so each cycle ships a visible deliverable. Don't accept "let me brainstorm Phase 2 in one shot" — that scope produces a sprawling spec that's hard to course-correct mid-build.

**Voice and brand discipline.** Every rendered output must follow Revenue Reimagined brand voice: no em dashes, no forbidden words (leverage, synergies, holistic, streamline, impactful), → for recommendation bullets, GTM Gap™ on first use. The `voice/rr_voice.py` post-processor enforces this on collector and synthesizer text. Apply it loosely to docs; apply it strictly to anything rendered to a customer or prospect.

---

## MANDATORY: Model selection per task — Balance Quality, Cost, Speed

This is non-negotiable. Dale's explicit ask: "best model for the best action for the best price." Apply on every subagent dispatch and every model decision. Default-to-Sonnet wastes budget on mechanical work; default-to-Haiku produces shallow design. Pick deliberately.

| Task type | Model | Rationale |
|---|---|---|
| Mechanical implementer (schema additions, fixtures, pipeline registration, single-line wiring) | **Haiku 4.5** (`claude-haiku-4-5-20251001`) | Pattern-following work |
| Real-logic implementer (multi-function code, parsing, integration glue, edge cases) | **Sonnet 4.6** (`claude-sonnet-4-6`) | Standard judgment, multi-file coordination |
| Spec compliance review (checklist against design doc) | **Haiku 4.5** | Pure pattern matching against requirements |
| Code quality review (bounded scope, named criteria) | **Haiku 4.5** | Most issues are obvious |
| Final whole-branch code review | **Opus 4.7** (`claude-opus-4-7`) | Broad context, architectural reasoning |
| Brainstorming, spec design, implementation-plan writing | **Opus 4.7** | Multi-step reasoning over ambiguous problem space |
| Prompt tuning, brand-voice review, narrative-quality judgment | **Opus 4.7** | Taste work where Opus pulls clearly ahead of Sonnet |
| Controller during quality-gate / iteration phases | **Opus 4.7** | High-stakes orchestration |
| Controller during routine TDD execution | **Sonnet 4.6** | Orchestration only; reasoning is in subagents |
| Live smoke runs, commits, mechanical checkpoint writing | **Sonnet 4.6 or Haiku 4.5** | Bash plumbing, no judgment |

**Escalation signals:**
- Subagent returns BLOCKED on a Sonnet implementer task → escalate to Opus and re-dispatch (don't retry Sonnet unless the gap was clearly contextual)
- Haiku reviewer misses something Opus would catch → upgrade that review-step to Sonnet
- "Mechanical" task takes >2 iterations → it wasn't actually mechanical; upgrade and re-dispatch

**Push this forward:** Every checkpoint should record which model handled which task so the next session inherits the working pattern. If a model choice produced a bad outcome, document the specific failure rather than abandoning the matrix.

---

## Environment gotchas

These are real issues encountered during Phase 1; future sessions should know about them.

- **Empty `ANTHROPIC_API_KEY=""` in shell shadows `.env`.** If `os.environ['ANTHROPIC_API_KEY']` is set to an empty string (a common shell-profile artifact), pydantic-settings prefers env vars over `.env` files (correct behavior) and the empty string wins over the real `.env` value. The Phase 1 fix in `rrxray/config.py` filters empty env vars out at the env-source layer so they fall through to the `.env` file. If a user reports auth errors despite a populated `.env`, check `os.environ` and have them `unset ANTHROPIC_API_KEY` in their shell.
- **`uv run rrxray` fails with `ModuleNotFoundError: No module named 'rrxray'` on Python 3.14.** The hatchling-editable `.pth` file is generated without a trailing newline, and Python 3.14's site processor is stricter. Fix: `printf '\n' >> .venv/lib/python*/site-packages/_editable_impl_rrxray.pth`.
- **archive.org returns 503s under load.** The Wayback availability lookup has retry-with-backoff (1s, 2s) but if archive.org is having a sustained outage, snapshots will simply be unavailable. Graceful degradation handles this — the report shows "zero Wayback Machine snapshots were recovered" and the synthesizer turns it into a finding.

---

## How to run the tool

```bash
# Dry-run (no API calls; shows estimated cost)
uv run rrxray run --domain example.com --dry-run

# Live run (needs ANTHROPIC_API_KEY + FIRECRAWL_API_KEY in .env or env)
uv run rrxray run --domain example.com

# Tests
uv run pytest -v

# Lint
uv run ruff check rrxray/ tests/
```

Output lands in `xray-{domain-slug}-{YYYYMMDD}/` (gitignored).

---

## When in doubt

Read the most recent checkpoint at `docs/checkpoints/`. It has everything you need to pick up where the prior session left off.
