"""observed_stability_trajectory synthesizer tests."""
from __future__ import annotations

import asyncio
from datetime import UTC
from unittest.mock import AsyncMock, MagicMock

from rrxray.schemas._shared import Finding, SourceCitation
from rrxray.schemas.funding_trajectory import FundingRound, FundingTrajectoryData
from rrxray.schemas.leadership_stability import (
    CurrentIncumbent,
    ExecAction,
    ExecChange,
    FounderTenure,
    LeadershipStabilityData,
    NameRegistration,
)
from rrxray.synthesizers.observed_stability_trajectory import (
    NarrativeResponse,
    _build_aggregates,
    synthesize,
)


def _placeholder_source() -> SourceCitation:
    """Internal-scheme SourceCitation for tests; mirrors collector pattern.

    Plan tests used `source=None`, but Finding.source is required (T10/T11
    SourceCitation schema mismatch). Collector uses `rrxray://` URL scheme
    for non-URL-anchored findings, so tests do the same.
    """
    from datetime import datetime
    return SourceCitation(
        url="rrxray://test/observed_stability_trajectory",
        timestamp=datetime(2026, 5, 9, tzinfo=UTC),
    )


def _full_data():
    from datetime import date, timedelta
    today = date.today()
    return LeadershipStabilityData(
        exec_changes=[
            ExecChange(
                name="Jane Doe", role_canonical="cro", role_raw="CRO",
                action=ExecAction.HIRE,
                occurred_at=today - timedelta(days=120),
                press_url="https://example.com/p/1",
                press_title="x",
            ),
        ],
        current_incumbents=[
            CurrentIncumbent(name="Jane Doe", role_canonical="cro", role_raw="CRO", confidence="high"),
            CurrentIncumbent(name="Founder Person", role_canonical="ceo", role_raw="CEO", confidence="high"),
            CurrentIncumbent(name="Founder Person", role_canonical="founder", role_raw="Founder", confidence="high"),
        ],
        founder_tenure=FounderTenure(inferred_year=2018, source="about_page"),
        name_registrations=[
            NameRegistration(name="Jane Doe", role_descriptor="Acme's CRO", whitelist=True),
            NameRegistration(name="Founder Person", role_descriptor="Acme's CEO", whitelist=False),
        ],
        findings=[
            Finding(text="CRO is in transition; current incumbent in seat ~4 months.",
                    source=_placeholder_source()),
        ],
    )


def test_build_aggregates_excludes_names():
    """Aggregates contain zero registered names; only counts and tenures."""
    aggs = _build_aggregates(_full_data())

    s = aggs.model_dump_json()
    assert "Jane Doe" not in s
    assert "Founder Person" not in s


def test_build_aggregates_seat_changes():
    aggs = _build_aggregates(_full_data())
    assert aggs.seat_changes == {"cro": 1}


def test_build_aggregates_recent_changes():
    aggs = _build_aggregates(_full_data())
    assert len(aggs.recent_changes) == 1
    assert aggs.recent_changes[0]["role"] == "cro"


def test_build_aggregates_founder_present_in_ceo_seat():
    aggs = _build_aggregates(_full_data())
    assert aggs.founder_present_in_ceo_seat is True
    assert aggs.founder_tenure_years is not None


def test_build_aggregates_collector_findings_strings():
    aggs = _build_aggregates(_full_data())
    assert aggs.collector_findings == ["CRO is in transition; current incumbent in seat ~4 months."]


def test_aggregates_tenure_ignores_departures():
    """Tenure for a current incumbent must be inferred from the latest
    hire/promotion in that seat, not from a departure (which reflects the
    prior incumbent leaving)."""
    from datetime import date, timedelta

    today = date.today()
    data = LeadershipStabilityData(
        exec_changes=[
            # Departure 90 days ago — should be ignored
            ExecChange(
                name="Old CRO", role_canonical="cro", role_raw="CRO",
                action=ExecAction.DEPARTURE,
                occurred_at=today - timedelta(days=90),
                press_url="x", press_title="y",
            ),
            # Hire 30 days ago — this is the tenure anchor
            ExecChange(
                name="New CRO", role_canonical="cro", role_raw="CRO",
                action=ExecAction.HIRE,
                occurred_at=today - timedelta(days=30),
                press_url="x", press_title="y",
            ),
        ],
        current_incumbents=[
            CurrentIncumbent(name="New CRO", role_canonical="cro", role_raw="CRO", confidence="high"),
        ],
        founder_tenure=FounderTenure(),
    )

    aggs = _build_aggregates(data)
    assert aggs.current_incumbents_by_role["cro"]["tenure_months"] == 1


