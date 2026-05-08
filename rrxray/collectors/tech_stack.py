"""tech_stack collector: detects analytics/martech/CRM tools by HTML signature matching."""
from __future__ import annotations

import logging
import re
from datetime import datetime

from rrxray.collectors._tech_stack_catalog import CATEGORIES, SIGNATURES
from rrxray.schemas._shared import Finding, SourceCitation
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


def _emit_findings(
    detected: list[DetectedTool],
    domain: str,
    scrape_url: str,
    now: datetime,
) -> tuple[list[Finding], list[str], list[str]]:
    """Rule-based findings/gaps/questions. No LLM."""
    findings: list[Finding] = []
    gaps: list[str] = []
    questions: list[str] = []

    if not detected:
        findings.append(Finding(
            text="No analytics, marketing, or CRM tags detected on the homepage.",
            source=SourceCitation(url=scrape_url, timestamp=now),
        ))
        questions.append(
            "We did not detect any common marketing or analytics tooling on your homepage. "
            "Is that a deliberate posture (e.g., privacy-led), or are tags loaded server-side "
            "or via a tag manager we did not match?"
        )
        return findings, gaps, questions

    categories = {t.category for t in detected}
    absent = [c for c in CATEGORIES if c not in categories]

    has_marketing = "marketing_automation" in categories
    has_crm = "crm" in categories
    has_product_analytics = "product_analytics" in categories
    has_chat = "chat" in categories

    if has_marketing and not has_crm:
        findings.append(Finding(
            text=(
                "Marketing automation present; no CRM signature detected on the homepage. "
                "CRM may be detected via other surfaces."
            ),
            source=SourceCitation(url=scrape_url, timestamp=now),
        ))

    if has_product_analytics:
        questions.append(
            "Product analytics tooling indicates an in-product activation focus. "
            "What are your activation and time-to-value benchmarks today?"
        )

    if has_chat and not has_marketing:
        gaps.append(
            "Live chat tooling is present but no marketing automation was detected. "
            "Inbound conversations may not be feeding a nurture sequence."
        )

    if "analytics" in absent and "tag_manager" in absent:
        gaps.append(
            "Neither web analytics nor a tag manager was detected. "
            "Site engagement data may be sparse."
        )
    if "marketing_automation" in absent and detected:
        gaps.append(
            "No marketing automation tooling was detected; "
            "lead nurture may rely on manual outreach."
        )
    if "product_analytics" in absent and detected:
        gaps.append(
            "No product analytics was detected; activation and feature adoption "
            "signals are likely informal."
        )

    return findings, gaps, questions


import json  # noqa: E402
from datetime import UTC  # noqa: E402
from pathlib import Path  # noqa: E402

from rrxray.context import CollectorContext  # noqa: E402
from rrxray.schemas.tech_stack import TechStackData  # noqa: E402
from rrxray.services.firecrawl_client import FirecrawlError  # noqa: E402


def _write_evidence(
    evidence_dir: Path,
    html: str,
    detected: list[DetectedTool],
) -> None:
    """Write the raw scraped HTML and the parsed detection set to the evidence dir."""
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / "homepage.html").write_text(html, encoding="utf-8")
    (evidence_dir / "detections.json").write_text(
        json.dumps([t.model_dump() for t in detected], indent=2),
        encoding="utf-8",
    )


async def collect(ctx: CollectorContext) -> TechStackData:
    """Scrape the homepage; run all signatures; emit DetectedTool list and findings."""
    now = datetime.now(UTC)
    homepage_url = f"https://{ctx.domain}"

    try:
        page = await ctx.firecrawl.scrape_url(homepage_url, only_main_content=False)
    except FirecrawlError as e:
        log.warning("homepage scrape failed for %s: %s", homepage_url, e)
        return TechStackData(
            findings=[Finding(
                text=f"Could not fetch homepage at {homepage_url} for tech stack detection: {e}",
                source=SourceCitation(url=homepage_url, timestamp=now),
            )],
        )

    html = page.html or ""
    detected = _detect(html)
    categories_observed = sorted({t.category for t in detected})
    categories_absent = [c for c in CATEGORIES if c not in categories_observed]

    findings, gaps, questions = _emit_findings(detected, ctx.domain, homepage_url, now)

    _write_evidence(ctx.evidence_dir / NAME, html, detected)

    sources = [SourceCitation(
        url=homepage_url,
        timestamp=now,
        evidence_path=str(
            (ctx.evidence_dir / NAME / "homepage.html").relative_to(ctx.evidence_dir)
        ),
    )]

    return TechStackData(
        detected_tools=detected,
        categories_observed=categories_observed,
        categories_absent=categories_absent,
        findings=findings,
        gaps=gaps,
        discovery_questions=questions,
        sources=sources,
    )
