"""Pure-function Markdown renderer for the internal-mode GTM X-Ray report."""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from rrxray.schemas.data import XrayData
from rrxray.voice.anonymizer import Anonymizer
from rrxray.voice.rr_voice import VoicePostProcessor


def _collect_discovery_questions(data: XrayData) -> list[str]:
    """Walk every collector and synthesizer output, dedupe while preserving order."""
    seen: set[str] = set()
    out: list[str] = []
    for field_name in data.collectors.model_fields_set or data.collectors.__class__.model_fields:
        c = getattr(data.collectors, field_name, None)
        if c is None:
            continue
        for q in getattr(c, "discovery_questions", []):
            if q not in seen:
                seen.add(q)
                out.append(q)
    for field_name in data.synthesizers.model_fields_set or data.synthesizers.__class__.model_fields:
        s = getattr(data.synthesizers, field_name, None)
        if s is None:
            continue
        for q in getattr(s, "discovery_questions", []):
            if q not in seen:
                seen.add(q)
                out.append(q)
    return out


def _templates_dir() -> Path:
    """Resolve the templates directory relative to the project root.

    rrxray ships templates outside the package because Jinja loaders work better with
    file paths than with importlib.resources. The repo layout is:
        rrxray/
        templates/         <- here
    """
    return Path(__file__).parent.parent.parent / "templates"


def render_internal(
    data: XrayData,
    anonymizer: Anonymizer,
    voice: VoicePostProcessor,
) -> str:
    """Render the internal-mode GTM X-Ray report. Pure: returns string, no I/O."""
    env = Environment(
        loader=FileSystemLoader(str(_templates_dir())),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["anonymize"] = anonymizer.anonymize
    env.filters["voice_collector"] = lambda text: voice.process_collector_text(
        str(text), context="render"
    )
    env.globals["collected_discovery_questions"] = _collect_discovery_questions
    env.globals["voice_events"] = voice.peek_log

    template = env.get_template("report_internal.md.jinja")
    rendered = template.render(data=data)

    # Defense in depth: if any registered name reached the output unanonymized, raise.
    anonymizer.assert_no_unanonymized(rendered)

    return rendered
