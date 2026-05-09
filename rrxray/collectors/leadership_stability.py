"""leadership_stability collector — first Section B signal.

Surfaces exec-change history (press search), current C-suite (LinkedIn search),
and founder tenure (/about scrape with Wayback fallback). Populates the
anonymizer name registry via name_registrations on the schema; pipeline
applies side effects post-collection.

LLM is used in this collector path for press / LinkedIn snippet extraction
(see rrxray/services/extraction.py for the rule amendment rationale).
"""
from __future__ import annotations

import json
import logging
import re
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from rrxray.collectors._leadership_stability_catalog import (
    FOUNDED_YEAR_PATTERNS,
    LEADERSHIP_ROLES,
    PRESS_ACTION_QUERIES,
    RECENT_THRESHOLD_DAYS,
    ROLE_DISPLAY,
)
from rrxray.schemas._shared import Finding, SourceCitation
from rrxray.schemas.leadership_stability import (
    CurrentIncumbent,
    ExecChange,
    FounderTenure,
    LeadershipStabilityData,
    NameRegistration,
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
    company: str,
    domain: str,
) -> list[ExecChange]:
    """Per-result extraction; filter is_relevant=False; preserve URL + title.

    The target company name AND domain are both passed through so the
    extractor can disambiguate when the company name is generic (e.g.,
    "Linear" matches Linear Retail, Linear Health Sciences, etc., as well
    as the actual target Linear.app). The domain is the authoritative
    identifier.
    """
    changes: list[ExecChange] = []
    for r in results:
        extracted = await extractor.extract_exec_change(
            r.title, r.description,
            target_company=company, target_domain=domain,
        )
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
    company: str,
    domain: str,
) -> list[CurrentIncumbent]:
    """Per-result LLM extraction; dedupe by (role, name); preserve LinkedIn URL.

    For each role, walk results in order; the first relevant extraction
    becomes the incumbent for that role. Subsequent same-role-same-name
    matches are skipped (dedup). The target company name AND domain are
    both passed through so the extractor can disambiguate when the company
    name is generic; the domain is the authoritative identifier.
    """
    incumbents: list[CurrentIncumbent] = []
    seen: set[tuple[str, str]] = set()  # (role_canonical, name)

    for role_canonical, results in results_by_role.items():
        for r in results:
            extracted = await extractor.extract_linkedin_role(
                r.title, r.description, role_canonical,
                target_company=company, target_domain=domain,
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
            # Spec: top match per role. The first relevant extraction in the
            # search-result order becomes the incumbent for this role; later
            # results in the same role (which can yield distinct names) are
            # skipped. Same-name dedup across roles still happens via `seen`.
            break

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


# Synthetic URL prefix for findings not anchored to a single source URL.
# SourceCitation requires url+timestamp; collector-derived findings use this
# label-style scheme so the report renderer can group them.
_INTERNAL_SOURCE_PREFIX = "rrxray://leadership_stability/"


def _internal_source(label: str) -> SourceCitation:
    return SourceCitation(
        url=f"{_INTERNAL_SOURCE_PREFIX}{label}",
        timestamp=datetime.now(UTC),
    )


def _build_name_registrations(
    exec_changes: list[ExecChange],
    current_incumbents: list[CurrentIncumbent],
    company: str,
) -> list[NameRegistration]:
    """Build deduped name registrations.

    Press names: whitelist=True. LinkedIn-only names: whitelist=False.
    Same name in both → single record; press takes precedence (whitelist=True wins).
    """
    by_name: dict[str, NameRegistration] = {}

    # Press names first (whitelist=True)
    for change in exec_changes:
        if not change.name:
            continue
        descriptor = f"{company}'s {ROLE_DISPLAY.get(change.role_canonical, change.role_raw)}"
        by_name[change.name] = NameRegistration(
            name=change.name,
            role_descriptor=descriptor,
            whitelist=True,
        )

    # LinkedIn names — only register if not already in press (don't downgrade whitelist)
    for inc in current_incumbents:
        if not inc.name or inc.name in by_name:
            continue
        descriptor = f"{company}'s {ROLE_DISPLAY.get(inc.role_canonical, inc.role_raw)}"
        by_name[inc.name] = NameRegistration(
            name=inc.name,
            role_descriptor=descriptor,
            whitelist=False,
        )

    return list(by_name.values())


def _emit_findings(
    exec_changes: list[ExecChange],
    current_incumbents: list[CurrentIncumbent],
    founder_tenure: FounderTenure,
) -> tuple[list[Finding], list[str], list[str]]:
    """Rule-based findings, gaps, and discovery questions per spec rules table."""
    findings: list[Finding] = []
    gaps: list[str] = []
    questions: list[str] = []
    now = datetime.now(UTC)
    today = now.date()

    # Rule 1: ≥2 changes in same seat in past 18 months → seat-turnover finding
    seat_counts: dict[str, int] = {}
    for c in exec_changes:
        seat_counts[c.role_canonical] = seat_counts.get(c.role_canonical, 0) + 1
    for role, count in seat_counts.items():
        if count >= 2:
            display = ROLE_DISPLAY.get(role, role)
            # Anchor to the most recent press URL for that role, if available.
            # Sort by occurred_at descending; treat None as oldest (date.min)
            # so dated changes win the anchor over undated ones.
            same_role = sorted(
                (c for c in exec_changes if c.role_canonical == role),
                key=lambda c: c.occurred_at or date.min,
                reverse=True,
            )
            anchor = same_role[0]
            findings.append(Finding(
                text=(
                    f"{display} seat has turned over {count} times in the past "
                    f"18 months → buyer-side ownership of the conversation may "
                    f"shift mid-cycle."
                ),
                source=SourceCitation(url=anchor.press_url, timestamp=now),
            ))

    # Rule 2: 1 change in seat ≤RECENT_THRESHOLD_DAYS → in-transition finding
    recent_role_changes: dict[str, ExecChange] = {}
    for c in exec_changes:
        if c.occurred_at is None:
            continue
        days_ago = (today - c.occurred_at).days
        if days_ago <= RECENT_THRESHOLD_DAYS:
            # Only flag once per role; latest change wins
            existing = recent_role_changes.get(c.role_canonical)
            if existing is None or (
                existing.occurred_at and c.occurred_at > existing.occurred_at
            ):
                recent_role_changes[c.role_canonical] = c
    for role, change in recent_role_changes.items():
        if seat_counts.get(role, 0) >= 2:
            continue  # already covered by Rule 1
        display = ROLE_DISPLAY.get(role, role)
        days_ago = (today - change.occurred_at).days  # type: ignore[operator]
        months_in_role = max(1, days_ago // 30)
        findings.append(Finding(
            text=(
                f"{display} is in transition; current incumbent in seat "
                f"~{months_in_role} months → motion direction likely still "
                f"being defined."
            ),
            source=SourceCitation(url=change.press_url, timestamp=now),
        ))

    # Rule 3: concurrent recent revenue + marketing leadership change
    revenue_recent = any(
        r in recent_role_changes for r in ("cro", "vp_sales", "vp_revenue")
    )
    marketing_recent = any(
        r in recent_role_changes for r in ("cmo", "vp_marketing")
    )
    if revenue_recent and marketing_recent:
        findings.append(Finding(
            text=(
                "Both revenue and marketing leadership turned over within "
                "9 months → top-of-funnel and pipeline motion both being "
                "redesigned simultaneously."
            ),
            source=_internal_source("cross_function"),
        ))

    # Rule 4: founder ≥7 years AND current CEO incumbent matches founder name
    founder_names = {i.name for i in current_incumbents if i.role_canonical == "founder"}
    ceo_incumbent_names = {i.name for i in current_incumbents if i.role_canonical == "ceo"}
    founder_in_ceo_seat = bool(founder_names & ceo_incumbent_names)
    tenure_years = (
        today.year - founder_tenure.inferred_year if founder_tenure.inferred_year else None
    )
    if founder_in_ceo_seat and tenure_years is not None and tenure_years >= 7:
        findings.append(Finding(
            text=(
                f"Founder-led for {tenure_years} years → decision authority "
                f"concentrated; commitment risk on multi-quarter buying "
                f"decisions is lower than at professionally-led peers."
            ),
            source=_internal_source("founder_tenure"),
        ))

    # Rule 5: founder tenure unknown AND zero current incumbents
    if founder_tenure.source == "unknown" and not current_incumbents:
        findings.append(Finding(
            text=(
                "Leadership signal not recovered from public sources → "
                "discovery should establish leadership stability and recent "
                "change directly."
            ),
            source=_internal_source("signal_loss"),
        ))
        questions.append(
            "Who is your current CRO and CMO? How long have they been in seat?"
        )

    # Rule 6: incumbents present AND zero exec changes
    if current_incumbents and not exec_changes:
        findings.append(Finding(
            text=(
                "No public exec announcements in past 18 months → leadership "
                "stability inferred (within the limits of public-record "
                "visibility)."
            ),
            source=_internal_source("no_press_signal"),
        ))

    return findings, gaps, questions


def _write_evidence(
    evidence_dir: Path,
    press_results: list[SearchResult],
    linkedin_results_by_role: dict[str, list[SearchResult]],
    exec_changes: list[ExecChange],
    current_incumbents: list[CurrentIncumbent],
) -> None:
    """Write evidence files under evidence_dir/leadership_stability/."""
    out_dir = evidence_dir / "leadership_stability"
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "press_search.json").write_text(
        json.dumps([r.model_dump() for r in press_results], indent=2)
    )
    (out_dir / "linkedin_search.json").write_text(
        json.dumps(
            {
                role: [r.model_dump() for r in results]
                for role, results in linkedin_results_by_role.items()
            },
            indent=2,
        )
    )
    (out_dir / "exec_changes.json").write_text(
        json.dumps([c.model_dump(mode="json") for c in exec_changes], indent=2)
    )
    (out_dir / "current_incumbents.json").write_text(
        json.dumps([i.model_dump() for i in current_incumbents], indent=2)
    )


async def collect(ctx: CollectorContext) -> LeadershipStabilityData:
    """Orchestrator. Runs press + LinkedIn + founder paths in sequence;
    each handles its own errors gracefully. Returns a fully-validated
    LeadershipStabilityData with name_registrations populated for the
    pipeline's anonymizer registration loop.
    """
    company = ctx.company_name or ctx.domain.split(".")[0].title()

    if ctx.extractor is None:
        log.warning("leadership_stability: no extractor on context; returning empty data")
        return LeadershipStabilityData(
            findings=[Finding(
                text="Leadership stability collector skipped: no extractor configured.",
                source=_internal_source("config"),
            )],
        )

    # Press path
    press_results = await _search_press_releases(ctx.firecrawl, company)
    exec_changes = await _extract_exec_changes(
        press_results, ctx.extractor, company, ctx.domain,
    )

    # LinkedIn path
    linkedin_results_by_role = await _search_linkedin_incumbents(ctx.firecrawl, company)
    current_incumbents = await _extract_current_incumbents(
        linkedin_results_by_role, ctx.extractor, company, ctx.domain,
    )

    # Founder tenure path
    founder_tenure = await _infer_founder_tenure(ctx.firecrawl, ctx.wayback, ctx.domain)

    # Build derived data
    name_registrations = _build_name_registrations(
        exec_changes, current_incumbents, company,
    )
    findings, gaps, questions = _emit_findings(
        exec_changes, current_incumbents, founder_tenure,
    )

    # Write evidence
    try:
        _write_evidence(
            ctx.evidence_dir,
            press_results,
            linkedin_results_by_role,
            exec_changes,
            current_incumbents,
        )
    except OSError as e:
        log.warning("evidence write failed: %s", e)

    return LeadershipStabilityData(
        exec_changes=exec_changes,
        current_incumbents=current_incumbents,
        founder_tenure=founder_tenure,
        name_registrations=name_registrations,
        findings=findings,
        gaps=gaps,
        discovery_questions=questions,
    )
