"""Frozen dataclasses for collector and synthesizer execution contexts."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rrxray.config import Config
    from rrxray.schemas.data import CollectorOutputs
    from rrxray.services.anthropic_client import AnthropicClient
    from rrxray.services.firecrawl_client import FirecrawlClient
    from rrxray.services.wayback_client import WaybackClient
    from rrxray.voice.anonymizer import Anonymizer
    from rrxray.voice.rr_voice import VoicePostProcessor


@dataclass(frozen=True)
class CollectorContext:
    domain: str
    company_name: str | None
    firecrawl: FirecrawlClient
    wayback: WaybackClient
    evidence_dir: Path
    config: Config


@dataclass(frozen=True)
class SynthesizerContext:
    collector_outputs: CollectorOutputs
    anthropic: AnthropicClient
    voice: VoicePostProcessor
    anonymizer: Anonymizer
    config: Config
