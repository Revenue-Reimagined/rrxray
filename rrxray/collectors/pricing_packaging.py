"""pricing_packaging collector: scrapes current pricing page + Wayback snapshots, diffs them."""
from __future__ import annotations

import json
import logging
import re
from datetime import UTC, date, datetime
from pathlib import Path

from rrxray.context import CollectorContext
from rrxray.schemas.data import Finding, SourceCitation
from rrxray.schemas.pricing_packaging import (
    HistoricalSnapshot,
    PricingChange,
    PricingPackagingData,
    PricingTier,
)
from rrxray.services.firecrawl_client import FirecrawlError, ScrapedPage
from rrxray.services.wayback_client import WaybackError

NAME = "pricing_packaging"
log = logging.getLogger(f"rrxray.collectors.{NAME}")

CANDIDATE_PATHS = ["/pricing", "/plans", "/pricing/"]

_PRICE_RE = re.compile(r"\$([\d,]+(?:\.\d{1,2})?)")
_TIER_HEADING_RE = re.compile(r"^#{2,3}\s+(.+?)\s*$", re.MULTILINE)
_CADENCE_HINTS = ["per month", "/month", "per year", "/year", "per user", "per seat", "/mo", "/yr"]
_CONTACT_HINTS = [
    "contact sales", "contact us", "request a demo", "request demo",
    "custom quote", "talk to sales",
]


def _extract_tiers(markdown: str) -> list[PricingTier]:
    """Heuristic tier extraction from a pricing page's markdown.

    Splits the markdown into sections by H2/H3 headings. For each section that contains
    a dollar amount, emits a PricingTier with name (heading), price (first $ amount),
    cadence (any matched cadence hint), and notes (rest of the section trimmed).
    Sections without a price are skipped.
    """
    tiers: list[PricingTier] = []
    headings = list(_TIER_HEADING_RE.finditer(markdown))
    if not headings:
        return tiers
    for i, h in enumerate(headings):
        start = h.end()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(markdown)
        body = markdown[start:end]
        price_m = _PRICE_RE.search(body)
        if price_m is None:
            continue
        name = h.group(1).split("—")[0].split(":")[0].strip()
        price = f"${price_m.group(1)}"
        cadence = ""
        for hint in _CADENCE_HINTS:
            if hint in body.lower():
                cadence = hint.lstrip("/")
                break
        notes = " ".join(body.split())[:200]
        tiers.append(PricingTier(name=name, price=price, cadence=cadence, notes=notes))
    return tiers


def _detect_contact_us(markdown: str) -> bool:
    """True if the page is contact-sales gated (no public prices) or appears to be."""
    has_dollar = bool(_PRICE_RE.search(markdown))
    has_contact_phrase = any(hint in markdown.lower() for hint in _CONTACT_HINTS)
    return has_contact_phrase and not has_dollar


def _parse_price_value(price: str) -> float | None:
    """Extract numeric value from a price string like '$50' or '$1,200.50'."""
    m = _PRICE_RE.search(price)
    if m is None:
        return None
    return float(m.group(1).replace(",", ""))


def _diff_tier_lists(
    older: list[PricingTier],
    current: list[PricingTier],
    observed_at: date,
) -> list[PricingChange]:
    """Compare two PricingTier lists and emit PricingChange rows.

    `older` represents the historically-earlier state; `current` the later state.
    Emits tier_added / tier_removed / price_increased / price_decreased rows.
    Comparison is by tier name (case-insensitive).
    """
    changes: list[PricingChange] = []
    older_by_name = {t.name.lower(): t for t in older}
    current_by_name = {t.name.lower(): t for t in current}

    for name_lower, t_current in current_by_name.items():
        if name_lower not in older_by_name:
            changes.append(PricingChange(
                date_observed=observed_at, kind="tier_added", before="", after=t_current.name,
            ))

    for name_lower, t_older in older_by_name.items():
        if name_lower not in current_by_name:
            changes.append(PricingChange(
                date_observed=observed_at, kind="tier_removed", before=t_older.name, after="",
            ))

    for name_lower in current_by_name.keys() & older_by_name.keys():
        t_old = older_by_name[name_lower]
        t_new = current_by_name[name_lower]
        old_v = _parse_price_value(t_old.price)
        new_v = _parse_price_value(t_new.price)
        if old_v is None or new_v is None:
            continue
        if new_v > old_v:
            changes.append(PricingChange(
                date_observed=observed_at, kind="price_increased",
                before=t_old.price, after=t_new.price,
            ))
        elif new_v < old_v:
            changes.append(PricingChange(
                date_observed=observed_at, kind="price_decreased",
                before=t_old.price, after=t_new.price,
            ))
    return changes


async def _discover_pricing_url(ctx: CollectorContext) -> tuple[str | None, ScrapedPage | None]:
    base = f"https://{ctx.domain}"
    for path in CANDIDATE_PATHS:
        url = base + path
        try:
            page = await ctx.firecrawl.scrape_url(url, only_main_content=True)
            if page.markdown.strip():
                return url, page
        except FirecrawlError as e:
            log.debug(f"discover: {url} not reachable: {e}")
            continue
    return None, None


