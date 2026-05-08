# rrxray Phase 2.1b Section A Multi-Collector Synthesizer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the Section A synthesizer to read from BOTH `pricing_packaging` and `tech_stack` collector outputs. Restructure the prompt template using a generic "available signals" frame so future widenings drop in cleanly. Drop the misleading `_pricing` suffix from the synthesizer module / prompt template / test file.

**Architecture:** Same module-pattern synthesizer as Phase 1, now reading two collectors instead of one. One Anthropic call per pipeline invocation with both collector outputs passed into the user-message renderer. Conditional Jinja blocks render only the signals that exist (graceful skip when a collector is absent). Voice post-processing on every synthesizer-generated string (matches Phase 1 T15-fix pattern). Quality gate as terminal task: 3-domain smoke + Dale-led prompt iteration.

**Tech Stack:** Python 3.12+, pydantic v2, jinja2, anthropic SDK (existing). No new dependencies.

**Spec reference:** [docs/superpowers/specs/2026-05-07-rrxray-phase-2.1b-section-a-multi-collector-design.md](../specs/2026-05-07-rrxray-phase-2.1b-section-a-multi-collector-design.md)

---

## File Structure

`[T#]` indicates the task that touches each file.

```
RENAMES (T1):
  rrxray/synthesizers/observed_gtm_motion_pricing.py
    → rrxray/synthesizers/observed_gtm_motion.py
  rrxray/prompts/observed_gtm_motion_pricing.md
    → rrxray/prompts/observed_gtm_motion.md
  tests/test_synthesizer_pricing.py
    → tests/test_synthesizer_observed_gtm_motion.py

MODIFICATIONS:
  rrxray/synthesizers/observed_gtm_motion.py        [T1: prompt-load path; T3: read tech_stack]
  rrxray/prompts/observed_gtm_motion.md             [T3: generic "available signals" structure]
  rrxray/pipeline.py                                [T1: import path update]
  tests/test_synthesizer_observed_gtm_motion.py     [T1: import path; T2: 4 new failing tests]
```

No new files. No new schemas. No renderer changes.

---

## Task overview

5 tasks total. Tasks 1-4 are mechanical TDD; Task 5 is the quality gate (Dale-driven, bounded by sign-off rather than time).

