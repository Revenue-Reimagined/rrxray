"""content_demand collector: blog cadence + post mix + lead magnets + podcast + newsletter."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rrxray.context import CollectorContext

NAME = "content_demand"
log = logging.getLogger(f"rrxray.collectors.{NAME}")

CANDIDATE_BLOG_PATHS = ["/blog", "/insights", "/resources", "/news", "/articles", "/learn"]


async def _discover_blog_url(ctx: "CollectorContext"):  # noqa: UP037
    """Try standard blog paths. Return (url, ScrapedPage) or (None, None)."""
    from rrxray.services.firecrawl_client import FirecrawlError
    base = f"https://{ctx.domain}"
    for path in CANDIDATE_BLOG_PATHS:
        url = base + path
        try:
            page = await ctx.firecrawl.scrape_url(url, only_main_content=False)
            html = page.html or ""
            if html.strip() and len(html) > 200:
                return url, page
        except FirecrawlError as e:
            log.debug("blog discover: %s not reachable: %s", url, e)
            continue
    return None, None
