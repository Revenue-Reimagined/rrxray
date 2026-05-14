"""content_demand collector: blog cadence + post mix + lead magnets + podcast + newsletter."""
# ruff: noqa: I001
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


import re  # noqa: E402
from urllib.parse import urljoin  # noqa: E402

from rrxray.schemas.content_demand import BlogPost  # noqa: E402


_BLOG_LINK_RE = re.compile(
    r'<a[^>]*\bhref=["\']([^"\']+)["\'][^>]*>([^<]+)</a>',
    re.IGNORECASE,
)

# Match <time datetime="2026-04-15"> or <time datetime="2026-04-15T10:00:00Z">
_TIME_DATETIME_RE = re.compile(
    r'<time[^>]*\bdatetime=["\'](\d{4}-\d{2}-\d{2})[^"\']*["\']',
    re.IGNORECASE,
)

# Fallback: match "Month DD, YYYY" or "YYYY-MM-DD" in nearby text
_DATE_TEXT_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2})|"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}",
    re.IGNORECASE,
)

_AUTHOR_RE = re.compile(
    r'(?:class=["\'][^"\']*author[^"\']*["\']|>By\s+)([^<]+)',
    re.IGNORECASE,
)


def _parse_blog_posts(html: str, base_url: str) -> list[BlogPost]:
    """Extract up to 15 blog posts from HTML.

    Anchor tags are the primary signal. Dates come from a nearby <time
    datetime=...> attribute (preferred) or any "YYYY-MM-DD" / "Month DD, YYYY"
    substring within the surrounding chunk. Author extraction is best-effort.

    Returns first 15 in document order.
    """
    if not html:
        return []

    posts: list[BlogPost] = []
    seen_titles: set[str] = set()

    # Split into rough per-post chunks by anchor positions so we can correlate
    # nearby <time> / author tags with the link above them.
    matches = list(_BLOG_LINK_RE.finditer(html))
    for i, m in enumerate(matches):
        href = m.group(1).strip()
        title = m.group(2).strip()
        if not title or len(title) > 250:
            continue
        # Skip obvious nav links
        if title.lower() in {"home", "about", "contact", "blog", "insights", "next", "previous"}:
            continue
        if title in seen_titles:
            continue
        seen_titles.add(title)

        # Chunk: from this anchor to the next one (or end of html), used to
        # find date / author near this post.
        chunk_start = m.end()
        chunk_end = matches[i + 1].start() if i + 1 < len(matches) else min(len(html), chunk_start + 1000)
        chunk = html[chunk_start:chunk_end]

        # Date: prefer <time datetime="..."> attribute
        published_date: str | None = None
        time_m = _TIME_DATETIME_RE.search(chunk)
        if time_m:
            published_date = time_m.group(1)
        else:
            date_m = _DATE_TEXT_RE.search(chunk)
            if date_m:
                published_date = date_m.group(0)

        # Author: best-effort
        author: str | None = None
        author_m = _AUTHOR_RE.search(chunk)
        if author_m:
            author = author_m.group(1).strip()
            if author.lower().startswith("by "):
                author = author[3:].strip()
            if len(author) > 80:
                author = None

        full_url = urljoin(base_url, href) if href and not href.startswith("#") else None
        posts.append(BlogPost(
            title=title,
            url=full_url,
            author=author,
            published_date=published_date,
            category="other",  # categorization happens later via _categorize_post
            matched_keyword=None,
        ))

        if len(posts) >= 15:
            break

    return posts


from rrxray.collectors._content_demand_catalog import CONTENT_KEYWORDS  # noqa: E402


# Numeric-prefix SEO listicle pattern: "5 ways", "12 tips", "7 mistakes", etc.
_SEO_NUMERIC_RE = re.compile(
    r"^\s*\d{1,3}\s+(ways|tips|mistakes|reasons|things|tools|strategies|tactics|examples|signs|lessons)\b",
    re.IGNORECASE,
)


def _categorize_post(title: str, description: str = "") -> tuple[str, str | None]:
    """Categorize a post via the keyword catalog.

    Order-by-specificity: CONTENT_KEYWORDS is pre-ordered (SEO listicles
    first, thought leadership last as catch-all). First-match wins.

    A dedicated SEO-listicle numeric-prefix regex runs before the keyword
    catalog so "5 ways to...", "12 tips for..." etc. categorize even when the
    exact substring isn't in the catalog.

    Returns (category, matched_keyword). Falls back to ("other", None).
    """
    haystack = f"{title} {description}".lower()

    # SEO listicle numeric-prefix short-circuit
    if _SEO_NUMERIC_RE.search(title):
        return "seo_listicle", "<numeric-prefix>"

    for entry in CONTENT_KEYWORDS:
        for kw in entry["keywords"]:
            if kw.lower() in haystack:
                return entry["category"], kw
    return "other", None