- **T1: Renames + pipeline import update** (mechanical; no behavior change; existing tests stay green)
- **T2: Add failing multi-collector tests** (4 new tests fail because synthesizer doesn't read tech_stack yet)
- **T3: Update synthesizer body + prompt template** (tests now pass; synthesizer reads tech_stack; prompt has generic-signals structure)
- **T4: Verify pipeline integration end-to-end** (existing pipeline graceful-degradation tests still pass; one new test for both-collectors-present pipeline path)
- **T5: Quality gate** (3-domain smoke + side-by-side compare + Dale-led prompt iteration; not complete until Dale signs off)

---

## Task 1: Renames + pipeline import update

**Files:**
- Rename (via `git mv`): `rrxray/synthesizers/observed_gtm_motion_pricing.py` → `rrxray/synthesizers/observed_gtm_motion.py`
- Rename (via `git mv`): `rrxray/prompts/observed_gtm_motion_pricing.md` → `rrxray/prompts/observed_gtm_motion.md`
- Rename (via `git mv`): `tests/test_synthesizer_pricing.py` → `tests/test_synthesizer_observed_gtm_motion.py`
- Modify: `rrxray/synthesizers/observed_gtm_motion.py` (one-line change: prompt-load path)
- Modify: `rrxray/pipeline.py` (import + SYNTHESIZERS list)
- Modify: `tests/test_synthesizer_observed_gtm_motion.py` (test import path)

This task does NOT change synthesizer behavior. Goal is clean filenames with everything still working.

- [ ] **Step 1: Rename the synthesizer module**

```bash
cd /Users/dalezwizinski/Documents/Apps/rrxray
git mv rrxray/synthesizers/observed_gtm_motion_pricing.py rrxray/synthesizers/observed_gtm_motion.py
```

- [ ] **Step 2: Rename the prompt template**

```bash
git mv rrxray/prompts/observed_gtm_motion_pricing.md rrxray/prompts/observed_gtm_motion.md
```

- [ ] **Step 3: Rename the test file**

```bash
git mv tests/test_synthesizer_pricing.py tests/test_synthesizer_observed_gtm_motion.py
```

- [ ] **Step 4: Update the prompt-load path in the renamed synthesizer**

In `rrxray/synthesizers/observed_gtm_motion.py`, find the `_render_user_message` function. It currently loads the prompt template by the old filename. Update:

```python
def _render_user_message(domain: str, pricing_data) -> str:
    template_text = files("rrxray.prompts").joinpath("observed_gtm_motion_pricing.md").read_text()
    ...
```

becomes:

```python
def _render_user_message(domain: str, pricing_data) -> str:
    template_text = files("rrxray.prompts").joinpath("observed_gtm_motion.md").read_text()
    ...
```

(One literal change: drop the `_pricing` suffix in the joinpath call.)

- [ ] **Step 5: Update the pipeline import**

In `rrxray/pipeline.py`, find:

```python
from rrxray.synthesizers import observed_gtm_motion_pricing
```

Change to:

```python
from rrxray.synthesizers import observed_gtm_motion
```

And find:

```python
SYNTHESIZERS = [observed_gtm_motion_pricing]
```

Change to:

```python
SYNTHESIZERS = [observed_gtm_motion]
```

- [ ] **Step 6: Update test imports**

In `tests/test_synthesizer_observed_gtm_motion.py`, find the existing imports:

```python
from rrxray.synthesizers import observed_gtm_motion_pricing
```

Change to:

```python
from rrxray.synthesizers import observed_gtm_motion
```

Find and replace ALL occurrences of `observed_gtm_motion_pricing` in the test file with `observed_gtm_motion` (this includes function calls like `observed_gtm_motion_pricing.synthesize(ctx)` → `observed_gtm_motion.synthesize(ctx)`).

- [ ] **Step 7: Run the full test suite**

```bash
uv run pytest -v 2>&1 | tail -10
```

Expected: 177 passed (same count as before T1; renames are behavior-preserving).

- [ ] **Step 8: Run ruff**

```bash
uv run ruff check rrxray/ tests/
```

Expected: All checks passed.

- [ ] **Step 9: Commit**

```bash
git status
# verify the three R-prefixed lines (renames) and three modified lines (synthesizer prompt-load path, pipeline import, test imports)

git commit -m "Rename observed_gtm_motion_pricing → observed_gtm_motion (drop _pricing suffix)

Phase 2.1b prep: the synthesizer now reads from multiple collectors,
making the _pricing suffix misleading. Use git mv for clean history;
update prompt-load path, pipeline import, and test imports. No
behavior change in this commit."
```

`git log --diff-filter=R --name-status -1` should show three R100 (rename, 100% similarity) entries.

---

## Task 2: Add failing multi-collector tests

**Files:**
- Modify: `tests/test_synthesizer_observed_gtm_motion.py` (append 4 new tests)

These tests fail because the current synthesizer ignores `tech_stack` entirely. T3 makes them pass.

- [ ] **Step 1: Update the `make_synth_ctx` helper to accept tech_stack**

The existing helper at the top of `tests/test_synthesizer_observed_gtm_motion.py` looks roughly like:

```python
def make_synth_ctx(pricing_data: PricingPackagingData | None, anthropic_response):
    fake_anthropic = MagicMock()
    fake_anthropic.complete_with_cached_system = AsyncMock(return_value=anthropic_response)

    config = MagicMock(domain="example.com", model="claude-sonnet-4-6")
    return SynthesizerContext(
        collector_outputs=CollectorOutputs(pricing_packaging=pricing_data),
        anthropic=fake_anthropic,
        voice=VoicePostProcessor(),
        anonymizer=Anonymizer(),
        config=config,
    )
```

Widen the signature to accept `tech_stack`:

```python
def make_synth_ctx(
    pricing_data: PricingPackagingData | None = None,
    anthropic_response=None,
    tech_stack: "TechStackData | None" = None,
):
    fake_anthropic = MagicMock()
    fake_anthropic.complete_with_cached_system = AsyncMock(return_value=anthropic_response)

    config = MagicMock(domain="example.com", model="claude-sonnet-4-6")
    return SynthesizerContext(
        collector_outputs=CollectorOutputs(
            pricing_packaging=pricing_data,
            tech_stack=tech_stack,
        ),
        anthropic=fake_anthropic,
        voice=VoicePostProcessor(),
        anonymizer=Anonymizer(),
        config=config,
    )
```

Add the import at the top of the test file: `from rrxray.schemas.tech_stack import DetectedTool, TechStackData`.

(Note: existing test calls like `make_synth_ctx(pricing_data=p, anthropic_response=r)` continue to work because new args have defaults.)

- [ ] **Step 2: Append the 4 new tests**

Append to `tests/test_synthesizer_observed_gtm_motion.py`:

```python
def test_synth_runs_with_tech_stack_only():
    """When pricing is None but tech_stack has data, synthesis runs and uses tech_stack."""
    tech = TechStackData(
        detected_tools=[DetectedTool(
            name="HubSpot", category="marketing_automation", confidence="high",
            signature_id="hubspot:strict_js", matched_text="js.hs-scripts.com/x.js",
        )],
        categories_observed=["marketing_automation"],
        categories_absent=["analytics", "tag_manager", "chat", "product_analytics",
                           "crm", "cdp", "ab_testing", "attribution"],
    )
    ctx = make_synth_ctx(
        pricing_data=None,
        tech_stack=tech,
        anthropic_response=make_anthropic_response(
            ["Tech-stack-only narrative."],
            ["No pricing data observed; relying on tech-stack signals."],
        ),
    )
    result = asyncio.run(observed_gtm_motion.synthesize(ctx))
    assert result is not None

    # Verify Anthropic was called with a user message containing tech_stack data
    ctx.anthropic.complete_with_cached_system.assert_called_once()
    user_msg = ctx.anthropic.complete_with_cached_system.call_args.kwargs["user_message"]
    assert "Tech Stack signal" in user_msg
    assert "HubSpot" in user_msg
    # Pricing block should fall back to "not collected"
    assert "Pricing & Packaging signal" in user_msg
    assert "not collected" in user_msg


def test_synth_runs_with_both_collectors():
    """When both collectors have data, the user message contains both signal blocks."""
    pricing = PricingPackagingData(
        has_public_pricing=True, is_contact_us_gated=False,
        current_pricing_url="https://example.com/pricing",
        current_tiers=[PricingTier(name="Pro", price="$50", cadence="month")],
    )
    tech = TechStackData(
        detected_tools=[DetectedTool(
            name="HubSpot", category="marketing_automation", confidence="high",
            signature_id="hubspot:strict_js", matched_text="js.hs-scripts.com/x.js",
        )],
        categories_observed=["marketing_automation"],
        categories_absent=["analytics", "tag_manager", "chat", "product_analytics",
                           "crm", "cdp", "ab_testing", "attribution"],
    )
    ctx = make_synth_ctx(
        pricing_data=pricing,
        tech_stack=tech,
        anthropic_response=make_anthropic_response(
            ["Multi-signal narrative."],
            ["Pricing public; HubSpot suggests marketing-led nurture."],
        ),
    )
    result = asyncio.run(observed_gtm_motion.synthesize(ctx))
    assert result is not None

    user_msg = ctx.anthropic.complete_with_cached_system.call_args.kwargs["user_message"]
    assert "Pricing & Packaging signal" in user_msg
    assert "https://example.com/pricing" in user_msg
    assert "Pro" in user_msg
    assert "Tech Stack signal" in user_msg
    assert "HubSpot" in user_msg


def test_synth_returns_none_when_both_collectors_absent():
    """When BOTH pricing and tech_stack are None, synthesis is skipped entirely (no Anthropic call)."""
    ctx = make_synth_ctx(
        pricing_data=None,
        tech_stack=None,
        anthropic_response=make_anthropic_response(["x"], ["y"]),
    )
    result = asyncio.run(observed_gtm_motion.synthesize(ctx))
    assert result is None
    ctx.anthropic.complete_with_cached_system.assert_not_called()


def test_user_message_renders_conditional_blocks():
    """Pricing-only path: user message has the pricing block populated; tech_stack falls back to 'not collected'."""
    pricing = PricingPackagingData(
        has_public_pricing=True, is_contact_us_gated=False,
        current_pricing_url="https://example.com/pricing",
    )
    user_msg = observed_gtm_motion._render_user_message(
        domain="example.com",
        pricing=pricing,
        tech_stack=None,
    )
    assert "Pricing & Packaging signal" in user_msg
    assert "https://example.com/pricing" in user_msg
    assert "Tech Stack signal" in user_msg
    assert "not collected" in user_msg  # the tech_stack absence fallback fires
```

Note: the existing `_render_user_message` function takes `(domain, pricing_data)`. T3 will widen it to `(domain, pricing, tech_stack)`. The test in Step 2 above calls it with the new signature; that's intentional (the test is supposed to fail in this task and pass after T3).

- [ ] **Step 3: Run tests to verify they fail**

```bash
uv run pytest tests/test_synthesizer_observed_gtm_motion.py -v
```

Expected: 4 new tests fail. Specifically:
- `test_synth_runs_with_tech_stack_only` fails because the current synthesizer returns None when `pricing_data is None` (it doesn't fall through to tech_stack)
- `test_synth_runs_with_both_collectors` fails because the user message doesn't contain "Tech Stack signal" (current prompt template has no such block)
- `test_synth_returns_none_when_both_collectors_absent` may or may not fail depending on existing behavior — verify it explicitly
- `test_user_message_renders_conditional_blocks` fails with TypeError because `_render_user_message` doesn't accept a `tech_stack` kwarg

- [ ] **Step 4: Commit (failing tests; T3 will turn them green)**

```bash
git add tests/test_synthesizer_observed_gtm_motion.py
git commit -m "Add failing multi-collector tests for Section A synthesizer

Four tests covering:
- tech_stack-only path (pricing absent)
- both collectors present
- both absent (graceful skip; no Anthropic call)
- conditional rendering of prompt blocks

Tests fail intentionally; T3 updates the synthesizer body and prompt
template to satisfy them."
```

---

## Task 3: Update synthesizer body + prompt template

**Files:**
- Modify: `rrxray/synthesizers/observed_gtm_motion.py` (full body update)
- Modify: `rrxray/prompts/observed_gtm_motion.md` (full content replacement)

This task makes the failing tests from T2 pass. Body change + prompt template change must land together because the tests verify the rendered user message structure.

- [ ] **Step 1: Replace `rrxray/synthesizers/observed_gtm_motion.py` with the multi-collector version**

Full content (paste exactly):

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
    """Structured response from the synthesizer."""

    narrative_paragraphs: list[str] = Field(description="3-5 factual paragraphs")
    gap_bullets: list[str] = Field(description="3-5 short bullets naming observed gaps")
    findings: list[Finding] = Field(default=[])
    gaps: list[str] = Field(default=[])
    discovery_questions: list[str] = Field(default=[])


def _load_system_prompt() -> str:
    return files("rrxray.prompts").joinpath("synthesizer_system.md").read_text()


def _render_user_message(domain: str, pricing, tech_stack) -> str:
    """Render the Section A user message.

    Both `pricing` and `tech_stack` are optional. The Jinja template renders
    a conditional block per signal: full data when present, "not collected"
    fallback when None.
    """
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

    # Voice post-processing on every synthesizer-generated string
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

- [ ] **Step 2: Replace `rrxray/prompts/observed_gtm_motion.md` with the multi-collector template**

Full content (paste exactly):

```markdown
## Section A: Observed GTM Motion

You are writing Section A of the GTM X-Ray for **{{ domain }}**. The question is: what is this company's observable GTM motion? Reason from the signals available below. Acknowledge gaps where signals are absent rather than fabricating; honest absence is more diagnostically valuable than padding.

### Signal-by-signal framework guidance

A company's GTM motion can be inferred by reading multiple signals together:

**Pricing & packaging tells you:**

- Public published pricing with tiers and per-seat cadence usually = self-serve / PLG-adjacent, mid-market to SMB
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

- [ ] **Step 3: Run the synthesizer test suite**

```bash
uv run pytest tests/test_synthesizer_observed_gtm_motion.py -v
```

Expected: ALL tests pass (existing voice / cache / NAME tests + the 4 new multi-collector tests).

If a previously-existing test fails because it called `_render_user_message(domain, pricing_data)` (the old 2-arg signature), update those calls to pass `tech_stack=None` explicitly: `_render_user_message(domain="example.com", pricing=pricing_data, tech_stack=None)`.

- [ ] **Step 4: Run the full test suite**

```bash
uv run pytest -v 2>&1 | tail -10
```

Expected: 181 passed (177 from prior phase + 4 new). One skip (the e2e smoke test).

- [ ] **Step 5: Run ruff**

```bash
uv run ruff check rrxray/ tests/
```

Expected: All checks passed. If any imports are flagged for ordering, run `uv run ruff check --fix rrxray/ tests/` and verify tests still pass.

- [ ] **Step 6: Commit**

```bash
git add rrxray/synthesizers/observed_gtm_motion.py rrxray/prompts/observed_gtm_motion.md tests/test_synthesizer_observed_gtm_motion.py
git commit -m "Wire Section A synthesizer to read pricing + tech_stack

Synthesizer body reads both collector outputs; skips synthesis only when
ALL collectors are absent (graceful partial-failure handling). Prompt
template restructured around a generic 'available signals' frame: each
collector gets a conditional block, future widenings drop in as
additional blocks without restructure. Voice post-processing applies
to every synthesizer-generated string (matches Phase 1 T15-fix pattern).

Section A narrative now reasons across pricing AND tech stack signals.
The 4 multi-collector tests from T2 are now green; full suite passes."
```

---

## Task 4: Verify pipeline integration

**Files:**
- Modify: `tests/test_pipeline_graceful_degradation.py` (one new test)

The pipeline already handles graceful degradation per Phase 1's T19. T4 adds an explicit test for the multi-collector synthesis path.

- [ ] **Step 1: Append a failing test to `tests/test_pipeline_graceful_degradation.py`**

```python
def test_pipeline_runs_section_a_with_both_collectors(tmp_path, monkeypatch):
    """When both pricing_packaging and tech_stack succeed, Section A synthesizer reads both."""
    from rrxray.schemas.tech_stack import DetectedTool, TechStackData

    config = fake_config(tmp_path)

    fake_pricing = MagicMock()
    fake_pricing.NAME = "pricing_packaging"

    async def pricing_collect(ctx):
        from rrxray.schemas.pricing_packaging import PricingPackagingData
        return PricingPackagingData(
            has_public_pricing=True, is_contact_us_gated=False,
            current_pricing_url="https://example.com/pricing",
        )

    fake_pricing.collect = pricing_collect

    fake_tech_stack = MagicMock()
    fake_tech_stack.NAME = "tech_stack"

    async def tech_collect(ctx):
        return TechStackData(
            detected_tools=[DetectedTool(
                name="HubSpot", category="marketing_automation", confidence="high",
                signature_id="hubspot:strict_js", matched_text="x",
            )],
            categories_observed=["marketing_automation"],
            categories_absent=["analytics", "tag_manager", "chat", "product_analytics",
                               "crm", "cdp", "ab_testing", "attribution"],
        )

    fake_tech_stack.collect = tech_collect

    fake_synth = MagicMock()
    fake_synth.NAME = "observed_gtm_motion"

    captured_ctx = {}

    async def synth_capture(ctx):
        # Verify the synth context has both collectors populated
        captured_ctx["pricing"] = ctx.collector_outputs.pricing_packaging
        captured_ctx["tech_stack"] = ctx.collector_outputs.tech_stack
        return None  # graceful skip; we only care about the context shape

    fake_synth.synthesize = synth_capture

    monkeypatch.setattr(pipeline, "COLLECTORS", [fake_pricing, fake_tech_stack])
    monkeypatch.setattr(pipeline, "SYNTHESIZERS", [fake_synth])
    monkeypatch.setattr(pipeline, "build_collector_context", lambda c: MagicMock())
    monkeypatch.setattr(
        pipeline, "build_synthesizer_context",
        lambda c, o, v, a: MagicMock(collector_outputs=o, voice=v, anonymizer=a, config=c),
    )

    asyncio.run(pipeline.run_pipeline(config))
    assert captured_ctx["pricing"] is not None
    assert captured_ctx["tech_stack"] is not None
    assert captured_ctx["tech_stack"].detected_tools[0].name == "HubSpot"
```

- [ ] **Step 2: Run the test to verify it passes (it should already)**

```bash
uv run pytest tests/test_pipeline_graceful_degradation.py -v
```

Expected: All tests pass including the new one. The pipeline already correctly threads both collectors into the synthesizer context; this test is regression protection.

- [ ] **Step 3: Run the full suite**

```bash
uv run pytest -v 2>&1 | tail -10
```

Expected: 182 passed, 1 skipped.

- [ ] **Step 4: Run ruff**

```bash
uv run ruff check rrxray/ tests/
```

Expected: All checks passed.

- [ ] **Step 5: Commit**

```bash
git add tests/test_pipeline_graceful_degradation.py
git commit -m "Pipeline regression test: both Section A collectors threaded into synth ctx

Locks in the contract that the pipeline orchestrator passes both
pricing_packaging and tech_stack outputs into the synthesizer's
SynthesizerContext.collector_outputs. Phase 2.1c+ collectors will
each add a similar regression test."
```

---

## Task 5: Quality gate

**Files:**
- Possibly: `rrxray/prompts/observed_gtm_motion.md` (iterations based on Dale review)

This task is bounded by Dale's sign-off, not by time or step count. The implementer subagent runs the smoke comparison and presents output for human review; iteration cycles continue until quality passes.

- [ ] **Step 1: Live smoke run against three domains**

```bash
cd /Users/dalezwizinski/Documents/Apps/rrxray
unset ANTHROPIC_API_KEY FIRECRAWL_API_KEY  # belt-and-suspenders against shell shadowing

# Force fresh runs (no cached synthesizer responses) so we see the new prompt's output
uv run rrxray run --domain swayable.com --no-cache 2>&1 | tail -3
uv run rrxray run --domain sqaservices.com --no-cache 2>&1 | tail -3
uv run rrxray run --domain linear.app --no-cache 2>&1 | tail -3
```

Expected: each run produces `xray-{domain}-{date}/data.json` and `report.internal.md`. No exceptions; graceful-degradation handles archive.org or Firecrawl flakiness.

- [ ] **Step 2: Extract and present each Section A**

For each domain, extract the Section A narrative from the rendered report:

```bash
for d in swayable-com sqaservices-com linear-app; do
  echo "=== $d Section A ==="
  awk '/## 2\. Section A/,/^---$/' /Users/dalezwizinski/Documents/Apps/rrxray/xray-$d-*/report.internal.md
  echo ""
done
```

Present the three Section A outputs to Dale.

- [ ] **Step 3: Side-by-side comparison vs prior pricing-only narrative**

If prior runs exist with the pricing-only synthesizer (e.g., the Phase 1 / Phase 2.1a Swayable and SQA runs are already in `xray-{domain}-20260507/`), pull those Section A narratives too. Show old vs new for each domain.

If only the new runs exist (because the cache was busted), present just the new narratives and note the comparison must be inferred against memory.

- [ ] **Step 4: Dale-led quality review**

Dale reads each Section A and calls out:

- Phrasings that read AI-generated rather than RR-authored
- Discovery questions that miss the mark or feel boilerplate
- Findings that lack specificity (e.g., "the company has a marketing automation tool" is too vague)
- Cross-signal reasoning gaps (does the narrative integrate signals, or just list them?)
- Any voice / brand violations the post-processor missed
- Any places where the LLM hallucinated data not present in the input

- [ ] **Step 5: Iterate the prompt based on Dale's feedback**

If quality issues surface:

1. Identify which prompt section needs sharpening (framework guidance, signal blocks, "your task" instruction, all of the above)
2. Modify `rrxray/prompts/observed_gtm_motion.md`
3. Re-run the smoke (`uv run rrxray run --domain X --no-cache`)
4. Present the new Section A output
5. Repeat until Dale signs off

The implementer subagent should:
- NOT mark Phase 2.1b complete on its own
- Present each iteration cycle's output and explicitly ask Dale "does this pass?" before continuing
- Stop iterating only when Dale says "approved" or equivalent

- [ ] **Step 6: Commit any prompt-template iterations**

After each prompt edit (Step 5):

```bash
git add rrxray/prompts/observed_gtm_motion.md
git commit -m "Tune Section A prompt: <one-line description of what changed>

<2-3 lines describing what Dale's review surfaced and how the
prompt change addresses it>"
```

Multiple iterations = multiple commits. Each commit is small enough that Dale can review the prompt diff.

- [ ] **Step 7: Final test run (post-quality-gate)**

```bash
uv run pytest -v 2>&1 | tail -5
uv run ruff check rrxray/ tests/
```

Expected: 182 passed, 1 skipped, ruff clean.

- [ ] **Step 8: Phase 2.1b checkpoint**

Per `CLAUDE.md` rule, write `docs/checkpoints/2026-05-07-phase-2.1b-section-a-multi-collector-checkpoint.md` capturing:

- Final commit SHA
- Final test count
- Quality-gate iteration count and what changed
- Side-by-side comparison summary (multi-collector Section A vs pricing-only)
- Linear smoke-run output highlights (if Linear had detectable tech stack, was it integrated?)
- What's queued next (likely Phase 2.1c: revenue_motion collector)

Use `docs/checkpoints/TEMPLATE.md` as the structure. Commit the checkpoint:

```bash
git add docs/checkpoints/2026-05-07-phase-2.1b-section-a-multi-collector-checkpoint.md
git commit -m "Add Phase 2.1b Section A multi-collector checkpoint"
```

---

## Self-Review

Run after the plan is complete to catch placeholders, contradictions, and gaps.

### Spec coverage check

| Spec section | Plan task |
|---|---|
| Rename three files via `git mv` | T1 |
| Update pipeline import path | T1 |
| Synthesizer reads both collectors | T3 |
| Generic "available signals" prompt frame with conditional blocks | T3 |
| Voice post-processing on every synthesizer string | T3 (preserved from Phase 1 T15-fix) |
| Skip synthesis only when ALL collectors absent | T2 (test) + T3 (implementation) |
| 4 new tests covering multi-collector paths | T2 |
| Pipeline integration regression test | T4 |
| Quality gate: 3-domain smoke + Dale-led iteration | T5 |
| Phase 2.1b checkpoint | T5 step 8 |

### Acceptance criteria coverage

| AC | Plan task |
|---|---|
| #1 Synthesizer reads both collectors | T3 (`test_synth_runs_with_both_collectors`) |
| #2 Tech-stack-only path produces synthesis | T3 (`test_synth_runs_with_tech_stack_only`) |
| #3 Both absent → graceful skip | T3 (`test_synth_returns_none_when_both_collectors_absent`) |
| #4 Voice post-processing on all strings | Preserved from Phase 1; existing tests carry forward |
| #5 Renames committed via `git mv` | T1 |
| #6 Pipeline import updated | T1 |
| #7 Live Swayable smoke produces multi-signal Section A | T5 |
| #8 Side-by-side shows sharper diagnostics on 2/3 domains | T5 |
| #9 Quality gate signed off by Dale | T5 |

### Type / signature consistency check

- `_render_user_message(domain: str, pricing, tech_stack) -> str`: defined T3, called by `synthesize` (T3) and by tests (T2)
- `synthesize(ctx: SynthesizerContext) -> ObservedGtmMotionNarrative | None`: defined T3, called by pipeline (T1)
- `make_synth_ctx(pricing_data, anthropic_response, tech_stack=None)`: widened T2; existing tests use defaults
- Pipeline import: `from rrxray.synthesizers import observed_gtm_motion` (T1), then `SYNTHESIZERS = [observed_gtm_motion]` (T1)
- Test file path: `tests/test_synthesizer_observed_gtm_motion.py` (T1)
- Prompt file path: `rrxray/prompts/observed_gtm_motion.md` (T1)

### Placeholder scan

Searched for: TBD, TODO, "implement later", "fill in", "add appropriate", "similar to". None found in the plan body.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-07-rrxray-phase-2.1b-section-a-multi-collector.md`. Two execution options:

**1. Subagent-Driven (recommended)** — fresh subagent per task, two-stage review (spec compliance + code quality) between tasks. Best for this plan because Tasks 1-4 are mechanical and Task 5 (quality gate) needs Dale's eyes anyway.

**2. Inline Execution** — `superpowers:executing-plans` with batch checkpoints. Best if you want to see every diff in real time before each commit.

Which approach?
