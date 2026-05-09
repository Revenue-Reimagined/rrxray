"""leadership_stability collector — first Section B signal.

Surfaces exec-change history (press search), current C-suite (LinkedIn search),
and founder tenure (/about scrape with Wayback fallback). Populates the
anonymizer name registry via name_registrations on the schema; pipeline
applies side effects post-collection.

LLM is used in this collector path for press / LinkedIn snippet extraction
(see rrxray/services/extraction.py for the rule amendment rationale).
"""
from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from rrxray.collectors._leadership_stability_catalog import (
    FOUNDED_YEAR_PATTERNS,
    LEADERSHIP_ROLES,
    PRESS_ACTION_QUERIES,
)
from rrxray.schemas.leadership_stability import (
    CurrentIncumbent,
    ExecChange,
    FounderTenure,
    LeadershipStabilityData,
)

if TYPE_CHECKING:
    from rrxray.context import CollectorContext
    from rrxray.services.extraction import GeminiFlashExtractor, HaikuExtractor
    from rrxray.services.firecrawl_client import FirecrawlClient, SearchResult
    from rrxray.services.wayback_client import WaybackClient


NAME = "leadership_stability"
log = logging.getLogger(f"rrxray.collectors.{NAME}")


async def _search_press_releases(
    firecrawl: FirecrawlClient, company: str,
) -> list[SearchResult]:
    """Run 3 per-action queries against Firecrawl search; dedupe by URL.

    Each action-query failure is logged and skipped; remaining queries continue.
    Returns the deduped union of all successful queries.
    """
    from rrxray.services.firecrawl_client import FirecrawlError

    seen_urls: set[str] = set()
    all_results: list[SearchResult] = []

    for action_label, action_keywords in PRESS_ACTION_QUERIES:
        query = f'"{company}" ({action_keywords}) (CEO OR CRO OR "Chief Revenue" OR "VP Sales" OR "VP of Sales" OR CMO OR "Chief Marketing" OR "VP Marketing" OR "VP of Marketing" OR Founder)'
        try:
            results = await firecrawl.search(query, limit=10)
        except FirecrawlError as e:
            log.warning("press search failed for action=%s: %s", action_label, e)
            continue

        for r in results:
            if r.url in seen_urls:
                continue
            seen_urls.add(r.url)
            all_results.append(r)

    return all_results


async def _extract_exec_changes(
    results: list[SearchResult],
    extractor: HaikuExtractor | GeminiFlashExtractor,
) -> list[ExecChange]:
    """Per-result extraction; filter is_relevant=False; preserve URL + title."""
    changes: list[ExecChange] = []
    for r in results:
        extracted = await extractor.extract_exec_change(r.title, r.description)
        if extracted is None:
            continue
        changes.append(ExecChange(
            name=extracted.name,
            role_canonical=extracted.role_canonical,
            role_raw=extracted.role_raw,
            action=extracted.action,
            occurred_at=None,  # Phase 2.2-deep may extract from snippet metadata
            press_url=r.url,
            press_title=r.title,
        ))
    return changes


async def _search_linkedin_incumbents(
    firecrawl: FirecrawlClient, company: str,
) -> dict[str, list[SearchResult]]:
    """Run 7 per-role LinkedIn /in/ searches; group results by canonical role.

    Per-role search failures are logged and yield empty list for that role
    (not missing-key); other roles continue.
    """
    from rrxray.services.firecrawl_client import FirecrawlError

    results_by_role: dict[str, list[SearchResult]] = {}

    for canonical, role_query in LEADERSHIP_ROLES:
        query = f'site:linkedin.com/in "{company}" {role_query}'
        try:
            results = await firecrawl.search(query, limit=3)
        except FirecrawlError as e:
            log.warning("linkedin search failed for role=%s: %s", canonical, e)
            results_by_role[canonical] = []
            continue
        results_by_role[canonical] = list(results)

    return results_by_role


def _confidence_for_linkedin_url(url: str) -> str:
    """LinkedIn /in/ profile URLs are 'high' confidence; /posts/ URLs are 'low'."""
    if "/in/" in url:
        return "high"
    return "low"


