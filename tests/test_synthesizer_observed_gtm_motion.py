"""Section A pricing-only synthesizer."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from rrxray.context import SynthesizerContext
from rrxray.schemas.data import CollectorOutputs
from rrxray.schemas.pricing_packaging import PricingPackagingData, PricingTier
from rrxray.synthesizers import observed_gtm_motion
from rrxray.voice.anonymizer import Anonymizer
from rrxray.voice.rr_voice import VoicePostProcessor


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


def make_anthropic_response(paragraphs, bullets, findings=None, gaps=None, questions=None):
    from rrxray.services.anthropic_client import AnthropicResponse
    from rrxray.synthesizers.observed_gtm_motion import NarrativeResponse

    parsed = NarrativeResponse(
        narrative_paragraphs=paragraphs,
        gap_bullets=bullets,
        findings=findings or [],
        gaps=gaps or [],
        discovery_questions=questions or [],
    )
    return AnthropicResponse(
        parsed=parsed,
        cache_hit=False,
        input_tokens=500,
        output_tokens=200,
        cache_creation_input_tokens=4000,
        cache_read_input_tokens=0,
        model_used="claude-sonnet-4-6",
    )


def test_synth_name_constant():
    assert observed_gtm_motion.NAME == "observed_gtm_motion"


def test_synth_returns_none_when_pricing_data_missing():
    ctx = make_synth_ctx(None, make_anthropic_response(["x"], ["y"]))
    result = asyncio.run(observed_gtm_motion.synthesize(ctx))
    assert result is None


def test_synth_calls_anthropic_with_cached_system():
    pricing = PricingPackagingData(
        has_public_pricing=True,
        is_contact_us_gated=False,
        current_pricing_url="https://example.com/pricing",
        current_tiers=[PricingTier(name="Pro", price="$50", cadence="month")],
    )
    ctx = make_synth_ctx(
        pricing,
        make_anthropic_response(
            ["The motion appears self-serve."],
            ["Pricing is published but unchanged for 18 months"],
        ),
    )
    asyncio.run(observed_gtm_motion.synthesize(ctx))
    ctx.anthropic.complete_with_cached_system.assert_called_once()
    kwargs = ctx.anthropic.complete_with_cached_system.call_args.kwargs
    assert "Verbatim Quarantine" in kwargs["system_prompt"]
    assert "example.com" in kwargs["user_message"]
    assert "Pro" in kwargs["user_message"]


def test_synth_runs_voice_post_processor_on_paragraphs():
    pricing = PricingPackagingData(
        has_public_pricing=True,
        is_contact_us_gated=False,
        current_pricing_url="https://example.com/pricing",
    )
    # Clean paragraph passes through unchanged
    ctx = make_synth_ctx(
        pricing,
        make_anthropic_response(
            ["This is fine."],
            ["clean bullet"],
        ),
    )
    result = asyncio.run(observed_gtm_motion.synthesize(ctx))
    assert result is not None
    assert result.narrative_paragraphs == ["This is fine."]


def test_synth_raises_when_anthropic_returns_voice_violation():
    pricing = PricingPackagingData(
        has_public_pricing=True,
        is_contact_us_gated=False,
        current_pricing_url="https://example.com/pricing",
    )
    from rrxray.voice.rr_voice import VoiceViolationError

    ctx = make_synth_ctx(
        pricing,
        make_anthropic_response(
            ["We leverage the pricing data."],  # forbidden word; should raise
            ["clean bullet"],
        ),
    )
    with pytest.raises(VoiceViolationError):
        asyncio.run(observed_gtm_motion.synthesize(ctx))


def test_synth_records_cache_hit():
    pricing = PricingPackagingData(
        has_public_pricing=True,
        is_contact_us_gated=False,
        current_pricing_url="https://example.com/pricing",
    )
    from rrxray.services.anthropic_client import AnthropicResponse
    from rrxray.synthesizers.observed_gtm_motion import NarrativeResponse

    parsed = NarrativeResponse(
        narrative_paragraphs=["x"],
        gap_bullets=["y"],
        findings=[],
        gaps=[],
        discovery_questions=[],
    )
    response = AnthropicResponse(
        parsed=parsed,
        cache_hit=True,
        input_tokens=500,
        output_tokens=200,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=4000,
        model_used="claude-sonnet-4-6",
    )
    ctx = make_synth_ctx(pricing, response)
    result = asyncio.run(observed_gtm_motion.synthesize(ctx))
    assert result.cache_hit is True


def test_synth_voice_processes_gap_bullets():
    pricing = PricingPackagingData(
        has_public_pricing=True, is_contact_us_gated=False,
        current_pricing_url="https://example.com/pricing",
    )
    from rrxray.voice.rr_voice import VoiceViolationError
    ctx = make_synth_ctx(pricing, make_anthropic_response(
        ["Clean paragraph."],
        ["We leverage data here."],  # forbidden word in bullet
    ))
    with pytest.raises(VoiceViolationError):
        asyncio.run(observed_gtm_motion.synthesize(ctx))


def test_synth_voice_processes_discovery_questions():
    pricing = PricingPackagingData(
        has_public_pricing=True, is_contact_us_gated=False,
        current_pricing_url="https://example.com/pricing",
    )
    from rrxray.voice.rr_voice import VoiceViolationError
    ctx = make_synth_ctx(pricing, make_anthropic_response(
        ["Clean."], ["clean bullet"],
        questions=["What synergies exist between teams?"],  # forbidden word
    ))
    with pytest.raises(VoiceViolationError):
        asyncio.run(observed_gtm_motion.synthesize(ctx))


def test_synth_voice_processes_finding_text():
    pricing = PricingPackagingData(
        has_public_pricing=True, is_contact_us_gated=False,
        current_pricing_url="https://example.com/pricing",
    )
    from datetime import UTC, datetime

    from rrxray.schemas._shared import Finding, SourceCitation
    from rrxray.voice.rr_voice import VoiceViolationError

    finding = Finding(
        text="Pricing is impactful for the GTM motion.",  # forbidden word
        source=SourceCitation(
            url="https://example.com/pricing",
            timestamp=datetime(2026, 5, 1, tzinfo=UTC),
        ),
    )
    ctx = make_synth_ctx(pricing, make_anthropic_response(
        ["Clean."], ["clean bullet"], findings=[finding],
    ))
    with pytest.raises(VoiceViolationError):
        asyncio.run(observed_gtm_motion.synthesize(ctx))


def test_synth_voice_processes_gaps_field():
    pricing = PricingPackagingData(
        has_public_pricing=True, is_contact_us_gated=False,
        current_pricing_url="https://example.com/pricing",
    )
    from rrxray.voice.rr_voice import VoiceViolationError
    ctx = make_synth_ctx(pricing, make_anthropic_response(
        ["Clean."], ["clean bullet"],
        gaps=["holistic approach to pricing"],  # forbidden word
    ))
    with pytest.raises(VoiceViolationError):
        asyncio.run(observed_gtm_motion.synthesize(ctx))
