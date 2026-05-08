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


def _read_evidence_text(ctx: SynthesizerContext, relative_path: str, max_chars: int) -> str:
    """Read raw text from evidence; truncate to max_chars; empty string on missing/error."""
    try:
        from pathlib import Path

        evidence_dir = (
            ctx.config.evidence_dir
            if hasattr(ctx.config, "evidence_dir")
            else Path("evidence")
        )
        full_path = evidence_dir / relative_path
        if not full_path.exists():
            return ""
        text = full_path.read_text(encoding="utf-8", errors="ignore")
        return text[:max_chars]
    except Exception as e:
        log.warning("Failed to read evidence at %s: %s", relative_path, e)
        return ""


def _render_user_message(
    domain: str,
    pricing,
    tech_stack,
    revenue_motion=None,
    raw_pricing_text: str = "",
    raw_homepage_text: str = "",
) -> str:
    """Render the Section A user message.

    All three Section A collector outputs are optional. The Jinja template
    renders a conditional block per signal: full data when present, "not
    collected" fallback when None.
    """
    template_text = files("rrxray.prompts").joinpath("observed_gtm_motion.md").read_text()
    env = Environment(trim_blocks=True, lstrip_blocks=True)
    return env.from_string(template_text).render(
        domain=domain,
        pricing=pricing,
        tech_stack=tech_stack,
        revenue_motion=revenue_motion,
        raw_pricing_text=raw_pricing_text,
        raw_homepage_text=raw_homepage_text,
    )


async def synthesize(ctx: SynthesizerContext) -> ObservedGtmMotionNarrative | None:
    pricing = ctx.collector_outputs.pricing_packaging
    tech_stack = ctx.collector_outputs.tech_stack
    revenue_motion = ctx.collector_outputs.revenue_motion

    # Skip only when ALL Section A collectors absent
    if pricing is None and tech_stack is None and revenue_motion is None:
        log.info("All Section A collectors absent; skipping observed_gtm_motion synthesis")
        return None

    # Read raw page excerpts from evidence (truncated to keep prompt size sane)
    raw_pricing_text = (
        _read_evidence_text(ctx, "pricing_packaging/current.md", max_chars=3000)
        if pricing
        else ""
    )
    raw_homepage_text = (
        _read_evidence_text(ctx, "tech_stack/homepage.html", max_chars=3000)
        if tech_stack
        else ""
    )

    system_prompt = _load_system_prompt()
    user_message = _render_user_message(
        ctx.config.domain,
        pricing,
        tech_stack,
        revenue_motion=revenue_motion,
        raw_pricing_text=raw_pricing_text,
        raw_homepage_text=raw_homepage_text,
    )

    response = await ctx.anthropic.complete_with_cached_system(
        system_prompt=system_prompt,
        user_message=user_message,
        model=ctx.config.model,
        response_schema=NarrativeResponse,
    )

    # Voice post-processing on every synthesizer-generated string.
    # sanitize_llm_output runs first to substitute LLM-emitted voice
    # violations the prompt can't fully suppress (em-dashes, occasional
    # forbidden words like "leverage" / "synergies"). process_synthesizer_text
    # then runs as a defense-in-depth check; any violation that survives
    # sanitization (shouldn't happen given the substitution table covers all
    # forbidden words) still raises rather than silently shipping.
    def _voice(text: str, ctx_label: str) -> str:
        clean = ctx.voice.sanitize_llm_output(text, context=ctx_label)
        return ctx.voice.process_synthesizer_text(clean, context=ctx_label)

    paragraphs = [
        _voice(p, f"{NAME} para {i}")
        for i, p in enumerate(response.parsed.narrative_paragraphs)
    ]
    gap_bullets = [
        _voice(g, f"{NAME} gap {i}")
        for i, g in enumerate(response.parsed.gap_bullets)
    ]
    gaps = [
        _voice(g, f"{NAME} gap-label {i}")
        for i, g in enumerate(response.parsed.gaps)
    ]
    discovery_questions = [
        _voice(q, f"{NAME} discovery {i}")
        for i, q in enumerate(response.parsed.discovery_questions)
    ]
    findings = []
    for i, f in enumerate(response.parsed.findings):
        cleaned_text = _voice(f.text, f"{NAME} finding {i}")
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
