# rrxray Phase 2.1b: Section A Multi-Collector Synthesizer Design

**Date:** 2026-05-07
**Status:** Approved (brainstorming complete)
**Phase:** 2.1b (smallest possible cycle inside Phase 2)
**Builds on:** Phase 2.1a tech_stack collector (commit `4d3021e`) + Phase 2.1a-fix DOM signatures (commit `90fa9f4`)

---

## Context

Phase 2.1a shipped the `tech_stack` collector. Live runs against `swayable.com` (HubSpot detected via DOM-anchor) and `sqaservices.com` (no martech detected — diagnostic finding) confirm the collector produces output. **But that output isn't yet feeding any narrative.** Section A still uses the Phase 1 pricing-only synthesizer; the tech_stack data sits unused in `data.json` and the Module Detail Appendix.

Phase 2.1b is the smallest cycle that bridges the gap: upgrade the Section A synthesizer to read from BOTH collectors and produce a single multi-signal narrative. The prompt template gets restructured around a generic "available signals" frame so future widenings (`revenue_motion`, `content_demand`) drop in as additional conditional blocks without restructuring.

This is also the **first multi-collector synthesizer call in the project**. Quality of the cross-signal reasoning is the actual product. The plan ends with a Dale-led quality gate against three domains; the cycle isn't done until the rendered output passes RR's brand-voice and diagnostic-density bar.

---

## Scope

### In scope

- Rename `rrxray/synthesizers/observed_gtm_motion_pricing.py` → `rrxray/synthesizers/observed_gtm_motion.py` (drops the misleading `_pricing` suffix)
- Rename `rrxray/prompts/observed_gtm_motion_pricing.md` → `rrxray/prompts/observed_gtm_motion.md`
- Rename `tests/test_synthesizer_pricing.py` → `tests/test_synthesizer_observed_gtm_motion.py`
- Update import path in `rrxray/pipeline.py` (one line)
- Modify the synthesizer to read both `pricing_packaging` and `tech_stack` collector outputs; pass both into the user-message renderer
- Restructure the prompt template using the generic "available signals" frame: two conditional Jinja blocks today, ready for `revenue_motion` and `content_demand` to drop in tomorrow
- Add 4 new tests covering the multi-collector paths (tech_stack-only, both collectors, both None graceful skip, prompt blocks render conditionally)
- Quality gate: smoke run against `swayable.com`, `sqaservices.com`, `linear.app` with side-by-side comparison vs the old pricing-only output. Plan isn't complete until Dale signs off on the rendered Section A reading like Revenue Reimagined wrote it.

### Out of scope (future cycles)

- New collectors (`revenue_motion`, `content_demand`, `funding_trajectory`, etc.)
- New section synthesizers (Section B `stability_trajectory`, Section C `external_voice_vs_internal`)
- Executive Summary synthesizer
- Schema changes (existing `ObservedGtmMotionNarrative` is sufficient)
- Renderer changes (existing template consumes `data.synthesizers.observed_gtm_motion` regardless of how many collectors fed it)
- LLM provider abstraction / Gemini integration (Phase 3)
- Modes / PDF / Gamma / dashboard renderers (Phase 3)

---

## Decisions Locked During Brainstorming

| Decision | Choice | Rationale |
|---|---|---|
| Prompt template structure | Generic "available signals" frame with conditional Jinja blocks per collector | Scales to 4+ collectors without template restructure; each block carries its own framework guidance the LLM uses for reasoning |
| File rename hygiene | `git mv` now to drop the `_pricing` suffix everywhere | Once and done, no legacy; matches the existing `NAME = "observed_gtm_motion"` constant |
| Synthesizer call shape | One Anthropic call per pipeline invocation, both collectors passed as inputs | Matches Phase 1 pattern; cheaper than per-collector micro-prompts; cross-signal reasoning happens in one Claude turn |
| Graceful skip semantics | Skip synthesis only when ALL collectors absent; run with whatever's available otherwise | Maximizes diagnostic output even under partial collector failure |
| Quality verification | Final plan task: 3-domain smoke + Dale-led prompt iteration until brand voice + diagnostic density pass | Synthesizer prompt is foundational for every future Section widening; worth tuning with eyes on real output |

