"""Section A pricing-only synthesizer (Phase 1).

Phase 2 replaces this with a multi-collector version (revenue_motion + tech_stack +
pricing_packaging + content_demand). For now, only pricing data flows in.
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
    findings: list[Finding] = Field(
        description="3-5 source-cited specific facts", default=[]
    )
    gaps: list[str] = Field(description="3-5 short gap labels", default=[])
    discovery_questions: list[str] = Field(
        description="3-5 questions to ask in conversation", default=[]
    )


def _load_system_prompt() -> str:
    return files("rrxray.prompts").joinpath("synthesizer_system.md").read_text()


def _render_user_message(domain: str, pricing_data) -> str:
    template_text = (
        files("rrxray.prompts").joinpath("observed_gtm_motion.md").read_text()
    )
    env = Environment(trim_blocks=True, lstrip_blocks=True)
    return env.from_string(template_text).render(domain=domain, data=pricing_data)


async def synthesize(ctx: SynthesizerContext) -> ObservedGtmMotionNarrative | None:
    pricing = ctx.collector_outputs.pricing_packaging
    if pricing is None:
        log.info("pricing_packaging output missing; skipping observed_gtm_motion synthesis")
        return None

    system_prompt = _load_system_prompt()
    user_message = _render_user_message(ctx.config.domain, pricing)

    response = await ctx.anthropic.complete_with_cached_system(
        system_prompt=system_prompt,
        user_message=user_message,
        model=ctx.config.model,
        response_schema=NarrativeResponse,
    )

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
    # Findings have a text field that needs processing; preserve the source citation.
    findings = []
    for i, f in enumerate(response.parsed.findings):
        cleaned_text = ctx.voice.process_synthesizer_text(
            f.text, context=f"{NAME} finding {i}"
        )
        # Re-construct Finding to keep immutability on the source citation
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
