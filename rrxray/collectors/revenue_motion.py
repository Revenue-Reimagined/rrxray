"""revenue_motion collector: careers page + LinkedIn job + employee count signals."""
from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from urllib.parse import urljoin

from rrxray.collectors._revenue_motion_catalog import ATS_PATTERNS, ROLE_KEYWORDS
from rrxray.schemas._shared import Finding, SourceCitation
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


async def _linkedin_search_jobs(firecrawl, domain: str) -> list[JobPosting]:
    """Search Google for LinkedIn job postings mentioning the domain.

    Best-effort. Returns empty list on search failure or no results.
    """
    from rrxray.services.firecrawl_client import FirecrawlError

    query = f'site:linkedin.com/jobs "{domain}"'
    try:
        results = await firecrawl.search(query, limit=10)
    except FirecrawlError as e:
        log.warning("LinkedIn jobs search failed for %s: %s", domain, e)
        return []

    roles: list[JobPosting] = []
    for r in results:
        title = r.title.strip()
        if not title:
            continue
        category, matched = _categorize_title(title)
        roles.append(JobPosting(
            title=title,
            category=category,  # type: ignore[arg-type]
            url=r.url or None,
            source="linkedin",
            matched_keyword=matched,
        ))
    return roles


_EMPLOYEE_COUNT_RE = re.compile(r"([\d,]+)\s+employees", re.IGNORECASE)


async def _linkedin_employee_count(firecrawl, domain: str) -> int | None:
    """Search Google for the LinkedIn company snippet and parse '<N> employees'.

    Returns int or None. Best-effort.
    """
    from rrxray.services.firecrawl_client import FirecrawlError

    query = f'"{domain}" employees site:linkedin.com/company'
    try:
        results = await firecrawl.search(query, limit=3)
    except FirecrawlError as e:
        log.warning("LinkedIn employee count search failed for %s: %s", domain, e)
        return None

    for r in results:
        haystack = " ".join([r.title, r.description])
        m = _EMPLOYEE_COUNT_RE.search(haystack)
        if m:
            try:
                return int(m.group(1).replace(",", ""))
            except ValueError:
                continue
    return None


def _compute_role_metrics(
    roles: list[JobPosting],
) -> tuple[dict[str, int], float | None]:
    """Aggregate role counts per category and compute AE/SDR ratio (None if either is 0)."""
    counts: dict[str, int] = {}
    for r in roles:
        counts[r.category] = counts.get(r.category, 0) + 1
    ae = counts.get("ae", 0)
    sdr = counts.get("sdr", 0)
    ratio: float | None = ae / sdr if (ae > 0 and sdr > 0) else None
    return counts, ratio


def _emit_findings(
    domain: str,
    careers_url: str | None,
    roles: list[JobPosting],
    counts: dict[str, int],
    ratio: float | None,
    employee_count: int | None,
    ats_platform: str | None,
) -> tuple[list[Finding], list[str], list[str]]:
    """Rule-based findings/gaps/questions. No LLM."""
    now = datetime.now(UTC)
    source_url = careers_url or f"https://{domain}"
    findings: list[Finding] = []
    gaps: list[str] = []
    questions: list[str] = []

    if not roles:
        findings.append(Finding(
            text=(
                f"No careers/jobs page or open roles discovered at standard paths "
                f"on {domain}. Either no current hiring activity or careers content "
                f"lives on a non-standard path or external surface."
            ),
            source=SourceCitation(url=source_url, timestamp=now),
        ))
        questions.append(
            "We did not find a public careers page or open roles. "
            "Are you actively hiring, and if so, where do you currently post roles? "
            "(Internal referral, executive recruiter, ATS-only, etc.)"
        )
        return findings, gaps, questions

    ae = counts.get("ae", 0)
    sdr = counts.get("sdr", 0)
    sales_leadership = counts.get("sales_leadership", 0)
    csm = counts.get("csm", 0)
    revops = counts.get("revops", 0)

    if ratio is not None and ratio >= 4.0:
        findings.append(Finding(
            text=(
                f"AE-to-SDR ratio is {ratio:.1f} ({ae} AEs hiring, {sdr} SDRs). "
                f"Outbound coverage looks under-resourced relative to AE capacity; "
                f"either pipeline is AE-self-sourced, founder-sourced, or pulled from "
                f"inbound demand alone."
            ),
            source=SourceCitation(url=source_url, timestamp=now),
        ))

    if ae > 0 and sdr == 0:
        gaps.append(
            f"Hiring {ae} AE{'s' if ae > 1 else ''} with zero SDRs in the open-role list. "
            "Top-of-funnel is either founder-led, AE-self-sourced, or assumed to come "
            "from inbound demand-gen — confirm which."
        )
        questions.append(
            "You're hiring AEs with no SDRs visible in the open requisitions. "
            "How are AEs sourcing pipeline today: outbound themselves, marketing-fed, "
            "or founder hand-offs?"
        )

    if sales_leadership > 0:
        findings.append(Finding(
            text=(
                f"Sales leadership role posted ({sales_leadership} open). The motion "
                "may be in transition — either the previous leader exited recently, "
                "or the company is scaling past founder-led sales."
            ),
            source=SourceCitation(url=source_url, timestamp=now),
        ))
        questions.append(
            "You're hiring sales leadership. What does the next 12 months look like "
            "for this role: rebuilding a function, scaling an existing one, or "
            "transitioning from founder-led sales?"
        )

    founding_titles = [
        r for r in roles
        if any(token in r.title.lower() for token in ["founding", "first sales", "first ae"])
    ]
    if founding_titles:
        findings.append(Finding(
            text=(
                f"'{founding_titles[0].title}' role posted — motion is transitioning "
                "from founder-led sales to a first dedicated GTM hire."
            ),
            source=SourceCitation(url=source_url, timestamp=now),
        ))

    if counts.get("marketing_leadership", 0) > 0 and counts.get("marketing_ops", 0) == 0:
        gaps.append(
            "Marketing leadership posted but no marketing-ops role visible. "
            "Building a demand-gen function from scratch — pipeline visibility "
            "and attribution will be a question."
        )

    if revops == 0 and (ae > 0 or sdr > 0):
        gaps.append(
            "Hiring revenue-facing roles with no Revenue Operations role visible. "
            "Pipeline data, comp plans, and forecasting may be ad hoc or owned by sales leadership."
        )

    if csm == 0 and ae > 0:
        gaps.append(
            "AEs hiring with no Customer Success role posted. Post-sale ownership "
            "may be unclear — either AEs hold accounts, or CS is centralized and not currently expanding."
        )

    if ats_platform:
        findings.append(Finding(
            text=(
                f"Recruiting via {ats_platform}. The careers page redirects there "
                f"and that's the source of truth for open roles."
            ),
            source=SourceCitation(url=source_url, timestamp=now),
        ))

    if employee_count is not None:
        findings.append(Finding(
            text=(
                f"LinkedIn shows ~{employee_count} employees. "
                f"Open-role count: {len(roles)}. Hiring rate "
                f"({len(roles) / employee_count * 100:.1f}% of headcount) "
                f"signals {'aggressive growth' if len(roles) / employee_count > 0.05 else 'measured pace'}."
            ),
            source=SourceCitation(
                url="https://www.linkedin.com/company/" + domain.split(".")[0],
                timestamp=now,
            ),
        ))

    return findings, gaps, questions