---

## Architecture

### File layout (changes only)

```
RENAMED:
  rrxray/synthesizers/observed_gtm_motion_pricing.py
    → rrxray/synthesizers/observed_gtm_motion.py
  rrxray/prompts/observed_gtm_motion_pricing.md
    → rrxray/prompts/observed_gtm_motion.md
  tests/test_synthesizer_pricing.py
    → tests/test_synthesizer_observed_gtm_motion.py

MODIFIED:
  rrxray/synthesizers/observed_gtm_motion.py
    body: read both pricing_packaging and tech_stack from ctx.collector_outputs;
    pass both to _render_user_message; preserve existing voice + finding handling
  rrxray/prompts/observed_gtm_motion.md
    structure: generic "available signals" intro; conditional blocks per collector;
    each block carries its own framework guidance for that signal type
  rrxray/pipeline.py
    update import path: from rrxray.synthesizers import observed_gtm_motion (drop _pricing)
  tests/test_synthesizer_observed_gtm_motion.py
    update existing tests for new module path; add 4 new tests for multi-collector paths
```

No new files. No new schemas. No renderer changes.

---

## Components

### Synthesizer (`rrxray/synthesizers/observed_gtm_motion.py`)

```python
"""Section A synthesizer (multi-collector).

Phase 2.1b: reads from pricing_packaging + tech_stack. Generic "available signals"
prompt structure means future widenings (revenue_motion, content_demand, ...)
drop in as additional conditional blocks without restructure.
"""
from __future__ import annotations

import logging
from importlib.resources import files

from jinja2 import Environment
from pydantic import BaseModel, Field

from rrxray.context import SynthesizerContext
from rrxray.schemas._shared import Finding
from rrxray.schemas.data import ObservedGtmMotionNarrative

NAME = "observed_gtm_motion"
log = logging.getLogger(f"rrxray.synthesizers.{NAME}")


class NarrativeResponse(BaseModel):
    narrative_paragraphs: list[str] = Field(description="3-5 factual paragraphs")
    gap_bullets: list[str] = Field(description="3-5 short gap bullets")
    findings: list[Finding] = Field(default=[])
    gaps: list[str] = Field(default=[])
    discovery_questions: list[str] = Field(default=[])


def _load_system_prompt() -> str:
    return files("rrxray.prompts").joinpath("synthesizer_system.md").read_text()


def _render_user_message(domain: str, pricing, tech_stack) -> str:
    template_text = files("rrxray.prompts").joinpath("observed_gtm_motion.md").read_text()
    env = Environment(trim_blocks=True, lstrip_blocks=True)
    return env.from_string(template_text).render(
        domain=domain,
        pricing=pricing,
        tech_stack=tech_stack,
    )


async def synthesize(ctx: SynthesizerContext) -> ObservedGtmMotionNarrative | None:
    pricing = ctx.collector_outputs.pricing_packaging
    tech_stack = ctx.collector_outputs.tech_stack

    # Skip only when ALL collectors absent (both failed / skipped)
    if pricing is None and tech_stack is None:
        log.info(
            "All Section A collectors (pricing_packaging, tech_stack) absent; "
            "skipping observed_gtm_motion synthesis"
        )
        return None

    system_prompt = _load_system_prompt()
    user_message = _render_user_message(ctx.config.domain, pricing, tech_stack)

    response = await ctx.anthropic.complete_with_cached_system(
        system_prompt=system_prompt,
        user_message=user_message,
        model=ctx.config.model,
        response_schema=NarrativeResponse,
    )

    # Voice post-processing on EVERY synthesizer-generated string
    # (matches Phase 1 T15-fix: paragraphs + gap_bullets + findings.text + gaps + discovery_questions)
    paragraphs = [
        ctx.voice.process_synthesizer_text(p, context=f"{NAME} para {i}")
        for i, p in enumerate(response.parsed.narrative_paragraphs)
    ]
    gap_bullets = [
        ctx.voice.process_synthesizer_text(g, context=f"{NAME} gap {i}")
        for i, g in enumerate(response.parsed.gap_bullets)
    ]
    gaps = [
        ctx.voice.process_synthesizer_text(g, context=f"{NAME} gap-label {i}")
        for i, g in enumerate(response.parsed.gaps)
    ]
    discovery_questions = [
        ctx.voice.process_synthesizer_text(q, context=f"{NAME} discovery {i}")
        for i, q in enumerate(response.parsed.discovery_questions)
    ]
    findings = []
    for i, f in enumerate(response.parsed.findings):
        cleaned_text = ctx.voice.process_synthesizer_text(
            f.text, context=f"{NAME} finding {i}"
        )
        findings.append(Finding(text=cleaned_text, source=f.source))

    return ObservedGtmMotionNarrative(
        narrative_paragraphs=paragraphs,
        gap_bullets=gap_bullets,
        findings=findings,
        gaps=gaps,
        discovery_questions=discovery_questions,
        model_used=response.model_used,
        cache_hit=response.cache_hit,
    )
```

