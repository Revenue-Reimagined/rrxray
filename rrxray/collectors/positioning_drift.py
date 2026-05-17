"""positioning_drift collector: Wayback homepage diffs detect messaging shift."""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from rrxray.collectors._positioning_drift_catalog import (
    _H1_RE,
    _MD_LINK_RE,
    MAX_HEADLINE_LEN,
    MAX_NAV_ITEMS,
    NAV_SKIP_PATTERNS,
)
from rrxray.schemas._shared import Finding, SourceCitation
from rrxray.schemas.positioning_drift import HomepageSnapshot

NAME = "positioning_drift"
log = logging.getLogger(f"rrxray.collectors.{NAME}")


def _extract_fields(markdown: str) -> tuple[str | None, str | None, list[str]]:
    """Extract (hero_headline, sub_headline, primary_nav) from homepage markdown.

    All extraction is deterministic — no LLM. Falls back gracefully on any missing
    element.
    """
    if not markdown:
        return None, None, []

    # Hero: first H1
    h1_match = _H1_RE.search(markdown)
    hero: str | None = None
    if h1_match:
        hero = h1_match.group(1).strip()[:MAX_HEADLINE_LEN]

    # Sub-headline: first non-empty, non-heading, non-link-only line after H1
    sub: str | None = None
    search_start = h1_match.end() if h1_match else 0
    for line in markdown[search_start:].splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            break  # hit next heading — stop looking
        if stripped.startswith("[") and stripped.endswith(")"):
            continue  # nav-link-only line
        sub = stripped[:300]
        break

    # Nav: markdown links in first third of document (or 1000 chars, whichever is larger)
    cutoff = max(len(markdown) // 3, 1000)
    nav_section = markdown[:cutoff]
    nav_items: list[str] = []
    seen: set[str] = set()
    for m in _MD_LINK_RE.finditer(nav_section):
        text = m.group(1).strip()
        if not text or len(text) < 2:
            continue
        lower = text.lower()
        if any(p.search(lower) for p in NAV_SKIP_PATTERNS):
            continue
        if lower in seen:
            continue
        seen.add(lower)
        nav_items.append(text)
        if len(nav_items) >= MAX_NAV_ITEMS:
            break

    return hero, sub, nav_items


def _diff_snapshots(
    oldest: HomepageSnapshot,
    newest: HomepageSnapshot,
) -> tuple[list[str], str | None]:
    """Compare oldest and newest snapshots. Return (changed_fields, diff_summary)."""
    changed: list[str] = []
    parts: list[str] = []

    # Hero headline
    if oldest.hero_headline != newest.hero_headline:
        changed.append("hero_headline")
        old_h = oldest.hero_headline or "(none)"
        new_h = newest.hero_headline or "(none)"
        parts.append(f"hero shifted from '{old_h[:60]}' to '{new_h[:60]}'")

    # Sub-headline
    if oldest.sub_headline != newest.sub_headline:
        changed.append("sub_headline")
        parts.append("sub-headline changed")

    # Primary nav (set comparison)
    old_nav = set(oldest.primary_nav)
    new_nav = set(newest.primary_nav)
    added = sorted(new_nav - old_nav)
    removed = sorted(old_nav - new_nav)
    if added or removed:
        changed.append("primary_nav")
        nav_parts: list[str] = []
        if added:
            nav_parts.append(f"{len(added)} nav item{'s' if len(added) > 1 else ''} added ({', '.join(added[:3])})")
        if removed:
            nav_parts.append(f"{len(removed)} nav item{'s' if len(removed) > 1 else ''} removed ({', '.join(removed[:3])})")
        parts.append("; ".join(nav_parts))

    summary = "; ".join(parts) if parts else None
    return changed, summary


def _emit_findings(
    domain: str,
    snapshots: list[HomepageSnapshot],
    changed_fields: list[str],
    diff_summary: str | None,
) -> tuple[list[Finding], list[str], list[str]]:
    """Rule-based findings, gaps, and discovery questions. No LLM."""
    now = datetime.now(UTC)
    source_url = f"https://{domain}"
    findings: list[Finding] = []
    gaps: list[str] = []
    questions: list[str] = []

    if not snapshots:
        gaps.append(
            "No Wayback Machine homepage snapshots recovered; "
            "positioning drift assessment not available for this domain."
        )
        return findings, gaps, questions

    if len(snapshots) == 1:
        findings.append(Finding(
            text=(
                f"Only one historical homepage snapshot recovered ({snapshots[0].timestamp}); "
                "drift assessment requires at least two data points."
            ),
            source=SourceCitation(url=source_url, timestamp=now),
        ))
        return findings, gaps, questions

    # 2+ snapshots
    date_range = f"{snapshots[0].timestamp} to {snapshots[-1].timestamp}"
    n = len(snapshots)

    if not changed_fields:
        findings.append(Finding(
            text=(
                f"Homepage messaging has been stable across {n} snapshots "
                f"in the 18-month window ({date_range}); hero headline, "
                "sub-headline, and primary nav are consistent."
            ),
            source=SourceCitation(url=source_url, timestamp=now),
        ))
        return findings, gaps, questions

    if diff_summary:
        findings.append(Finding(
            text=(
                f"Positioning shift detected across {n} snapshots ({date_range}): {diff_summary}."
            ),
            source=SourceCitation(url=source_url, timestamp=now),
        ))

    if "hero_headline" in changed_fields:
        old_h = snapshots[0].hero_headline or "(none)"
        new_h = snapshots[-1].hero_headline or "(none)"
        questions.append(
            f"Your homepage hero shifted from '{old_h[:60]}' to '{new_h[:60]}' "
            "over the past 18 months. What drove that repositioning: new ICP, "
            "competitive pressure, or internal rebrand?"
        )

    return findings, gaps, questions
