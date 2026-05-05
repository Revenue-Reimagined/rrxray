"""Markdown renderer: pure XrayData -> str function with anonymize + voice filters."""
from __future__ import annotations

from datetime import UTC, datetime

from rrxray.rendering.markdown import render_internal
from rrxray.schemas.data import (
    CollectorOutputs,
    InputParams,
    ObservedGtmMotionNarrative,
    RunMetadata,
    SourceCitation,
    SynthesizerOutputs,
    XrayData,
)
from rrxray.schemas.pricing_packaging import PricingPackagingData, PricingTier
from rrxray.voice.anonymizer import Anonymizer
from rrxray.voice.rr_voice import VoicePostProcessor


def make_data(
    *,
    pricing: PricingPackagingData | None = None,
    narrative: ObservedGtmMotionNarrative | None = None,
) -> XrayData:
    return XrayData(
        domain="example.com",
        company_name="Example Inc.",
        run_metadata=RunMetadata(
            timestamp=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
            tool_version="0.1.0",
            modes_built=["internal"],
            model_used="claude-sonnet-4-6",
        ),
        inputs=InputParams(domain="example.com", mode="internal", model="claude-sonnet-4-6"),
        collectors=CollectorOutputs(pricing_packaging=pricing),
        synthesizers=SynthesizerOutputs(observed_gtm_motion=narrative),
    )


def test_full_skeleton_present():
    data = make_data()
    out = render_internal(data, Anonymizer(), VoicePostProcessor())
    for header in [
        "# GTM X-Ray™:",
        "## 1. Executive Summary",
        "## 2. Section A: Observed GTM Motion",
        "## 3. Section B: Stability and Trajectory Signals",
        "## 4. Section C: External Voice vs. Internal Voice",
        "## 5. Module Detail Appendix",
        "## 6. Discovery Questions",
        "## 7. Sources & Methodology",
    ]:
        assert header in out


def test_unavailable_module_renders_placeholder_string():
    data = make_data()
    out = render_internal(data, Anonymizer(), VoicePostProcessor())
    assert "[Module not available for this domain]" in out


def test_section_a_renders_narrative_when_present():
    narrative = ObservedGtmMotionNarrative(
        narrative_paragraphs=["The motion appears self-serve.", "Pricing is published."],
        gap_bullets=["Pricing has been static for 18 months"],
        findings=[], gaps=[], discovery_questions=["Have you tested price increases?"],
        model_used="claude-sonnet-4-6", cache_hit=False,
    )
    data = make_data(narrative=narrative)
    out = render_internal(data, Anonymizer(), VoicePostProcessor())
    assert "The motion appears self-serve." in out
    assert "→ Pricing has been static for 18 months" in out


def test_pricing_detail_renders_tiers():
    pricing = PricingPackagingData(
        has_public_pricing=True, is_contact_us_gated=False,
        current_pricing_url="https://example.com/pricing",
        current_tiers=[
            PricingTier(name="Starter", price="$0", cadence="month", notes=""),
            PricingTier(name="Pro", price="$50", cadence="per seat per month", notes=""),
        ],
    )
    data = make_data(pricing=pricing)
    out = render_internal(data, Anonymizer(), VoicePostProcessor())
    assert "| Starter |" in out
    assert "| Pro |" in out
    assert "$50" in out


def test_voice_collector_filter_substitutes():
    pricing = PricingPackagingData(
        has_public_pricing=True, is_contact_us_gated=False,
        current_pricing_url="https://example.com/pricing",
        current_tiers=[PricingTier(name="Pro", price="$50", cadence="month",
                                    notes="We leverage data to set prices.")],
    )
    data = make_data(pricing=pricing)
    voice = VoicePostProcessor()
    out = render_internal(data, Anonymizer(), voice)
    # "leverage" must not appear in rendered content; it is allowed in the Voice Adjustments
    # audit section where it documents the substitution (per plan T22 AC #4)
    body = out.split("### Voice Adjustments")[0]
    assert "leverage" not in body
    assert "use" in out  # substituted


def test_anonymize_filter_replaces_registered_name():
    narrative = ObservedGtmMotionNarrative(
        narrative_paragraphs=["Sarah Chen leads sales."],
        gap_bullets=["No SDR support"],
        findings=[], gaps=[], discovery_questions=[],
        model_used="x", cache_hit=False,
    )
    data = make_data(narrative=narrative)
    a = Anonymizer()
    a.register_individual("Sarah Chen", "the current VP of Sales")
    out = render_internal(data, a, VoicePostProcessor())
    assert "Sarah Chen" not in out
    assert "the current VP of Sales leads sales." in out


def test_sources_section_lists_all():
    pricing = PricingPackagingData(
        has_public_pricing=True, is_contact_us_gated=False,
        current_pricing_url="https://example.com/pricing",
    )
    data = make_data(pricing=pricing)
    data.sources = [SourceCitation(
        url="https://example.com/pricing",
        timestamp=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
        evidence_path="pricing_packaging/current.md",
    )]
    out = render_internal(data, Anonymizer(), VoicePostProcessor())
    assert "[https://example.com/pricing](https://example.com/pricing)" in out
    assert "evidence/pricing_packaging/current.md" in out


def test_voice_adjustments_section_present_when_substitutions_happened():
    pricing = PricingPackagingData(
        has_public_pricing=True, is_contact_us_gated=False,
        current_pricing_url="https://example.com/pricing",
        current_tiers=[PricingTier(
            name="Pro", price="$50", cadence="month",
            notes="We leverage data.",
        )],
    )
    data = make_data(pricing=pricing)
    voice = VoicePostProcessor()
    out = render_internal(data, Anonymizer(), voice)
    assert "### Voice Adjustments" in out
    assert "forbidden_word" in out


def test_known_limitations_section_present():
    data = make_data()
    out = render_internal(data, Anonymizer(), VoicePostProcessor())
    assert "### Known Limitations" in out
    assert "LinkedIn" in out