### Prompt template (`rrxray/prompts/observed_gtm_motion.md`)

```jinja
## Section A: Observed GTM Motion

You are writing Section A of the GTM X-Ray for **{{ domain }}**. The question is: what is this company's observable GTM motion? Reason from the signals available below. Acknowledge gaps where signals are absent rather than fabricating; honest absence is more diagnostically valuable than padding.

### Signal-by-signal framework guidance

A company's GTM motion can be inferred by reading multiple signals together:

**Pricing & packaging tells you:**
- Public published pricing with tiers + per-seat cadence usually = self-serve / PLG-adjacent, mid-market to SMB
- Contact-us gating with no public prices usually = enterprise-led, sales-driven
- Mixed (some tiers public, top tier "contact us") = hybrid land-and-expand
- Frequent pricing changes = still finding pricing fit
- Tier additions = segment expansion or upmarket
- Tier removals = pruning underperforming segments

**Tech stack tells you:**
- HubSpot only = mid-market sales, marketing-led nurture
- HubSpot + Salesforce signals = upmarket movement, hybrid CRM
- Pendo + Intercom + product-analytics = product-led adoption motion
- Marketo + Demandbase / 6sense = enterprise ABM motion
- No detectable martech = early-stage, privacy-led, server-side tagging, or low GTM maturity (the discovery question disambiguates)
- Live chat without marketing automation = inbound conversations not feeding nurture

**Cross-signal reasoning** is the diagnostic value:
- Pricing gated + Marketo + Demandbase = enterprise ABM motion (consistent)
- Pricing public + Pendo + Intercom = PLG with sales-assist (consistent)
- Pricing gated + HubSpot only = misalignment between intended motion and tooling maturity (diagnostic finding worth surfacing)
- Pricing public + no analytics = unusual; flag in discovery questions

### Available signals for {{ domain }}

{% if pricing %}
**Pricing & Packaging signal**

- Public pricing page found: {{ "yes" if pricing.has_public_pricing else "no" }}
- Contact-us gated: {{ "yes" if pricing.is_contact_us_gated else "no" }}
- Pricing URL: {{ pricing.current_pricing_url or "not found" }}

Current tiers:
{% if pricing.current_tiers %}
{% for t in pricing.current_tiers %}
- {{ t.name }}: {{ t.price }} {{ t.cadence }}{% if t.notes %}. {{ t.notes }}{% endif %}
{% endfor %}
{% else %}
(none extracted)
{% endif %}

Pricing changes observed in the last 18 months:
{% if pricing.detected_changes %}
{% for c in pricing.detected_changes %}
- {{ c.date_observed }}: {{ c.kind }} — `{{ c.before }}` → `{{ c.after }}`
{% endfor %}
{% else %}
(none)
{% endif %}

Historical snapshots: {{ pricing.historical_snapshots | length }} Wayback snapshot(s) recovered.
{% else %}
**Pricing & Packaging signal:** not collected (collector failed or skipped). Note this gap; consider adding pricing-related discovery questions.
{% endif %}

{% if tech_stack %}
**Tech Stack signal**

Detected tools ({{ tech_stack.detected_tools | length }}):
{% if tech_stack.detected_tools %}
{% for tool in tech_stack.detected_tools %}
- {{ tool.category }}: {{ tool.name }} ({{ tool.confidence }} confidence; signature: `{{ tool.signature_id }}`)
{% endfor %}
{% else %}
(none detected)
{% endif %}

Categories observed: {{ tech_stack.categories_observed | join(", ") if tech_stack.categories_observed else "(none)" }}
Categories not detected: {{ tech_stack.categories_absent | join(", ") if tech_stack.categories_absent else "(all 9 categories observed)" }}

Collector findings:
{% if tech_stack.findings %}
{% for f in tech_stack.findings %}
- {{ f.text }}
{% endfor %}
{% else %}
(none)
{% endif %}
{% else %}
**Tech Stack signal:** not collected (collector failed or skipped). Note this gap; consider adding analytics / martech discovery questions.
{% endif %}

### Your task

Write Section A. Reason ACROSS the available signals (not just within each one). Pick out cross-signal patterns that confirm or contradict each other. Be specific: cite which tier, which tool, which date when relevant. State patterns as facts, not opinions ("the current revenue leader has been in seat 11 months" not "leadership might be unstable"). Acknowledge gaps where you can't tell from the data; add those to discovery_questions.

Output 3-5 narrative paragraphs and 3-5 gap_bullets. Each finding cites a source. Each discovery question is one Revenue Reimagined would actually ask in a real conversation.
```

