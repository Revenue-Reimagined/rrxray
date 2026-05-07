"""revenue_motion collector: careers page + LinkedIn job + employee count signals."""
from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING
from urllib.parse import urljoin

from rrxray.collectors._revenue_motion_catalog import ATS_PATTERNS, ROLE_KEYWORDS
from rrxray.schemas.revenue_motion import JobPosting

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


# Compile keyword patterns once at module load.
def _compile_role_patterns() -> list[tuple[str, str, re.Pattern]]:
    compiled = []
    for entry in ROLE_KEYWORDS:
        for kw in entry["keywords"]:
            # Word-boundary match for short acronyms to avoid false matches.
            if len(kw) <= 4 and kw.isupper():
                pattern = re.compile(rf"\b{re.escape(kw)}\b", re.IGNORECASE)
            else:
                pattern = re.compile(re.escape(kw), re.IGNORECASE)
            compiled.append((entry["category"], kw, pattern))
    return compiled


_ROLE_PATTERNS = _compile_role_patterns()


def _categorize_title(title: str) -> tuple[str, str | None]:
    """Categorize a job title via the keyword catalog.

    Returns (category, matched_keyword). Falls back to ('other', None).
    """
    for category, keyword, pattern in _ROLE_PATTERNS:
        if pattern.search(title):
            return category, keyword
    return "other", None


_LINK_RE = re.compile(
    r'<a[^>]*\bhref=["\']([^"\']+)["\'][^>]*>([^<]+)</a>',
    re.IGNORECASE,
)


def _extract_roles(html: str, source: str, base_url: str) -> list[JobPosting]:
    """Extract job postings from HTML anchor tags, categorized via the role catalog."""
    if not html:
        return []
    roles: list[JobPosting] = []
    seen_titles: set[str] = set()
    for m in _LINK_RE.finditer(html):
        href = m.group(1).strip()
        title = m.group(2).strip()
        if not title or len(title) > 200:
            continue
        if title in seen_titles:
            continue
        seen_titles.add(title)
        category, matched = _categorize_title(title)
        full_url = urljoin(base_url, href) if href and not href.startswith("#") else None
        roles.append(JobPosting(
            title=title,
            category=category,  # type: ignore[arg-type]
            url=full_url,
            source=source,  # type: ignore[arg-type]
            matched_keyword=matched,
        ))
    return roles
