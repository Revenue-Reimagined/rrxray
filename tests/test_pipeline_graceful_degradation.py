"""Pipeline orchestrator: runs collectors and synthesizers concurrently with
return_exceptions=True for graceful degradation."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from rrxray import pipeline
from rrxray.schemas.data import XrayData


def fake_config(tmp_path: Path):
    config = MagicMock()
    config.domain = "example.com"
    config.company_name = None
    config.competitors = []
    config.skip_modules = []
    config.mode = "internal"
    config.use_cache = True
    config.model = "claude-sonnet-4-6"
    config.output_dir = tmp_path / "out"
    config.evidence_dir = tmp_path / "out" / "evidence"
    config.cache_dir = tmp_path / "cache"
    return config


def test_run_pipeline_returns_xraydata_and_markdown(tmp_path, monkeypatch):
    config = fake_config(tmp_path)

    # Stub each collector and synthesizer at the module level
    fake_pricing = MagicMock()
    fake_pricing.NAME = "pricing_packaging"

    async def fake_collect(ctx):
        from rrxray.schemas.pricing_packaging import PricingPackagingData
        return PricingPackagingData(
            has_public_pricing=True,
            is_contact_us_gated=False,
            current_pricing_url="https://example.com/pricing",
        )

    fake_pricing.collect = fake_collect

    fake_synth = MagicMock()
    fake_synth.NAME = "observed_gtm_motion"

    async def fake_synthesize(ctx):
        from rrxray.schemas.data import ObservedGtmMotionNarrative
        return ObservedGtmMotionNarrative(
            narrative_paragraphs=["Self-serve motion observed."],
            gap_bullets=["Pricing static for 18 months"],
            findings=[], gaps=[], discovery_questions=[],
            model_used="claude-sonnet-4-6", cache_hit=False,
        )

    fake_synth.synthesize = fake_synthesize

    monkeypatch.setattr(pipeline, "COLLECTORS", [fake_pricing])
    monkeypatch.setattr(pipeline, "SYNTHESIZERS", [fake_synth])
    monkeypatch.setattr(pipeline, "build_collector_context", lambda c: MagicMock())
    monkeypatch.setattr(pipeline, "build_synthesizer_context",
                        lambda c, o, v, a: MagicMock(collector_outputs=o, voice=v, anonymizer=a, config=c))

    data, markdown = asyncio.run(pipeline.run_pipeline(config))
    assert isinstance(data, XrayData)
    assert data.collectors.pricing_packaging is not None
    assert data.synthesizers.observed_gtm_motion is not None
    assert "Self-serve motion observed." in markdown
    assert data.failures == []


def test_collector_failure_recorded_no_crash(tmp_path, monkeypatch):
    config = fake_config(tmp_path)

    fake_pricing = MagicMock()
    fake_pricing.NAME = "pricing_packaging"

    async def boom(ctx):
        raise ValueError("collector exploded")

    fake_pricing.collect = boom

    fake_synth = MagicMock()
    fake_synth.NAME = "observed_gtm_motion"

    async def fake_synthesize(ctx):
        return None  # graceful: no pricing data

    fake_synth.synthesize = fake_synthesize

    monkeypatch.setattr(pipeline, "COLLECTORS", [fake_pricing])
    monkeypatch.setattr(pipeline, "SYNTHESIZERS", [fake_synth])
    monkeypatch.setattr(pipeline, "build_collector_context", lambda c: MagicMock())
    monkeypatch.setattr(pipeline, "build_synthesizer_context",
                        lambda c, o, v, a: MagicMock(collector_outputs=o, voice=v, anonymizer=a, config=c))

    data, markdown = asyncio.run(pipeline.run_pipeline(config))
    assert data.collectors.pricing_packaging is None
    assert any(f.module == "pricing_packaging" and f.kind == "collector" for f in data.failures)
    assert "[Module not available for this domain]" in markdown


def test_data_json_round_trips(tmp_path, monkeypatch):
    config = fake_config(tmp_path)

    fake_pricing = MagicMock()
    fake_pricing.NAME = "pricing_packaging"

    async def fake_collect(ctx):
        from rrxray.schemas.pricing_packaging import PricingPackagingData
        return PricingPackagingData(
            has_public_pricing=True, is_contact_us_gated=False,
            current_pricing_url="https://example.com/pricing",
        )

    fake_pricing.collect = fake_collect

    fake_synth = MagicMock()
    fake_synth.NAME = "observed_gtm_motion"
    fake_synth.synthesize = AsyncMock(return_value=None)

    monkeypatch.setattr(pipeline, "COLLECTORS", [fake_pricing])
    monkeypatch.setattr(pipeline, "SYNTHESIZERS", [fake_synth])
    monkeypatch.setattr(pipeline, "build_collector_context", lambda c: MagicMock())
    monkeypatch.setattr(pipeline, "build_synthesizer_context",
                        lambda c, o, v, a: MagicMock(collector_outputs=o, voice=v, anonymizer=a, config=c))

    data, _markdown = asyncio.run(pipeline.run_pipeline(config))
    serialized = data.model_dump_json()
    restored = XrayData.model_validate(json.loads(serialized))
    assert restored.domain == data.domain
    assert restored.collectors.pricing_packaging is not None


def test_voice_log_includes_render_time_substitutions(tmp_path, monkeypatch):
    config = fake_config(tmp_path)

    fake_pricing = MagicMock()
    fake_pricing.NAME = "pricing_packaging"

    async def fake_collect(ctx):
        from rrxray.schemas.pricing_packaging import PricingPackagingData, PricingTier
        return PricingPackagingData(
            has_public_pricing=True, is_contact_us_gated=False,
            current_pricing_url="https://example.com/pricing",
            current_tiers=[PricingTier(
                name="Pro", price="$50", cadence="month", notes="We leverage data.",
            )],
        )

    fake_pricing.collect = fake_collect

    fake_synth = MagicMock()
    fake_synth.NAME = "observed_gtm_motion"
    fake_synth.synthesize = AsyncMock(return_value=None)

    monkeypatch.setattr(pipeline, "COLLECTORS", [fake_pricing])
    monkeypatch.setattr(pipeline, "SYNTHESIZERS", [fake_synth])
    monkeypatch.setattr(pipeline, "build_collector_context", lambda c: MagicMock())
    monkeypatch.setattr(pipeline, "build_synthesizer_context",
                        lambda c, o, v, a: MagicMock(collector_outputs=o, voice=v, anonymizer=a, config=c))

    data, _markdown = asyncio.run(pipeline.run_pipeline(config))
    # Voice substitution from rendering Pro tier notes should be in voice_log
    assert any(e.rule == "forbidden_word" and e.original.lower() == "leverage" for e in data.voice_log)


def test_synthesizer_failure_recorded_no_crash(tmp_path, monkeypatch):
    """Synthesizer raising should produce a ModuleFailure row, not crash the pipeline."""
    config = fake_config(tmp_path)

    fake_pricing = MagicMock()
    fake_pricing.NAME = "pricing_packaging"

    async def fake_collect(ctx):
        from rrxray.schemas.pricing_packaging import PricingPackagingData
        return PricingPackagingData(
            has_public_pricing=True, is_contact_us_gated=False,
            current_pricing_url="https://example.com/pricing",
        )

    fake_pricing.collect = fake_collect

    fake_synth = MagicMock()
    fake_synth.NAME = "observed_gtm_motion"

    async def boom(ctx):
        raise RuntimeError("synthesizer exploded")

    fake_synth.synthesize = boom

    monkeypatch.setattr(pipeline, "COLLECTORS", [fake_pricing])
    monkeypatch.setattr(pipeline, "SYNTHESIZERS", [fake_synth])
    monkeypatch.setattr(pipeline, "build_collector_context", lambda c: MagicMock())
    monkeypatch.setattr(pipeline, "build_synthesizer_context",
                        lambda c, o, v, a: MagicMock(collector_outputs=o, voice=v, anonymizer=a, config=c))

    data, _markdown = asyncio.run(pipeline.run_pipeline(config))
    assert data.synthesizers.observed_gtm_motion is None
    assert any(f.module == "observed_gtm_motion" and f.kind == "synthesizer" for f in data.failures)


def test_cancellation_propagates(tmp_path, monkeypatch):
    """Pipeline cancellation must propagate; CancelledError is not a ModuleFailure."""
    config = fake_config(tmp_path)

    fake_pricing = MagicMock()
    fake_pricing.NAME = "pricing_packaging"

    async def hang_then_cancel(ctx):
        await asyncio.sleep(10)  # will be cancelled before this finishes

    fake_pricing.collect = hang_then_cancel

    fake_synth = MagicMock()
    fake_synth.NAME = "observed_gtm_motion"
    fake_synth.synthesize = AsyncMock(return_value=None)

    monkeypatch.setattr(pipeline, "COLLECTORS", [fake_pricing])
    monkeypatch.setattr(pipeline, "SYNTHESIZERS", [fake_synth])
    monkeypatch.setattr(pipeline, "build_collector_context", lambda c: MagicMock())
    monkeypatch.setattr(pipeline, "build_synthesizer_context",
                        lambda c, o, v, a: MagicMock(collector_outputs=o, voice=v, anonymizer=a, config=c))

    async def main():
        task = asyncio.create_task(pipeline.run_pipeline(config))
        await asyncio.sleep(0.05)
        task.cancel()
        await task

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(main())


def test_tech_stack_collector_registered_in_pipeline():
    """tech_stack module must be in COLLECTORS so the orchestrator runs it."""
    from rrxray import pipeline
    from rrxray.collectors import tech_stack

    assert tech_stack in pipeline.COLLECTORS


def test_pipeline_includes_tech_stack_in_data_json(tmp_path, monkeypatch):
    """End-to-end: a tech_stack stub returns TechStackData; pipeline puts it on CollectorOutputs."""
    from rrxray import pipeline
    from rrxray.schemas.tech_stack import DetectedTool, TechStackData

    config = fake_config(tmp_path)

    fake_pricing = MagicMock()
    fake_pricing.NAME = "pricing_packaging"

    async def pricing_collect(ctx):
        from rrxray.schemas.pricing_packaging import PricingPackagingData
        return PricingPackagingData(
            has_public_pricing=True, is_contact_us_gated=False,
            current_pricing_url="https://example.com/pricing",
        )

    fake_pricing.collect = pricing_collect

    fake_tech_stack = MagicMock()
    fake_tech_stack.NAME = "tech_stack"

    async def tech_collect(ctx):
        return TechStackData(
            detected_tools=[DetectedTool(
                name="HubSpot", category="marketing_automation", confidence="high",
                signature_id="hubspot:strict_js", matched_text="x",
            )],
            categories_observed=["marketing_automation"],
        )

    fake_tech_stack.collect = tech_collect

    fake_synth = MagicMock()
    fake_synth.NAME = "observed_gtm_motion"
    fake_synth.synthesize = AsyncMock(return_value=None)

    monkeypatch.setattr(pipeline, "COLLECTORS", [fake_pricing, fake_tech_stack])
    monkeypatch.setattr(pipeline, "SYNTHESIZERS", [fake_synth])
    monkeypatch.setattr(pipeline, "build_collector_context", lambda c: MagicMock())
    monkeypatch.setattr(
        pipeline, "build_synthesizer_context",
        lambda c, o, v, a: MagicMock(collector_outputs=o, voice=v, anonymizer=a, config=c),
    )

    data, markdown = asyncio.run(pipeline.run_pipeline(config))
    assert data.collectors.tech_stack is not None
    assert data.collectors.tech_stack.detected_tools[0].name == "HubSpot"
    assert "### Tech Stack" in markdown
    assert "HubSpot" in markdown


def test_pipeline_runs_section_a_with_both_collectors(tmp_path, monkeypatch):
    """When both pricing_packaging and tech_stack succeed, Section A synthesizer reads both."""
    from rrxray.schemas.tech_stack import DetectedTool, TechStackData

    config = fake_config(tmp_path)

    fake_pricing = MagicMock()
    fake_pricing.NAME = "pricing_packaging"

    async def pricing_collect(ctx):
        from rrxray.schemas.pricing_packaging import PricingPackagingData
        return PricingPackagingData(
            has_public_pricing=True, is_contact_us_gated=False,
            current_pricing_url="https://example.com/pricing",
        )

    fake_pricing.collect = pricing_collect

    fake_tech_stack = MagicMock()
    fake_tech_stack.NAME = "tech_stack"

    async def tech_collect(ctx):
        return TechStackData(
            detected_tools=[DetectedTool(
                name="HubSpot", category="marketing_automation", confidence="high",
                signature_id="hubspot:strict_js", matched_text="x",
            )],
            categories_observed=["marketing_automation"],
            categories_absent=["analytics", "tag_manager", "chat", "product_analytics",
                               "crm", "cdp", "ab_testing", "attribution"],
        )

    fake_tech_stack.collect = tech_collect

    fake_synth = MagicMock()
    fake_synth.NAME = "observed_gtm_motion"

    captured_ctx = {}

    async def synth_capture(ctx):
        # Verify the synth context has both collectors populated
        captured_ctx["pricing"] = ctx.collector_outputs.pricing_packaging
        captured_ctx["tech_stack"] = ctx.collector_outputs.tech_stack
        return None  # graceful skip; we only care about the context shape

    fake_synth.synthesize = synth_capture

    monkeypatch.setattr(pipeline, "COLLECTORS", [fake_pricing, fake_tech_stack])
    monkeypatch.setattr(pipeline, "SYNTHESIZERS", [fake_synth])
    monkeypatch.setattr(pipeline, "build_collector_context", lambda c: MagicMock())
    monkeypatch.setattr(
        pipeline, "build_synthesizer_context",
        lambda c, o, v, a: MagicMock(collector_outputs=o, voice=v, anonymizer=a, config=c),
    )

    asyncio.run(pipeline.run_pipeline(config))
    assert captured_ctx["pricing"] is not None
    assert captured_ctx["tech_stack"] is not None
    assert captured_ctx["tech_stack"].detected_tools[0].name == "HubSpot"