def test_synth_skips_when_collector_absent():
    """leadership_stability is None → synthesize returns None."""
    from rrxray.config import Config
    from rrxray.context import SynthesizerContext
    from rrxray.schemas.data import CollectorOutputs

    ctx = SynthesizerContext(
        collector_outputs=CollectorOutputs(),
        anthropic=MagicMock(),
        voice=MagicMock(),
        anonymizer=MagicMock(),
        config=Config(domain="example.com"),
    )
    result = asyncio.run(synthesize(ctx))
    assert result is None


def test_synth_runs_with_full_data():
    """Full data → calls anthropic, returns narrative."""
    from rrxray.config import Config
    from rrxray.context import SynthesizerContext
    from rrxray.schemas._shared import Finding
    from rrxray.schemas.data import CollectorOutputs

    fake_anthropic = MagicMock()
    fake_anthropic.complete_with_cached_system = AsyncMock(return_value=MagicMock(
        parsed=NarrativeResponse(
            narrative_paragraphs=["The CRO change places motion in active transition.", "Founder still in CEO seat for ~8 years."],
            findings=[Finding(text="CRO recently hired.", source=_placeholder_source())],
            gaps=["Tenure of new CRO unknown."],
            discovery_questions=["What does the new CRO see as the priority motion shift?"],
        ),
        model_used="claude-sonnet-4-6",
        cache_hit=False,
    ))

    fake_voice = MagicMock()
    fake_voice.sanitize_llm_output = lambda text, context: text
    fake_voice.process_synthesizer_text = lambda text, context: text

    ctx = SynthesizerContext(
        collector_outputs=CollectorOutputs(leadership_stability=_full_data()),
        anthropic=fake_anthropic,
        voice=fake_voice,
        anonymizer=MagicMock(),
        config=Config(domain="example.com"),
    )
    result = asyncio.run(synthesize(ctx))

    assert result is not None
    assert len(result.narrative_paragraphs) == 2
    assert len(result.findings) == 1
    fake_anthropic.complete_with_cached_system.assert_called_once()


def test_synth_voice_processing_applied():
    """Em-dashes and forbidden words substituted by voice processor."""
    from rrxray.config import Config
    from rrxray.context import SynthesizerContext
    from rrxray.schemas.data import CollectorOutputs

    fake_anthropic = MagicMock()
    fake_anthropic.complete_with_cached_system = AsyncMock(return_value=MagicMock(
        parsed=NarrativeResponse(
            narrative_paragraphs=["Leverage the CRO's momentum — motion is shifting."],
            findings=[],
            gaps=[],
            discovery_questions=[],
        ),
        model_used="claude-sonnet-4-6",
        cache_hit=False,
    ))

    # Real-ish voice processor
    fake_voice = MagicMock()
    fake_voice.sanitize_llm_output = lambda text, context: text.replace("—", ", ").replace("Leverage", "Use")
    fake_voice.process_synthesizer_text = lambda text, context: text

    ctx = SynthesizerContext(
        collector_outputs=CollectorOutputs(leadership_stability=_full_data()),
        anthropic=fake_anthropic,
        voice=fake_voice,
        anonymizer=MagicMock(),
        config=Config(domain="example.com"),
    )
    result = asyncio.run(synthesize(ctx))

    assert "—" not in result.narrative_paragraphs[0]
    assert "Leverage" not in result.narrative_paragraphs[0]


def test_aggregates_compute_tenure_confirmed_count():
    from rrxray.schemas.leadership_stability import (
        CurrentIncumbent,
        LeadershipStabilityData,
    )
    from rrxray.synthesizers.observed_stability_trajectory import _build_aggregates
    data = LeadershipStabilityData(
        current_incumbents=[
            CurrentIncumbent(name="A", role_canonical="cro", role_raw="CRO", tenure_months=14),
            CurrentIncumbent(name="B", role_canonical="cmo", role_raw="CMO", tenure_months=None),
            CurrentIncumbent(name="C", role_canonical="ceo", role_raw="CEO", tenure_months=84),
        ],
    )
    aggs = _build_aggregates(data)
    assert aggs.tenure_confirmed_count == 2  # A and C
    assert aggs.tenure_confirmed_total == 3


