"""revenue_motion collector: careers page + LinkedIn job + employee count signals."""
from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urljoin, urlparse

from rrxray.collectors._revenue_motion_catalog import ATS_PATTERNS, ROLE_KEYWORDS
from rrxray.schemas._shared import Finding, SourceCitation
from rrxray.schemas.revenue_motion import JobPosting, RevenueMotionData

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
            if html.strip() and len(html) > 50:
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

_ATS_DOMAINS = frozenset({
    "greenhouse.io", "lever.co", "workday.com", "myworkdayjobs.com",
    "ashbyhq.com", "bamboohr.com", "smartrecruiters.com", "jobvite.com",
    "icims.com", "taleo.net", "paylocity.com", "breezy.hr", "recruitee.com",
    "workable.com", "jazz.co", "applytojob.com", "rippling.com",
})


def _is_job_posting_href(href: str, base_url: str) -> bool:
    """Return True if href points to a job posting (ATS domain or sub-path of careers URL)."""
    if not href or href.startswith("#"):
        return False
    full = urljoin(base_url, href)
    parsed = urlparse(full)
    netloc = parsed.netloc.lower()
    for ats in _ATS_DOMAINS:
        if netloc == ats or netloc.endswith("." + ats):
            return True
    base_parsed = urlparse(base_url)
    if parsed.netloc == base_parsed.netloc:
        base_path = base_parsed.path.rstrip("/")
        link_path = parsed.path.rstrip("/")
        return link_path != base_path and link_path.startswith(base_path + "/")
    return False


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
        if not _is_job_posting_href(href, base_url):
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
        return findings, gaps, questions  # early return - no roles

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


def _write_evidence(
    evidence_dir: Path,
    careers_html: str,
    ats_html: str | None,
    linkedin_jobs: list,
    linkedin_employee_count: int | None,
) -> None:
    """Write raw HTML + LinkedIn search results to evidence dir."""
    evidence_dir.mkdir(parents=True, exist_ok=True)
    for stale in evidence_dir.glob("*.html"):
        stale.unlink()
    for stale in evidence_dir.glob("*.json"):
        stale.unlink()

    if careers_html:
        (evidence_dir / "careers.html").write_text(careers_html, encoding="utf-8")
    if ats_html:
        (evidence_dir / "ats.html").write_text(ats_html, encoding="utf-8")
    (evidence_dir / "linkedin_jobs.json").write_text(
        json.dumps([j.model_dump() for j in linkedin_jobs], indent=2),
        encoding="utf-8",
    )
    (evidence_dir / "linkedin_employee_count.json").write_text(
        json.dumps({"count": linkedin_employee_count}, indent=2),
        encoding="utf-8",
    )


async def collect(ctx) -> RevenueMotionData:
    """Discover careers page, scrape it (and ATS if linked), search LinkedIn, emit findings."""
    from rrxray.services.firecrawl_client import FirecrawlError

    now = datetime.now(UTC)

    # Discover careers page
    careers_url, careers_page = await _discover_careers_url(ctx)
    careers_html = (careers_page.html if careers_page else "") or ""

    # Detect ATS link in careers page HTML
    ats_platform: str | None = None
    ats_url: str | None = None
    ats_html: str | None = None
    if careers_html:
        ats_platform, ats_url = _detect_ats(careers_html)
        if ats_url and not ats_url.startswith("http"):
            ats_url = "https://" + ats_url
        if ats_url:
            try:
                ats_page = await ctx.firecrawl.scrape_url(ats_url, only_main_content=False)
                ats_html = ats_page.html or ""
            except FirecrawlError as e:
                log.warning("ATS scrape failed for %s: %s", ats_url, e)
                ats_html = None

    # Extract roles from careers page + ATS page
    base_url = f"https://{ctx.domain}"
    careers_roles = _extract_roles(careers_html, source="company_careers", base_url=base_url)
    ats_roles = _extract_roles(ats_html or "", source="ats", base_url=ats_url or base_url)
    company_roles = careers_roles + ats_roles

    # Search LinkedIn
    linkedin_roles = await _linkedin_search_jobs(ctx.firecrawl, ctx.domain)
    linkedin_employee_count = await _linkedin_employee_count(ctx.firecrawl, ctx.domain)

    # Combine all roles for metrics
    all_roles = company_roles + linkedin_roles
    role_counts, ratio = _compute_role_metrics(all_roles)

    # Findings
    findings, gaps, questions = _emit_findings(
        domain=ctx.domain,
        careers_url=careers_url,
        roles=all_roles,
        counts=role_counts,
        ratio=ratio,
        employee_count=linkedin_employee_count,
        ats_platform=ats_platform,
    )

    # Evidence
    _write_evidence(
        ctx.evidence_dir / NAME,
        careers_html,
        ats_html,
        linkedin_roles,
        linkedin_employee_count,
    )

    # Source citations
    sources = []
    if careers_url:
        sources.append(SourceCitation(
            url=careers_url, timestamp=now,
            evidence_path=str(
                (ctx.evidence_dir / NAME / "careers.html").relative_to(ctx.evidence_dir)
            ),
        ))
    if ats_url:
        sources.append(SourceCitation(
            url=ats_url, timestamp=now,
            evidence_path=str(
                (ctx.evidence_dir / NAME / "ats.html").relative_to(ctx.evidence_dir)
            ) if ats_html else None,
        ))

    return RevenueMotionData(
        careers_page_url=careers_url,
        ats_platform=ats_platform,
        open_roles=all_roles,
        role_counts=role_counts,
        ae_to_sdr_ratio=ratio,
        linkedin_employee_count=linkedin_employee_count,
        linkedin_job_count=len(linkedin_roles),
        findings=findings,
        gaps=gaps,
        discovery_questions=questions,
        sources=sources,
    )
