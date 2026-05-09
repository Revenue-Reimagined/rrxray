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
    PRESS_ACTION_QUERIES,
)
from rrxray.schemas.leadership_stability import (
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


async def collect(ctx: CollectorContext) -> LeadershipStabilityData:
    """Orchestrator. Phase 2.2 T7-T11 incrementally fills this in."""
    company = ctx.company_name or ctx.domain.split(".")[0].title()
    if ctx.extractor is None:
        return LeadershipStabilityData(
            findings=[],  # T10 will fill in graceful-degradation finding
        )

    press_results = await _search_press_releases(ctx.firecrawl, company)
    exec_changes = await _extract_exec_changes(press_results, ctx.extractor)

    # T8-T11 fill in the rest
    return LeadershipStabilityData(
        exec_changes=exec_changes,
    )
