"""Section B synthesizer: observed_stability_trajectory.

Reads from leadership_stability collector. Pre-aggregates the data into a
name-free StabilityAggregates structure before rendering the prompt template.
Names never enter the synthesizer prompt or LLM output.

Future Phase 2 sub-phases (funding_trajectory, customer_concentration) widen
this synthesizer the same way Phase 2.1c widened observed_gtm_motion: add
conditional blocks; the synthesizer body unchanged.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from importlib.resources import files

from jinja2 import Environment
from pydantic import BaseModel, Field

from rrxray.collectors._leadership_stability_catalog import RECENT_THRESHOLD_DAYS
from rrxray.context import SynthesizerContext
from rrxray.schemas._shared import Finding
from rrxray.schemas.data import ObservedStabilityTrajectoryNarrative
from rrxray.schemas.leadership_stability import ExecAction, LeadershipStabilityData

NAME = "observed_stability_trajectory"
log = logging.getLogger(f"rrxray.synthesizers.{NAME}")


class StabilityAggregates(BaseModel):
    """Name-free pre-aggregation passed to the prompt template."""
    seat_changes: dict[str, int]
    recent_changes: list[dict]
    current_incumbents_by_role: dict[str, dict]
    founder_present_in_ceo_seat: bool
    founder_tenure_years: int | None
    seats_with_no_change_18mo: list[str]
    collector_findings: list[str]


class NarrativeResponse(BaseModel):
    """Structured response from the synthesizer."""
    narrative_paragraphs: list[str] = Field(description="2-4 paragraphs committing to a stability/trajectory hypothesis")
    findings: list[Finding] = Field(default=[])
    gaps: list[str] = Field(default=[])
    discovery_questions: list[str] = Field(default=[])


def _load_system_prompt() -> str:
    return files("rrxray.prompts").joinpath("synthesizer_system.md").read_text()


def _build_aggregates(data: LeadershipStabilityData) -> StabilityAggregates:
    """Pre-aggregate LeadershipStabilityData into a name-free structure."""
    today = datetime.now(UTC).date()

    # Seat-change counts
    seat_changes: dict[str, int] = {}
    for c in data.exec_changes:
        seat_changes[c.role_canonical] = seat_changes.get(c.role_canonical, 0) + 1

    # Recent changes (≤RECENT_THRESHOLD_DAYS)
    recent_changes = []
    for c in data.exec_changes:
        if c.occurred_at is None:
            continue
        days_ago = (today - c.occurred_at).days
        if days_ago <= RECENT_THRESHOLD_DAYS:
            recent_changes.append({
                "role": c.role_canonical,
                "action": c.action.value if hasattr(c.action, "value") else str(c.action),
                "occurred_at_months_ago": max(1, days_ago // 30),
            })

    # Current incumbents — high confidence only; tenure inferred from latest matching change
    incumbents_by_role: dict[str, dict] = {}
    for inc in data.current_incumbents:
        if inc.confidence != "high":
            continue
        # tenure: if there's a recent hire/promotion in this role, use its
        # months_ago. Departures don't reflect the current incumbent's tenure
        # so they're filtered out.
        tenure_months = None
        latest_change = max(
            (c for c in data.exec_changes
             if c.role_canonical == inc.role_canonical
             and c.occurred_at is not None
             and c.action in {ExecAction.HIRE, ExecAction.PROMOTION}),
            key=lambda c: c.occurred_at,
            default=None,
        )
        if latest_change is not None and latest_change.occurred_at is not None:
            tenure_months = max(1, (today - latest_change.occurred_at).days // 30)
        incumbents_by_role[inc.role_canonical] = {
            "tenure_months": tenure_months,
            "confidence": inc.confidence,
        }

    # Founder presence in CEO seat
    founder_names = {i.name for i in data.current_incumbents if i.role_canonical == "founder"}
    ceo_names = {i.name for i in data.current_incumbents if i.role_canonical == "ceo"}
    founder_in_ceo = bool(founder_names & ceo_names)

    founder_tenure_years: int | None = None
    if data.founder_tenure and data.founder_tenure.inferred_year:
        founder_tenure_years = today.year - data.founder_tenure.inferred_year

    # Seats with no change in 18 months — derived from seat_changes vs all known roles
    all_roles = ["ceo", "cro", "vp_sales", "vp_revenue", "cmo", "vp_marketing", "founder"]
    seats_with_no_change = [r for r in all_roles if r not in seat_changes]

    return StabilityAggregates(
        seat_changes=seat_changes,
        recent_changes=recent_changes,
        current_incumbents_by_role=incumbents_by_role,
        founder_present_in_ceo_seat=founder_in_ceo,
        founder_tenure_years=founder_tenure_years,
        seats_with_no_change_18mo=seats_with_no_change,
        collector_findings=[f.text for f in data.findings],
    )


def _render_user_message(domain: str, aggregates: StabilityAggregates) -> str:
    template_text = files("rrxray.prompts").joinpath("observed_stability_trajectory.md").read_text()
    env = Environment(trim_blocks=True, lstrip_blocks=True)
    return env.from_string(template_text).render(
        domain=domain,
        aggregates=aggregates,
    )


async def synthesize(ctx: SynthesizerContext) -> ObservedStabilityTrajectoryNarrative | None:
    leadership = ctx.collector_outputs.leadership_stability
    if leadership is None:
        log.info("leadership_stability collector absent; skipping observed_stability_trajectory synthesis")
        return None

    aggregates = _build_aggregates(leadership)
    system_prompt = _load_system_prompt()
    user_message = _render_user_message(ctx.config.domain, aggregates)

    response = await ctx.anthropic.complete_with_cached_system(
        system_prompt=system_prompt,
        user_message=user_message,
        model=ctx.config.model,
        response_schema=NarrativeResponse,
    )

    def _voice(text: str, ctx_label: str) -> str:
        clean = ctx.voice.sanitize_llm_output(text, context=ctx_label)
        return ctx.voice.process_synthesizer_text(clean, context=ctx_label)

    paragraphs = [_voice(p, f"{NAME} para {i}") for i, p in enumerate(response.parsed.narrative_paragraphs)]
    gaps = [_voice(g, f"{NAME} gap {i}") for i, g in enumerate(response.parsed.gaps)]
    discovery_questions = [_voice(q, f"{NAME} discovery {i}") for i, q in enumerate(response.parsed.discovery_questions)]
    findings = [
        Finding(text=_voice(f.text, f"{NAME} finding {i}"), source=f.source)
        for i, f in enumerate(response.parsed.findings)
    ]

    return ObservedStabilityTrajectoryNarrative(
        narrative_paragraphs=paragraphs,
        findings=findings,
        gaps=gaps,
        discovery_questions=discovery_questions,
        model_used=response.model_used,
        cache_hit=response.cache_hit,
    )
