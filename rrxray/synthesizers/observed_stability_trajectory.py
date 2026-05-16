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
    seat_change_ages_months: dict[str, int | None]  # last change months ago, or None if undatable
    recent_changes: list[dict]
    current_incumbents_by_role: dict[str, dict]
    founder_present_in_ceo_seat: bool
    founder_tenure_years: int | None
    seats_with_no_change_18mo: list[str]
    collector_findings: list[str]
    # Phase 2.2-deep additions
    tenure_confirmed_count: int = 0
    tenure_confirmed_total: int = 0
    external_hire_count: int = 0
    internal_promotion_count: int = 0
    prior_employer_signals: dict[str, str | None] = Field(default_factory=dict)
    enrichment_aborted_reason: str = "disabled"
    enrichment_spend_dollars: float = 0.0
    # Phase 2.4a additions
    funding_recovered: bool = False
    last_round_series: str | None = None
    last_round_months_ago: int | None = None
    last_round_amount_usd_millions: float | None = None
    total_raised_usd_millions: float | None = None
    implied_stage: str = "signal_not_recovered"
    recent_rounds: list[dict] = Field(default_factory=list)


class NarrativeResponse(BaseModel):
    """Structured response from the synthesizer."""
    narrative_paragraphs: list[str] = Field(description="2-4 paragraphs committing to a stability/trajectory hypothesis")
    findings: list[Finding] = Field(default=[])
    gaps: list[str] = Field(default=[])
    discovery_questions: list[str] = Field(default=[])


def _load_system_prompt() -> str:
    return files("rrxray.prompts").joinpath("synthesizer_system.md").read_text()


def _build_aggregates(data: LeadershipStabilityData, funding=None) -> StabilityAggregates:
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
            "tenure_months": inc.tenure_months if inc.tenure_months is not None else tenure_months,
            "confidence": inc.confidence,
            "years_at_company": inc.years_at_company,
            "prior_employer": inc.prior_employer,
            "prior_role": inc.prior_role,
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

    # For each seat that has a change, compute "months ago" of the latest change.
    # Prefer the explicit press date when available; fall back to current
    # incumbent's tenure_months when there's exactly one change in that seat
    # (the change is, by definition, the one that produced the incumbent).
    seat_change_ages: dict[str, int | None] = {}
    for role in seat_changes:
        latest_dated = max(
            (c for c in data.exec_changes
             if c.role_canonical == role and c.occurred_at is not None),
            key=lambda c: c.occurred_at,
            default=None,
        )
        if latest_dated is not None and latest_dated.occurred_at is not None:
            seat_change_ages[role] = max(1, (today - latest_dated.occurred_at).days // 30)
        elif (
            seat_changes[role] == 1
            and role in incumbents_by_role
            and incumbents_by_role[role].get("tenure_months") is not None
        ):
            seat_change_ages[role] = incumbents_by_role[role]["tenure_months"]
        else:
            seat_change_ages[role] = None

    # Phase 2.2-deep: tenure confirmation counts (high-confidence incumbents only)
    high_conf = [i for i in data.current_incumbents if i.confidence == "high"]
    tenure_confirmed_count = sum(1 for i in high_conf if i.tenure_months is not None)
    tenure_confirmed_total = len(high_conf)

    # Phase 2.2-deep: external hire vs internal promotion counts + prior_employer signals
    # Heuristic (per plan):
    # - external hire: prior_employer is set (and non-empty) → came from outside
    # - internal promotion: prior_role is set AND prior_employer is None → moved up within
    # Internal-promotion debias: if both fire, decrement external (the plan documents
    # this as the de-bias step so internal+external never double-counts a person).
    external_hire_count = 0
    internal_promotion_count = 0
    prior_employer_signals: dict[str, str | None] = {}
    for inc in high_conf:
        prior_employer_signals[inc.role_canonical] = inc.prior_employer
        if inc.prior_employer is not None:
            external_hire_count += 1
    for inc in high_conf:
        if inc.prior_role is not None and inc.prior_employer is None:
            internal_promotion_count += 1
            external_hire_count = max(0, external_hire_count - 1)

    # Phase 2.2-deep: enrichment metadata
    enrichment_aborted_reason = data.enrichment_metadata.aborted_reason
    enrichment_spend_dollars = data.enrichment_metadata.spend_dollars

    # Phase 2.4a: funding trajectory fields
    funding_recovered = False
    last_round_series = None
    last_round_months_ago_val = None
    last_round_amount_usd_millions = None
    total_raised_usd_millions = None
    implied_stage = "signal_not_recovered"
    recent_rounds_list: list[dict] = []

    if funding is not None:
        funding_recovered = funding.crunchbase_recovered or len(funding.rounds) > 0
        implied_stage = funding.implied_stage
        total_raised_usd_millions = funding.total_raised_usd_millions
        last_round_months_ago_val = funding.last_round_months_ago
        if funding.rounds:
            latest = funding.rounds[0]
            last_round_series = latest.series
            last_round_amount_usd_millions = latest.amount_usd_millions
            for r in funding.rounds[:5]:
                recent_rounds_list.append({
                    "series": r.series,
                    "announced_date": r.announced_date.isoformat() if r.announced_date else None,
                })

    return StabilityAggregates(
        seat_changes=seat_changes,
        seat_change_ages_months=seat_change_ages,
        recent_changes=recent_changes,
        current_incumbents_by_role=incumbents_by_role,
        founder_present_in_ceo_seat=founder_in_ceo,
        founder_tenure_years=founder_tenure_years,
        seats_with_no_change_18mo=seats_with_no_change,
        collector_findings=[f.text for f in data.findings],
        tenure_confirmed_count=tenure_confirmed_count,
        tenure_confirmed_total=tenure_confirmed_total,
        external_hire_count=external_hire_count,
        internal_promotion_count=internal_promotion_count,
        prior_employer_signals=prior_employer_signals,
        enrichment_aborted_reason=enrichment_aborted_reason,
        enrichment_spend_dollars=enrichment_spend_dollars,
        # Phase 2.4a fields
        funding_recovered=funding_recovered,
        last_round_series=last_round_series,
        last_round_months_ago=last_round_months_ago_val,
        last_round_amount_usd_millions=last_round_amount_usd_millions,
        total_raised_usd_millions=total_raised_usd_millions,
        implied_stage=implied_stage,
        recent_rounds=recent_rounds_list,
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

    funding = ctx.collector_outputs.funding_trajectory
    aggregates = _build_aggregates(leadership, funding=funding)
    system_prompt = _load_system_prompt()
    user_message = _render_user_message(ctx.config.domain, aggregates)

    response = await ctx.anthropic.complete_with_cached_system(
        system_prompt=system_prompt,
        user_message=user_message,
        # Section B is voice-critical AND requires strict instruction-following on
        # data-anchored timeframes (Sonnet 4.6 was reverting to rounded "9-18 month"
        # framing even with explicit "use the precise N months" instruction). Per
        # CLAUDE.md model matrix, narrative-quality judgment work goes to Opus.
        model="claude-opus-4-7",
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
