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
