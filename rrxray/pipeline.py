"""Pipeline orchestrator: runs collectors and synthesizers concurrently with
graceful degradation, then renders."""
from __future__ import annotations

import asyncio
import logging
import traceback as tb_module
from datetime import UTC, datetime
from importlib.metadata import version

from rrxray.collectors import pricing_packaging, tech_stack
from rrxray.context import CollectorContext, SynthesizerContext
from rrxray.rendering.markdown import render_internal
from rrxray.schemas.data import (
    CollectorOutputs,
    InputParams,
    ModuleFailure,
    RunMetadata,
    SourceCitation,
    SynthesizerOutputs,
    XrayData,
)
from rrxray.services.anthropic_client import AnthropicClient
from rrxray.services.cache import DiskCache
from rrxray.services.firecrawl_client import FirecrawlClient
from rrxray.services.wayback_client import WaybackClient
from rrxray.synthesizers import observed_gtm_motion_pricing
from rrxray.voice.anonymizer import Anonymizer
from rrxray.voice.rr_voice import VoicePostProcessor

log = logging.getLogger("rrxray.pipeline")

# Phase 2 will append to these lists.
COLLECTORS = [pricing_packaging, tech_stack]
SYNTHESIZERS = [observed_gtm_motion_pricing]


def build_collector_context(config) -> CollectorContext:
    cache_root = config.cache_dir
    firecrawl = FirecrawlClient(
        api_key=config.firecrawl_api_key.get_secret_value() if config.firecrawl_api_key else "",
        cache=DiskCache(dir=cache_root / "firecrawl", mode="live" if config.use_cache else "refresh"),
        max_concurrent=getattr(config, "firecrawl_max_concurrent", 5),
    )
    wayback = WaybackClient(
        firecrawl=firecrawl,
        cache=DiskCache(dir=cache_root / "wayback", mode="live" if config.use_cache else "refresh"),
    )
    return CollectorContext(
        domain=config.domain,
        company_name=config.company_name,
        firecrawl=firecrawl,
        wayback=wayback,
        evidence_dir=config.evidence_dir,
        config=config,
    )


def build_synthesizer_context(
    config,
    collector_outputs: CollectorOutputs,
    voice: VoicePostProcessor,
    anonymizer: Anonymizer,
) -> SynthesizerContext:
    cache_root = config.cache_dir
    anthropic = AnthropicClient(
        api_key=config.anthropic_api_key.get_secret_value() if config.anthropic_api_key else "",
        cache=DiskCache(dir=cache_root / "anthropic", mode="live" if config.use_cache else "refresh"),
    )
    return SynthesizerContext(
        collector_outputs=collector_outputs,
        anthropic=anthropic,
        voice=voice,
        anonymizer=anonymizer,
        config=config,
    )


async def run_collectors(ctx: CollectorContext) -> tuple[CollectorOutputs, list[ModuleFailure]]:
    coros = [(c.NAME, c.collect(ctx)) for c in COLLECTORS]
    results = await asyncio.gather(*[coro for _, coro in coros], return_exceptions=True)
    outputs = CollectorOutputs()
    failures: list[ModuleFailure] = []
    for (name, _), result in zip(coros, results, strict=True):
        if isinstance(result, asyncio.CancelledError):
            raise result
        if isinstance(result, BaseException):
            tb = "".join(tb_module.format_exception(type(result), result, result.__traceback__))
            failures.append(ModuleFailure(module=name, kind="collector", error=str(result), traceback=tb))
            log.warning("Collector %s failed: %s", name, result)
        else:
            setattr(outputs, name, result)
    return outputs, failures


async def run_synthesizers(ctx: SynthesizerContext) -> tuple[SynthesizerOutputs, list[ModuleFailure]]:
    coros = [(s.NAME, s.synthesize(ctx)) for s in SYNTHESIZERS]
    results = await asyncio.gather(*[coro for _, coro in coros], return_exceptions=True)
    outputs = SynthesizerOutputs()
    failures: list[ModuleFailure] = []
    for (name, _), result in zip(coros, results, strict=True):
        if isinstance(result, asyncio.CancelledError):
            raise result
        if isinstance(result, BaseException):
            tb = "".join(tb_module.format_exception(type(result), result, result.__traceback__))
            failures.append(ModuleFailure(module=name, kind="synthesizer", error=str(result), traceback=tb))
            log.warning("Synthesizer %s failed: %s", name, result)
        elif result is not None:
            setattr(outputs, name, result)
    return outputs, failures


def _flatten_sources(collector_outputs: CollectorOutputs) -> list[SourceCitation]:
    sources: list[SourceCitation] = []
    for field_name in collector_outputs.__class__.model_fields:
        c = getattr(collector_outputs, field_name, None)
        if c is None:
            continue
        sources.extend(getattr(c, "sources", []))
    return sources


def _build_run_metadata(config) -> RunMetadata:
    try:
        tool_version = version("rrxray")
    except Exception:
        tool_version = "0.1.0"
    return RunMetadata(
        timestamp=datetime.now(UTC),
        tool_version=tool_version,
        modes_built=[config.mode],
        model_used=config.model,
    )


def _input_params(config) -> InputParams:
    return InputParams(
        domain=config.domain,
        company_name=config.company_name,
        competitors=getattr(config, "competitors", []),
        skip_modules=getattr(config, "skip_modules", []),
        mode=config.mode,
        use_cache=config.use_cache,
        model=config.model,
    )


async def run_pipeline(config) -> tuple[XrayData, str]:
    """Returns (data, rendered_markdown). Caller writes both to disk."""
    voice = VoicePostProcessor()
    anonymizer = Anonymizer()

    collector_ctx = build_collector_context(config)
    collector_outputs, collector_failures = await run_collectors(collector_ctx)

    synth_ctx = build_synthesizer_context(config, collector_outputs, voice, anonymizer)
    synth_outputs, synth_failures = await run_synthesizers(synth_ctx)

    data = XrayData(
        domain=config.domain,
        company_name=config.company_name,
        run_metadata=_build_run_metadata(config),
        inputs=_input_params(config),
        collectors=collector_outputs,
        synthesizers=synth_outputs,
        sources=_flatten_sources(collector_outputs),
        voice_log=[],  # filled in below after render
        failures=collector_failures + synth_failures,
    )

    rendered = render_internal(data, anonymizer, voice)
    data.voice_log = voice.flush_log()

    return data, rendered
