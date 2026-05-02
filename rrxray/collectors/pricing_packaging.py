"""pricing_packaging collector: scrapes current pricing page + Wayback snapshots."""
from __future__ import annotations

import logging
import re

from rrxray.context import CollectorContext
from rrxray.schemas.pricing_packaging import PricingPackagingData, PricingTier
from rrxray.services.firecrawl_client import FirecrawlError, ScrapedPage

NAME = "pricing_packaging"
log = logging.getLogger(f"rrxray.collectors.{NAME}")

CANDIDATE_PATHS = ["/pricing", "/plans", "/pricing/"]

_PRICE_RE = re.compile(r"\$([\d,]+(?:\.\d{1,2})?)")
_TIER_HEADING_RE = re.compile(r"^#{2,3}\s+(.+?)\s*$", re.MULTILINE)
_CADENCE_HINTS = ["per month", "/month", "per year", "/year", "per user", "per seat", "/mo", "/yr"]
_CONTACT_HINTS = ["contact sales", "contact us", "request a demo", "request demo", "custom quote", "talk to sales"]


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
        name = h.group(1).split("—")[0].split(":")[0].strip()
        price = f"${price_m.group(1)}" if price_m else ""
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


async def collect(ctx: CollectorContext) -> PricingPackagingData:
    pricing_url, current_page = await _discover_pricing_url(ctx)
    if pricing_url is None or current_page is None:
        return PricingPackagingData(
            has_public_pricing=False,
            is_contact_us_gated=True,
            current_pricing_url=None,
        )

    current_tiers = _extract_tiers(current_page.markdown)
    is_gated = _detect_contact_us(current_page.markdown) and not current_tiers

    return PricingPackagingData(
        has_public_pricing=bool(current_tiers) or not is_gated,
        is_contact_us_gated=is_gated,
        current_pricing_url=pricing_url,
        current_tiers=current_tiers,
    )
