"""pricing_packaging collector: scrapes current pricing page + Wayback snapshots."""
from __future__ import annotations

import logging

from rrxray.context import CollectorContext
from rrxray.schemas.pricing_packaging import PricingPackagingData
from rrxray.services.firecrawl_client import FirecrawlError

NAME = "pricing_packaging"
log = logging.getLogger(f"rrxray.collectors.{NAME}")

CANDIDATE_PATHS = ["/pricing", "/plans", "/pricing/"]


async def _discover_pricing_url(ctx: CollectorContext) -> tuple[str | None, dict | None]:
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
    pricing_url, _current_page = await _discover_pricing_url(ctx)
    if pricing_url is None:
        return PricingPackagingData(
            has_public_pricing=False,
            is_contact_us_gated=True,
            current_pricing_url=None,
        )

    return PricingPackagingData(
        has_public_pricing=True,
        is_contact_us_gated=False,
        current_pricing_url=pricing_url,
    )
