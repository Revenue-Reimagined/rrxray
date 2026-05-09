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
from typing import TYPE_CHECKING

from rrxray.collectors._leadership_stability_catalog import (
    LEADERSHIP_ROLES,
    PRESS_ACTION_QUERIES,
)
from rrxray.schemas.leadership_stability import (
    CurrentIncumbent,
    ExecChange,
    LeadershipStabilityData,
)

if TYPE_CHECKING:
    from rrxray.context import CollectorContext
    from rrxray.services.extraction import GeminiFlashExtractor, HaikuExtractor
    from rrxray.services.firecrawl_client import FirecrawlClient, SearchResult


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

    # T9-T11 fill in the rest
    return LeadershipStabilityData(
        exec_changes=exec_changes,
        current_incumbents=current_incumbents,
    )