### Pipeline integration (`rrxray/pipeline.py`)

```python
# Before:
from rrxray.synthesizers import observed_gtm_motion_pricing
SYNTHESIZERS = [observed_gtm_motion_pricing]

# After:
from rrxray.synthesizers import observed_gtm_motion
SYNTHESIZERS = [observed_gtm_motion]
```

One-line change.

---

## Data flow

```
SynthesizerContext (collector_outputs, anthropic, voice, anonymizer, config)
   ↓
observed_gtm_motion.synthesize(ctx)
   ↓
read pricing = ctx.collector_outputs.pricing_packaging
read tech_stack = ctx.collector_outputs.tech_stack
   ↓
both None? → return None (graceful skip)
otherwise → continue
   ↓
load system prompt (cached)
render user message with both pricing and tech_stack (Jinja conditional blocks)
   ↓
ctx.anthropic.complete_with_cached_system(...)
   ↓
parse NarrativeResponse
   ↓
voice.process_synthesizer_text on EVERY string
(paragraphs, bullets, findings.text, gaps, discovery_questions)
   ↓
return ObservedGtmMotionNarrative
```

---

## Error handling

- **Both collectors absent** → graceful skip (return None). The pipeline orchestrator records this as a None synthesizer output, NOT a failure. The renderer will show "[Module not available for this domain]" in Section A.
- **Voice violation** during post-processing → propagates as `VoiceViolationError`. The pipeline catches at synthesizer-gather level and records a `ModuleFailure` with `kind="synthesizer"`. Section A renders as `[Module not available for this domain]`. This is unchanged from Phase 1 T15.
- **Anthropic API failure** → propagates as `AnthropicError`. Same fate.
- **Partial collector data** (e.g., pricing has empty tiers, tech_stack has zero detections) → synthesis runs, the prompt's conditional blocks render the empty-data states, the LLM reasons about the absence as itself a signal.

---

## Testing

### Test files

```
tests/test_synthesizer_observed_gtm_motion.py    [renamed from test_synthesizer_pricing.py]
```

### New tests added (4)

- `test_synth_runs_with_tech_stack_only` — pricing is None, tech_stack has detections; synthesis runs, user message contains tech stack block but NOT pricing block
- `test_synth_runs_with_both_collectors` — both collectors present; user message contains both blocks
- `test_synth_returns_none_when_both_collectors_absent` — both None; synthesizer returns None (no Anthropic call)
- `test_user_message_renders_conditional_blocks` — verifies the Jinja template renders only the blocks corresponding to non-None inputs (regression-protects the conditional logic)

### Existing tests updated (10)

The 10 voice-processing tests from Phase 1 T15 + T15-fix continue to apply. Updated to:
- Reference the new module path (`from rrxray.synthesizers import observed_gtm_motion`)
- Pass `tech_stack=None` explicitly where the test only exercises pricing
- Verify the pricing-only path (existing behavior) still works after the prompt template change