def test_aggregates_compute_external_hire_count():
    from rrxray.schemas.leadership_stability import (
        CurrentIncumbent,
        LeadershipStabilityData,
    )
    from rrxray.synthesizers.observed_stability_trajectory import _build_aggregates
    data = LeadershipStabilityData(
        current_incumbents=[
            CurrentIncumbent(name="A", role_canonical="cro", role_raw="CRO",
                             prior_employer="Salesforce"),
            CurrentIncumbent(name="B", role_canonical="cmo", role_raw="CMO",
                             prior_employer="HubSpot"),
            CurrentIncumbent(name="C", role_canonical="ceo", role_raw="CEO",
                             prior_employer=None),
        ],
    )
    aggs = _build_aggregates(data)
    # A and B have prior_employer set and ≠ current; C has None
    assert aggs.external_hire_count == 2


def test_aggregates_compute_internal_promotion_count():
    from rrxray.schemas.leadership_stability import (
        CurrentIncumbent,
        LeadershipStabilityData,
    )
    from rrxray.synthesizers.observed_stability_trajectory import _build_aggregates
    # Internal promotion = prior_role set AND prior_employer matches current company name
    # We pass company_name via the data context — for this test we rely on the
    # _build_aggregates signature; if it doesn't take company_name, the heuristic
    # "prior_employer is None AND prior_role is set" identifies a likely-internal move.
    # Implementer: pick the cleaner heuristic in the actual code; this test asserts
    # the count is reported, not the exact rule.
    data = LeadershipStabilityData(
        current_incumbents=[
            CurrentIncumbent(name="A", role_canonical="cro", role_raw="CRO",
                             prior_employer="Acme", prior_role="VP of Sales"),
            CurrentIncumbent(name="B", role_canonical="cmo", role_raw="CMO",
                             prior_employer="HubSpot", prior_role="VP Marketing"),
        ],
    )
    aggs = _build_aggregates(data)
    assert aggs.internal_promotion_count + aggs.external_hire_count == 2


def test_aggregates_compute_prior_employer_signals_per_role():
    from rrxray.schemas.leadership_stability import (
        CurrentIncumbent,
        LeadershipStabilityData,
    )
    from rrxray.synthesizers.observed_stability_trajectory import _build_aggregates
    data = LeadershipStabilityData(
        current_incumbents=[
            CurrentIncumbent(name="A", role_canonical="cro", role_raw="CRO",
                             prior_employer="Salesforce"),
            CurrentIncumbent(name="B", role_canonical="cmo", role_raw="CMO",
                             prior_employer=None),
        ],
    )
    aggs = _build_aggregates(data)
    assert aggs.prior_employer_signals.get("cro") == "Salesforce"
    assert aggs.prior_employer_signals.get("cmo") is None


def test_aggregates_handle_missing_enrichment_data_gracefully():
    """When no incumbents have enrichment fields, counts are 0 / signals empty."""
    from rrxray.schemas.leadership_stability import (
        CurrentIncumbent,
        LeadershipStabilityData,
    )
    from rrxray.synthesizers.observed_stability_trajectory import _build_aggregates
    data = LeadershipStabilityData(
        current_incumbents=[
            CurrentIncumbent(name="A", role_canonical="cro", role_raw="CRO"),
        ],
    )
    aggs = _build_aggregates(data)
    assert aggs.tenure_confirmed_count == 0
    assert aggs.tenure_confirmed_total == 1
    assert aggs.external_hire_count == 0
    assert aggs.internal_promotion_count == 0
    assert aggs.prior_employer_signals.get("cro") is None