def _write_evidence(
    evidence_dir: Path,
    current_page: ScrapedPage,
    snapshots: list,
    tiers: list[PricingTier],
) -> None:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    # Clean up stale wayback_*.md files from prior runs so the directory
    # faithfully reflects this run's snapshots.
    for stale in evidence_dir.glob("wayback_*.md"):
        stale.unlink()
    (evidence_dir / "current.md").write_text(current_page.markdown, encoding="utf-8")
    (evidence_dir / "current.html").write_text(current_page.html, encoding="utf-8")
    (evidence_dir / "extracted_tiers.json").write_text(
        json.dumps([t.model_dump() for t in tiers], indent=2),
        encoding="utf-8",
    )
    for s in snapshots:
        ts = s.timestamp.strftime("%Y%m%d")
        (evidence_dir / f"wayback_{ts}.md").write_text(s.markdown, encoding="utf-8")


async def collect(ctx: CollectorContext) -> PricingPackagingData:
    now = datetime.now(UTC)
    pricing_url, current_page = await _discover_pricing_url(ctx)
    if pricing_url is None or current_page is None:
        return PricingPackagingData(
            has_public_pricing=False,
            is_contact_us_gated=True,
            current_pricing_url=None,
            findings=[Finding(
                text="No public pricing page found at /pricing, /plans, or /pricing/. "
                     "Pricing motion appears contact-sales gated.",
                source=SourceCitation(url=f"https://{ctx.domain}", timestamp=now),
            )],
        )

    current_tiers = _extract_tiers(current_page.markdown)
    is_gated = _detect_contact_us(current_page.markdown) and not current_tiers
    has_public_pricing = bool(current_tiers)

    # Wayback snapshots
    snapshots = []
    try:
        snapshots = await ctx.wayback.snapshots(pricing_url, interval_months=6, span_months=18)
    except WaybackError as e:
        log.warning("wayback snapshots failed for %s: %s", pricing_url, e)

    historical: list[HistoricalSnapshot] = []
    detected_changes: list[PricingChange] = []
    for s in snapshots:
        s_tiers = _extract_tiers(s.markdown)
        historical.append(HistoricalSnapshot(
            timestamp=s.timestamp, archive_url=s.archive_url, tiers=s_tiers,
        ))

    # Diff: pair each consecutive (older -> newer) starting from the oldest
    sorted_history = sorted(historical, key=lambda h: h.timestamp)
    series = [*sorted_history, HistoricalSnapshot(
        timestamp=now, archive_url=pricing_url, tiers=current_tiers,
    )]
    for i in range(len(series) - 1):
        observed = series[i + 1].timestamp.date()
        detected_changes.extend(
            _diff_tier_lists(series[i].tiers, series[i + 1].tiers, observed_at=observed)
        )

    # Evidence
    _write_evidence(ctx.evidence_dir / NAME, current_page, snapshots, current_tiers)

    findings: list[Finding] = []
    if has_public_pricing:
        findings.append(Finding(
            text=f"Public pricing page at {pricing_url} with {len(current_tiers)} tier(s).",
            source=SourceCitation(
                url=pricing_url,
                timestamp=now,
                evidence_path=str(
                    (ctx.evidence_dir / NAME / "current.md").relative_to(ctx.evidence_dir.parent)
                ),
            ),
        ))
    elif is_gated:
        findings.append(Finding(
            text=f"Pricing page exists at {pricing_url} but appears contact-sales gated.",
            source=SourceCitation(url=pricing_url, timestamp=now),
        ))

    sources = [SourceCitation(
        url=pricing_url,
        timestamp=now,
        evidence_path=str(
            (ctx.evidence_dir / NAME / "current.md").relative_to(ctx.evidence_dir.parent)
        ),
    )]
    for s in snapshots:
        sources.append(SourceCitation(
            url=s.archive_url,
            timestamp=s.timestamp,
            evidence_path=str(
                (ctx.evidence_dir / NAME / f"wayback_{s.timestamp.strftime('%Y%m%d')}.md").relative_to(
                    ctx.evidence_dir.parent
                )
            ),
        ))

    discovery_questions: list[str] = []
    if not has_public_pricing:
        discovery_questions.append(
            "What's the rationale for not publishing pricing? Have you tested public pricing in the past?"
        )
    if any(c.kind == "price_increased" for c in detected_changes):
        discovery_questions.append(
            "We observed a price increase in the last 18 months. What was the trigger? "
            "How did existing customers respond?"
        )

    gaps: list[str] = []
    if has_public_pricing and not detected_changes:
        gaps.append("Pricing has been static for the observable window; consider testing willingness-to-pay.")

    return PricingPackagingData(
        has_public_pricing=has_public_pricing,
        is_contact_us_gated=is_gated,
        current_pricing_url=pricing_url,
        current_tiers=current_tiers,
        historical_snapshots=historical,
        detected_changes=detected_changes,
        findings=findings,
        gaps=gaps,
        discovery_questions=discovery_questions,
        sources=sources,
    )