---

## Quality gate (terminal task in the implementation plan)

The plan's final task is NOT marked complete until:

1. Smoke run against three domains: **Swayable**, **SQA Services**, **Linear**. Each produces a fresh `report.internal.md` with the new multi-collector Section A.
2. Side-by-side comparison: pull the existing pricing-only Section A output from each domain's prior run (or regenerate against a temporary checkout of the pre-Phase-2.1b synthesizer). Compare same domain, old narrative vs new narrative.
3. Dale reads. Calls out:
   - Phrases that read AI-generated rather than RR-authored
   - Discovery questions that miss the mark
   - Findings that lack specificity
   - Cross-signal reasoning gaps (does Section A actually integrate signals, or just list them?)
   - Voice / brand violations the post-processor missed
4. Iterate the prompt template. Re-smoke. Repeat until quality gate passes.

This task is bounded by quality, not time. The implementation plan documents this and the executing subagent does NOT mark Phase 2.1b complete until Dale has signed off.

---

## Phase 2.1b acceptance criteria

| # | Criterion | Verified by |
|---|---|---|
| 1 | Synthesizer reads from BOTH `pricing_packaging` and `tech_stack` collector outputs | `test_synth_runs_with_both_collectors` |
| 2 | Tech-stack-only path produces a synthesizer call (Pricing collector failure doesn't kill Section A) | `test_synth_runs_with_tech_stack_only` |
| 3 | Both collectors absent → graceful skip (no Anthropic call) | `test_synth_returns_none_when_both_collectors_absent` |
| 4 | Voice post-processing applies to ALL synthesizer-generated text (paragraphs, bullets, findings, gaps, questions) | Existing voice tests pass after rename |
| 5 | File renames committed cleanly via `git mv` | `git log` shows R-status entries |
| 6 | Pipeline import path updated; existing pipeline tests still pass | `tests/test_pipeline_graceful_degradation.py` green |
| 7 | Live smoke against `swayable.com` produces a Section A narrative referencing both pricing AND tech stack signals (where present) | manual review of rendered report |
| 8 | Side-by-side comparison shows multi-collector Section A produces sharper diagnostics than pricing-only equivalent on at least 2 of 3 smoke domains | Dale-led review |
| 9 | Quality gate signed off by Dale | manual review |

---

## Risks and known limitations

- **Prompt iteration may take multiple cycles.** First multi-collector synthesis. If the LLM produces shallow output (e.g., "The pricing is gated. The tech stack has HubSpot. Therefore the motion is..."), the prompt's framework guidance needs sharpening. Build budget for 2-4 iteration cycles in the quality gate.
- **Tech stack data is currently sparse on most domains** because of the Firecrawl `<script>` strip (see Phase 2.1a checkpoint). The DOM-level signatures from 2.1a-fix help but don't fully close the gap. Expect "tech_stack signal: 1-2 detections, mostly low-confidence" on real domains. The synthesizer's framework guidance needs to handle that gracefully (treat sparse detections as a signal of either privacy posture or scrape limitation).
- **Cost per smoke run rises** because the prompt now includes tech_stack data — input tokens grow by ~500-1000 per run. Sonnet 4.6 at cached cost stays roughly $0.013-0.018 per run. Acceptable.
- **Cross-signal reasoning quality is hard to test programmatically.** Acceptance criterion #8 is the only structural check; #7 and #9 rely on Dale's read. This is by design — synthesizer quality is fundamentally a brand-voice judgment, not a unit test.

---

## Out of scope but accommodated by the design

- Phase 2.1c's `revenue_motion` collector adds a third conditional block in the prompt template (≤30 lines of Jinja), no synthesizer code change.
- Phase 2.1d's `content_demand` collector adds a fourth block.
- Phase 3's Gemini integration uses the `--model` flag at runtime; no synthesizer change.
- The renderer template at `templates/report_internal.md.jinja` consumes `data.synthesizers.observed_gtm_motion` regardless of how many collectors fed it; no renderer change needed.

---

## Open questions

None at this time. All material decisions are locked.
