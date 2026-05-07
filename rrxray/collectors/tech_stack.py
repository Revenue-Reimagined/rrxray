"""tech_stack collector: detects analytics/martech/CRM tools by HTML signature matching."""
from __future__ import annotations

import logging
import re

from rrxray.collectors._tech_stack_catalog import SIGNATURES
from rrxray.schemas.tech_stack import DetectedTool

NAME = "tech_stack"
log = logging.getLogger(f"rrxray.collectors.{NAME}")


def _compile_signatures() -> list[dict[str, object]]:
    """Pre-compile every signature regex once at module load time."""
    compiled: list[dict[str, object]] = []
    for sig in SIGNATURES:
        compiled.append({
            **sig,
            "compiled": re.compile(sig["pattern"], re.IGNORECASE),
        })
    return compiled


_COMPILED = _compile_signatures()


def _detect(html: str) -> list[DetectedTool]:
    """Run every compiled signature against the HTML.

    Returns one DetectedTool per tool name; if both strict and loose signatures
    match for the same tool, the higher-confidence detection wins.

    Results are sorted by (category, name) for deterministic output across runs.
    """
    matches: dict[str, DetectedTool] = {}
    for sig in _COMPILED:
        m = sig["compiled"].search(html)  # type: ignore[union-attr]
        if not m:
            continue

        existing = matches.get(sig["tool"])  # type: ignore[arg-type]
        new_conf = sig["confidence"]

        # Keep the higher-confidence detection per tool name
        if existing and existing.confidence == "high" and new_conf == "low":
            continue

        matches[sig["tool"]] = DetectedTool(  # type: ignore[arg-type]
            name=sig["tool"],  # type: ignore[arg-type]
            category=sig["category"],  # type: ignore[arg-type]
            confidence=new_conf,  # type: ignore[arg-type]
            signature_id=sig["id"],  # type: ignore[arg-type]
            matched_text=m.group(0)[:100],
        )
    return sorted(matches.values(), key=lambda t: (t.category, t.name))
