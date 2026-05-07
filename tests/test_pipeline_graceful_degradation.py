"""Pipeline orchestrator: runs collectors and synthesizers concurrently with
return_exceptions=True for graceful degradation."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

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
