"""Canonical schemas for XrayData and shared helper types."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# Re-export shared base types so existing importers (tests, etc.) keep working.
from rrxray.schemas._shared import Finding, SourceCitation


class ModuleFailure(BaseModel):
    module: str
    kind: Literal["collector", "synthesizer"]
    error: str
    traceback: str


class VoiceEvent(BaseModel):
    rule: Literal["em_dash", "forbidden_word", "trademark"]
    original: str
    replacement: str | None
    context: str
    action: Literal["substitute", "raise"]


class RunMetadata(BaseModel):
    timestamp: datetime
    tool_version: str
    modes_built: list[str]
    model_used: str


class InputParams(BaseModel):
    domain: str
    company_name: str | None = None
    competitors: list[str] = []
    skip_modules: list[str] = []
    mode: str = "internal"
    use_cache: bool = True
    model: str = "claude-sonnet-4-6"


class CollectorOutputs(BaseModel):
    """One field per collector. None = not run or failed gracefully."""
    pricing_packaging: "PricingPackagingData | None" = None  # forward ref


class ObservedGtmMotionNarrative(BaseModel):
    narrative_paragraphs: list[str]
    gap_bullets: list[str]
    findings: list[Finding] = []
    gaps: list[str] = []
    discovery_questions: list[str] = []
    model_used: str
    cache_hit: bool


class SynthesizerOutputs(BaseModel):
    observed_gtm_motion: ObservedGtmMotionNarrative | None = None


class XrayData(BaseModel):
    schema_version: Literal["1"] = "1"
    domain: str
    company_name: str | None = None
    run_metadata: RunMetadata
    inputs: InputParams
    collectors: CollectorOutputs = Field(default_factory=CollectorOutputs)
    synthesizers: SynthesizerOutputs = Field(default_factory=SynthesizerOutputs)
    sources: list[SourceCitation] = []
    voice_log: list[VoiceEvent] = []
    failures: list[ModuleFailure] = []


# Resolve forward reference
from rrxray.schemas.pricing_packaging import PricingPackagingData  # noqa: E402

CollectorOutputs.model_rebuild()
