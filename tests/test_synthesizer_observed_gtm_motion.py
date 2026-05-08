"""Section A pricing-only synthesizer."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from rrxray.context import SynthesizerContext
from rrxray.schemas.data import CollectorOutputs
from rrxray.schemas.pricing_packaging import PricingPackagingData, PricingTier
from rrxray.schemas.tech_stack import DetectedTool, TechStackData
from rrxray.synthesizers import observed_gtm_motion
from rrxray.voice.anonymizer import Anonymizer
from rrxray.voice.rr_voice import VoicePostProcessor


def make_synth_ctx(
    pricing_data: PricingPackagingData | None = None,
    anthropic_response=None,
    tech_stack: TechStackData | None = None,
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


def test_synth_substitutes_forbidden_words_in_narrative():
    """Forbidden words in LLM narrative are substituted by sanitize_llm_output, not raised.

    Phase 2.1c update: a single forbidden-word emission used to fail the whole
    synthesis (see git history). It now substitutes via sanitize_llm_output so
    one stray "leverage" doesn't cost a full re-run. Vocabulary discipline still
    holds in the rendered output: the substitute appears, the original does not.
    """
    pricing = PricingPackagingData(
        has_public_pricing=True,
        is_contact_us_gated=False,
        current_pricing_url="https://example.com/pricing",
    )
    ctx = make_synth_ctx(
        pricing,
        make_anthropic_response(
            ["We leverage the pricing data."],  # forbidden word; should substitute
            ["clean bullet"],
        ),
    )
    result = asyncio.run(observed_gtm_motion.synthesize(ctx))
    assert result is not None
    assert "leverage" not in result.narrative_paragraphs[0].lower()
    assert "use" in result.narrative_paragraphs[0].lower()


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


def test_synth_substitutes_forbidden_words_in_gap_bullets():
    pricing = PricingPackagingData(
        has_public_pricing=True, is_contact_us_gated=False,
        current_pricing_url="https://example.com/pricing",
    )
    ctx = make_synth_ctx(pricing, make_anthropic_response(
        ["Clean paragraph."],
        ["We leverage data here."],
    ))
    result = asyncio.run(observed_gtm_motion.synthesize(ctx))
    assert result is not None
    assert "leverage" not in result.gap_bullets[0].lower()
    assert "use" in result.gap_bullets[0].lower()


def test_synth_substitutes_forbidden_words_in_discovery_questions():
    pricing = PricingPackagingData(
        has_public_pricing=True, is_contact_us_gated=False,
        current_pricing_url="https://example.com/pricing",
    )
    ctx = make_synth_ctx(pricing, make_anthropic_response(
        ["Clean."], ["clean bullet"],
        questions=["What synergies exist between teams?"],
    ))
    result = asyncio.run(observed_gtm_motion.synthesize(ctx))
    assert result is not None
    assert "synergies" not in result.discovery_questions[0].lower()
    assert "overlap" in result.discovery_questions[0].lower()


def test_synth_substitutes_forbidden_words_in_finding_text():
    pricing = PricingPackagingData(
        has_public_pricing=True, is_contact_us_gated=False,
        current_pricing_url="https://example.com/pricing",
    )
    from datetime import UTC, datetime

    from rrxray.schemas._shared import Finding, SourceCitation

    finding = Finding(
        text="Pricing is impactful for the GTM motion.",
        source=SourceCitation(
            url="https://example.com/pricing",
            timestamp=datetime(2026, 5, 1, tzinfo=UTC),
        ),
    )
    ctx = make_synth_ctx(pricing, make_anthropic_response(
        ["Clean."], ["clean bullet"], findings=[finding],
    ))
    result = asyncio.run(observed_gtm_motion.synthesize(ctx))
    assert result is not None
    assert "impactful" not in result.findings[0].text.lower()
    assert "meaningful" in result.findings[0].text.lower()


def test_synth_substitutes_forbidden_words_in_gaps_field():
    pricing = PricingPackagingData(
        has_public_pricing=True, is_contact_us_gated=False,
        current_pricing_url="https://example.com/pricing",
    )
    ctx = make_synth_ctx(pricing, make_anthropic_response(
        ["Clean."], ["clean bullet"],
        gaps=["holistic approach to pricing"],
    ))
    result = asyncio.run(observed_gtm_motion.synthesize(ctx))
    assert result is not None
    assert "holistic" not in result.gaps[0].lower()
    assert "end-to-end" in result.gaps[0].lower()


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


def test_synth_runs_with_three_collectors():
    """When all three Section A collectors are present, all three blocks render in the user message."""
    from rrxray.schemas.revenue_motion import JobPosting, RevenueMotionData
    pricing = PricingPackagingData(
        has_public_pricing=True, is_contact_us_gated=False,
        current_pricing_url="https://example.com/pricing",
        current_tiers=[PricingTier(name="Pro", price="$50", cadence="month")],
    )
    tech = TechStackData(
        detected_tools=[DetectedTool(
            name="HubSpot", category="marketing_automation", confidence="high",
            signature_id="hubspot:strict_js", matched_text="x",
        )],
        categories_observed=["marketing_automation"],
        categories_absent=["analytics", "tag_manager", "chat", "product_analytics",
                           "crm", "cdp", "ab_testing", "attribution"],
    )
    rm = RevenueMotionData(
        careers_page_url="https://example.com/careers",
        ats_platform="lever",
        open_roles=[
            JobPosting(title="Senior AE", category="ae", source="company_careers"),
            JobPosting(title="SDR", category="sdr", source="company_careers"),
        ],
        role_counts={"ae": 1, "sdr": 1},
        ae_to_sdr_ratio=1.0,
        linkedin_employee_count=247,
        linkedin_job_count=3,
    )

    fake_anthropic = MagicMock()
    fake_anthropic.complete_with_cached_system = AsyncMock(
        return_value=make_anthropic_response(
            ["Three-signal narrative."],
            ["Multi-signal observation"],
        ),
    )
    config = MagicMock(domain="example.com", model="claude-sonnet-4-6")
    config.evidence_dir = MagicMock()
    ctx = SynthesizerContext(
        collector_outputs=CollectorOutputs(
            pricing_packaging=pricing,
            tech_stack=tech,
            revenue_motion=rm,
        ),
        anthropic=fake_anthropic,
        voice=VoicePostProcessor(),
        anonymizer=Anonymizer(),
        config=config,
    )

    result = asyncio.run(observed_gtm_motion.synthesize(ctx))
    assert result is not None
    user_msg = ctx.anthropic.complete_with_cached_system.call_args.kwargs["user_message"]
    assert "Pricing & Packaging signal" in user_msg
    assert "Tech Stack signal" in user_msg
    assert "Revenue Motion signal" in user_msg
    assert "Senior AE" in user_msg
    assert "lever" in user_msg.lower()
    assert "247" in user_msg


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


def test_synth_reads_raw_page_text_into_prompt(tmp_path):
    """Raw evidence text is read from evidence_dir and injected into the user message."""
    import asyncio

    # Pre-populate evidence files with sentinel text
    pricing_dir = tmp_path / "pricing_packaging"
    pricing_dir.mkdir(parents=True)
    (pricing_dir / "current.md").write_text("SENTINEL_PRICING_RAW_TEXT", encoding="utf-8")

    tech_dir = tmp_path / "tech_stack"
    tech_dir.mkdir(parents=True)
    (tech_dir / "homepage.html").write_text("SENTINEL_HOMEPAGE_RAW_TEXT", encoding="utf-8")

    pricing = PricingPackagingData(
        has_public_pricing=True,
        is_contact_us_gated=False,
        current_pricing_url="https://example.com/pricing",
    )
    tech = TechStackData(
        detected_tools=[DetectedTool(
            name="HubSpot", category="marketing_automation", confidence="high",
            signature_id="hubspot:strict_js", matched_text="js.hs-scripts.com/x.js",
        )],
        categories_observed=["marketing_automation"],
        categories_absent=["analytics"],
    )

    fake_anthropic = MagicMock()
    fake_anthropic.complete_with_cached_system = AsyncMock(
        return_value=make_anthropic_response(["paragraph"], ["bullet"])
    )

    config = MagicMock(domain="example.com", model="claude-sonnet-4-6")
    config.evidence_dir = tmp_path

    from rrxray.voice.anonymizer import Anonymizer
    from rrxray.voice.rr_voice import VoicePostProcessor

    ctx = SynthesizerContext(
        collector_outputs=CollectorOutputs(
            pricing_packaging=pricing,
            tech_stack=tech,
        ),
        anthropic=fake_anthropic,
        voice=VoicePostProcessor(),
        anonymizer=Anonymizer(),
        config=config,
    )

    asyncio.run(observed_gtm_motion.synthesize(ctx))

    fake_anthropic.complete_with_cached_system.assert_called_once()
    user_msg = fake_anthropic.complete_with_cached_system.call_args.kwargs["user_message"]
    assert "SENTINEL_PRICING_RAW_TEXT" in user_msg
    assert "SENTINEL_HOMEPAGE_RAW_TEXT" in user_msg
