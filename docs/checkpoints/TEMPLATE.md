# [Phase ID] Checkpoint — [YYYY-MM-DD]

> **Purpose:** Self-contained handoff document. A fresh Claude session (or a different human) should be able to read this in 5 minutes and pick up where the prior session left off.

**Phase status:** [Done | In progress | Blocked | Partial — running low on context]
**Branch:** `feat/...`
**Last commit:** `<sha>`
**Test status:** N passed, M skipped, ruff clean (or describe failures)
**Total elapsed:** approximate hours of subagent execution

---

## What this phase shipped

Bullet list of deliverables. Be specific.

- [Deliverable 1]
- [Deliverable 2]

---

## Where the work lives

- **Spec:** `docs/superpowers/specs/...`
- **Plan:** `docs/superpowers/plans/...`
- **New / modified files:** list paths grouped by area (collectors, schemas, services, tests)
- **Notable commits:** SHA + short message for the most important commits in this phase

---

## Test status

Paste the tail of `uv run pytest -v 2>&1 | tail -10` or describe.

```
[paste test output]
```

`uv run ruff check rrxray/ tests/` — clean / list violations.

---

## Known issues / limitations

What surfaced during this phase but didn't get fixed. Not crashes — those should be fixed before checkpointing. These are deferred concerns or trade-offs accepted for this phase.

- [Issue 1] — deferred to [phase / never / when X]
- [Issue 2] — accepted because [reason]

---

## Environment gotchas

Setup quirks the next user needs to know about. Skip if nothing new (CLAUDE.md already covers the standing list).

- [Quirk] — [how to handle]

---

## What's queued next

Be concrete. Name the next phase, where the spec/plan live (or where they'll be written), and why this is the priority.

**Next phase:** [Phase X.Y — name]

- **Spec:** `docs/superpowers/specs/...` ([written | not yet written | in progress])
- **Plan:** `docs/superpowers/plans/...` ([written | not yet written | in progress])
- **Why this is next:** [one sentence]
- **Roughly how big:** [task count + hours estimate]

---

## Open todos / in-flight work

Anything started but not finished. If the session ended cleanly with no in-flight work, write "None."

- [Todo] — [status]

---

## Process notes

What workflow was used (subagent-driven, inline, hybrid). What worked. What didn't. What the next session should do differently. Token-budget observations.

- [Note]

---

## Pointers

Links to key docs the next session will want.

- [`roadmap.md`](../../roadmap.md) — phased roadmap with decisions log
- [Prior checkpoint] — `docs/checkpoints/<previous>-checkpoint.md`
- [Relevant spec / plan files for the next phase]