def test_synth_renders_enrichment_metadata_when_partial():
    """Prompt should reflect aborted_reason='cost_cap' when set."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    from rrxray.config import Config
    from rrxray.context import SynthesizerContext
    from rrxray.schemas.data import CollectorOutputs
    from rrxray.schemas.leadership_stability import (
        LeadershipEnrichmentMetadata,
        LeadershipStabilityData,
    )
    from rrxray.synthesizers.observed_stability_trajectory import (
        NarrativeResponse,
        synthesize,
    )

    fake_anthropic = MagicMock()
    fake_anthropic.complete_with_cached_system = AsyncMock(return_value=MagicMock(
        parsed=NarrativeResponse(narrative_paragraphs=["test"]),
        model_used="claude-opus-4-7", cache_hit=False,
    ))
    fake_voice = MagicMock()
    fake_voice.sanitize_llm_output = lambda text, context: text
    fake_voice.process_synthesizer_text = lambda text, context: text

    data = LeadershipStabilityData(
        enrichment_metadata=LeadershipEnrichmentMetadata(
            spend_dollars=5.0, aborted_reason="cost_cap",
        ),
    )
    ctx = SynthesizerContext(
        collector_outputs=CollectorOutputs(leadership_stability=data),
        anthropic=fake_anthropic, voice=fake_voice,
        anonymizer=MagicMock(), config=Config(domain="example.com"),
    )
    asyncio.run(synthesize(ctx))

    # Capture the user_message sent to the LLM
    call_args = fake_anthropic.complete_with_cached_system.await_args
    user_message = call_args.kwargs.get("user_message", "")
    assert "cost_cap" in user_message or "partial" in user_message.lower()


# --- Phase 2.4a: StabilityAggregates funding fields ---

def test_stability_aggregates_funding_fields_default():
    """StabilityAggregates has funding fields with safe defaults."""
    aggs = _build_aggregates(_full_data(), funding=None)
    assert aggs.funding_recovered is False
    assert aggs.last_round_series is None
    assert aggs.last_round_months_ago is None
    assert aggs.last_round_amount_usd_millions is None
    assert aggs.total_raised_usd_millions is None
    assert aggs.implied_stage == "signal_not_recovered"
    assert aggs.recent_rounds == []


def test_build_aggregates_with_funding_populates_fields():
    from datetime import date
    ft = FundingTrajectoryData(
        rounds=[
            FundingRound(
                series="series_b", amount_usd_millions=25.0,
                announced_date=date(2024, 3, 15),
                lead_investor="Sequoia",
                source_url="https://crunchbase.com/x",
                source_type="crunchbase",
            ),
            FundingRound(
                series="series_a", amount_usd_millions=8.0,
                announced_date=date(2022, 6, 1),
                source_url="https://crunchbase.com/y",
                source_type="crunchbase",
            ),
        ],
        total_raised_usd_millions=33.0,
        last_round_months_ago=14,
        implied_stage="early_growth",
        crunchbase_recovered=True,
    )
    aggs = _build_aggregates(_full_data(), funding=ft)
    assert aggs.funding_recovered is True
    assert aggs.last_round_series == "series_b"
    assert aggs.last_round_months_ago == 14
    assert aggs.last_round_amount_usd_millions == 25.0
    assert aggs.total_raised_usd_millions == 33.0
    assert aggs.implied_stage == "early_growth"
    assert len(aggs.recent_rounds) == 2
    assert aggs.recent_rounds[0]["series"] == "series_b"


def test_prompt_renders_funding_block_when_present():
    from datetime import date

    from rrxray.synthesizers.observed_stability_trajectory import _render_user_message
    ft = FundingTrajectoryData(
        rounds=[
            FundingRound(series="series_b", amount_usd_millions=25.0, announced_date=date(2024, 3, 15),
                         source_url="https://x", source_type="crunchbase"),
        ],
        last_round_months_ago=14, implied_stage="early_growth", crunchbase_recovered=True,
        total_raised_usd_millions=25.0,
    )
    aggs = _build_aggregates(_full_data(), funding=ft)
    msg = _render_user_message("acme.com", aggs)
    assert "Funding trajectory signal" in msg
    assert "series_b" in msg
    assert "14" in msg


def test_prompt_renders_not_recovered_when_funding_absent():
    from rrxray.synthesizers.observed_stability_trajectory import _render_user_message
    aggs = _build_aggregates(_full_data(), funding=None)
    msg = _render_user_message("acme.com", aggs)
    assert "Funding trajectory signal" in msg
    assert "not recovered" in msg.lower()


def test_build_aggregates_funding_recovered_false_when_no_rounds():
    ft = FundingTrajectoryData(
        rounds=[], implied_stage="signal_not_recovered", crunchbase_recovered=False
    )
    aggs = _build_aggregates(_full_data(), funding=ft)
    assert aggs.funding_recovered is False
    assert aggs.implied_stage == "signal_not_recovered"