async def _extract_current_incumbents(
    results_by_role: dict[str, list[SearchResult]],
    extractor: HaikuExtractor | GeminiFlashExtractor,
) -> list[CurrentIncumbent]:
    """Per-result LLM extraction; dedupe by (role, name); preserve LinkedIn URL.

    For each role, walk results in order; the first relevant extraction
    becomes the incumbent for that role. Subsequent same-role-same-name
    matches are skipped (dedup).
    """
    incumbents: list[CurrentIncumbent] = []
    seen: set[tuple[str, str]] = set()  # (role_canonical, name)

    for role_canonical, results in results_by_role.items():
        for r in results:
            extracted = await extractor.extract_linkedin_role(
                r.title, r.description, role_canonical,
            )
            if extracted is None:
                continue
            key = (extracted.role_canonical, extracted.name)
            if key in seen:
                continue
            seen.add(key)
            incumbents.append(CurrentIncumbent(
                name=extracted.name,
                role_canonical=extracted.role_canonical,
                role_raw=extracted.role_raw,
                linkedin_url=r.url,
                confidence=_confidence_for_linkedin_url(r.url),  # type: ignore[arg-type]
            ))

    return incumbents


def _parse_founding_year_from_about(html: str) -> tuple[int, str] | None:
    """Returns (year, raw_evidence_quote) on first match; None if no pattern matches."""
    text = re.sub(r"<[^>]+>", " ", html)  # strip tags crudely
    for pattern in FOUNDED_YEAR_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            year = int(m.group(1))
            # Capture a small surrounding quote for evidence
            start = max(0, m.start() - 20)
            end = min(len(text), m.end() + 20)
            quote = text[start:end].strip()
            return year, quote
    return None


async def _infer_founder_tenure(
    firecrawl: FirecrawlClient,
    wayback: WaybackClient,
    domain: str,
) -> FounderTenure:
    """F1: scrape /about, regex for founding year. F2 fallback: Wayback oldest snapshot.

    Returns FounderTenure(source='unknown') if both fail.
    """
    from rrxray.services.firecrawl_client import FirecrawlError

    # F1: try /about
    about_url = f"https://{domain}/about"
    try:
        page = await firecrawl.scrape_url(about_url, only_main_content=True)
    except FirecrawlError as e:
        log.warning("about page scrape failed: %s", e)
        page = None

    if page is not None:
        parsed = _parse_founding_year_from_about(page.html or page.markdown or "")
        if parsed is not None:
            year, evidence = parsed
            return FounderTenure(
                inferred_year=year,
                source="about_page",
                raw_evidence=evidence,
            )

    # F2: Wayback fallback — oldest reachable homepage snapshot
    try:
        snapshots = await wayback.snapshots(
            f"https://{domain}",
            interval_months=12,
            span_months=120,  # 10 years
        )
    except Exception as e:  # WaybackError or transient
        log.warning("wayback snapshots failed: %s", e)
        snapshots = []

    if snapshots:
        oldest = min(snapshots, key=lambda s: s.timestamp)
        return FounderTenure(
            inferred_year=oldest.timestamp.year,
            source="wayback_homepage",
            raw_evidence=f"Oldest reachable Wayback snapshot: {oldest.archive_url}",
        )

    return FounderTenure(source="unknown")


async def collect(ctx: CollectorContext) -> LeadershipStabilityData:
    """Orchestrator. Phase 2.2 T7-T11 incrementally fills this in."""
    company = ctx.company_name or ctx.domain.split(".")[0].title()
    if ctx.extractor is None:
        return LeadershipStabilityData(
            findings=[],  # T10 will fill in graceful-degradation finding
        )

    press_results = await _search_press_releases(ctx.firecrawl, company)
    exec_changes = await _extract_exec_changes(press_results, ctx.extractor)

    linkedin_results = await _search_linkedin_incumbents(ctx.firecrawl, company)
    current_incumbents = await _extract_current_incumbents(linkedin_results, ctx.extractor)

    founder_tenure = await _infer_founder_tenure(ctx.firecrawl, ctx.wayback, ctx.domain)

    # T10-T11 fill in the rest
    return LeadershipStabilityData(
        exec_changes=exec_changes,
        current_incumbents=current_incumbents,
        founder_tenure=founder_tenure,
    )
