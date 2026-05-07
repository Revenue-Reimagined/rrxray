"""revenue_motion collector: careers page + LinkedIn job + employee count signals."""
from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from rrxray.collectors._revenue_motion_catalog import ATS_PATTERNS

if TYPE_CHECKING:
    from rrxray.context import CollectorContext

NAME = "revenue_motion"
log = logging.getLogger(f"rrxray.collectors.{NAME}")

CANDIDATE_PATHS = ["/careers", "/jobs", "/work-with-us", "/join-us"]


async def _discover_careers_url(ctx: CollectorContext):
    """Try standard careers paths. Return (url, ScrapedPage) or (None, None)."""
    from rrxray.services.firecrawl_client import FirecrawlError
    base = f"https://{ctx.domain}"
    for path in CANDIDATE_PATHS:
        url = base + path
        try:
            page = await ctx.firecrawl.scrape_url(url, only_main_content=False)
            html = page.html or ""
            if html.strip() and len(html) > 200:
                return url, page
        except FirecrawlError as e:
            log.debug("careers discover: %s not reachable: %s", url, e)
            continue
    return None, None


def _detect_ats(html: str) -> tuple[str | None, str | None]:
    """Scan HTML for known ATS subdomain links. Return (platform_name, full_url) or (None, None)."""
    if not html:
        return None, None
    for pattern_entry in ATS_PATTERNS:
        m = re.search(pattern_entry["url_pattern"], html, re.IGNORECASE)
        if m:
            return pattern_entry["name"], m.group(0)
    return None, None
