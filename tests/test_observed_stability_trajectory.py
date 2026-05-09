"""observed_stability_trajectory synthesizer tests."""
from __future__ import annotations

import asyncio
from datetime import UTC
from unittest.mock import AsyncMock, MagicMock

from rrxray.schemas._shared import Finding, SourceCitation
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
