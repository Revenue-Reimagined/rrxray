"""funding_trajectory collector.

Discovers and parses public funding signals for a company from Crunchbase
(deterministic HTML parsing) and press releases (LLM extraction via
HaikuExtractor). No paid third-party APIs in v1.

LLM-in-collector exception: press release text is genuinely unstructured
natural language; regex coverage of funding-round amounts, dates, and investor
names is too patchy. Mirrors Phase 2.2 extract_exec_change amendment exactly.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rrxray.collectors._funding_trajectory_catalog import (
    AMOUNT_RE,
    CRUNCHBASE_BLOCKED_PHRASES,
    CRUNCHBASE_SEARCH_QUERY_TEMPLATE,
    DATE_RE,
    FUNDING_PRESS_QUERY_TEMPLATE,
    FUNDING_PRESS_RESULT_LIMIT,
    RECENT_RAISE_THRESHOLD_MONTHS,
    SERIES_KEYWORDS,
    SERIES_LABEL_MAP,
    SERIES_TO_STAGE,
    STRETCHING_RUNWAY_THRESHOLD_MONTHS,
)
from rrxray.schemas._shared import Finding, SourceCitation
from rrxray.schemas.funding_trajectory import FundingRound, FundingTrajectoryData

if TYPE_CHECKING:
    from rrxray.context import CollectorContext

NAME = "funding_trajectory"
log = logging.getLogger(f"rrxray.collectors.{NAME}")

# Crunchbase synthetic-fixture parsing patterns.
# The funding-round card boundary: a <div> whose class contains
# "funding-round-card" (we tolerate dashes, underscores, or spaces).
_CARD_RE = re.compile(
    r'<div[^>]*class="[^"]*funding[-_\s]?round[-_\s]?card[^"]*"[^>]*>(.*?)</div>',
    re.IGNORECASE | re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")
_INVESTOR_RE = re.compile(
    r'<[a-zA-Z]+[^>]*class="[^"]*(?:lead[-_\s]?investor|investor|lead)[^"]*"[^>]*>'
    r"([^<]+)</[a-zA-Z]+>",
    re.IGNORECASE,
)
_FUNDING_SECTION_RE = re.compile(
    r"Funding\s+Rounds?",
    re.IGNORECASE,
)


def _is_crunchbase_blocked(html: str) -> bool:
    """Return True if the Crunchbase page is a bot-detection interstitial."""
    lower = html.lower()
    return any(phrase in lower for phrase in CRUNCHBASE_BLOCKED_PHRASES)


def _get_attr(obj: Any, key: str, default: Any = None) -> Any:
    """Read either a dict key or an attribute. Defensive for mock vs real shapes."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


async def _discover_crunchbase_url(
    firecrawl: Any, company: str, domain: str
) -> str | None:
    """Search Firecrawl for the company's Crunchbase organization page URL."""
    query = CRUNCHBASE_SEARCH_QUERY_TEMPLATE.format(company=company)
    try:
        results = await firecrawl.search(query, limit=5)
    except Exception as e:
        log.debug("Crunchbase search failed: %s", e)
        return None
    for r in results or []:
        url = _get_attr(r, "url", "") or ""
        if "crunchbase.com/organization/" in url:
            return url
    return None


def _parse_amount(text: str) -> float | None:
    """Extract USD amount in millions from text like '$25M' or '$8.5 million'."""
    m = AMOUNT_RE.search(text)
    if not m:
        return None
    raw = float(m.group(1))
    matched = text[m.start():m.end()].lower()
    if "billion" in matched or matched.rstrip().endswith("b"):
        return raw * 1000
    return raw


def _parse_date(text: str) -> date | None:
    """Extract first parseable date from text. Returns None if unparseable."""
    m = DATE_RE.search(text)
    if not m:
        return None
    raw = m.group(0).replace(",", "")
    for fmt in ("%Y-%m-%d", "%B %d %Y", "%b %d %Y", "%B %Y", "%b %Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _detect_series(text: str) -> str | None:
    """Detect funding series keyword in text. Returns FundingSeries literal or None."""
    lower = text.lower()
    for keyword, series in SERIES_KEYWORDS:
        if keyword.lower() in lower:
            return series
    return None


def _strip_tags(html_fragment: str) -> str:
    """Strip HTML tags and collapse whitespace."""
    text = _TAG_RE.sub(" ", html_fragment)
    return re.sub(r"\s+", " ", text).strip()


def _parse_crunchbase_html(html: str, source_url: str) -> list[FundingRound]:
    """Parse funding round cards from Crunchbase HTML using regex."""
    rounds: list[FundingRound] = []

    cards = _CARD_RE.findall(html)
    if cards:
        for card_html in cards:
            text = _strip_tags(card_html)
            series = _detect_series(text)
            if series is None:
                continue
            amount = _parse_amount(text)
            announced = _parse_date(text)

            investor_match = _INVESTOR_RE.search(card_html)
            lead_investor = (
                investor_match.group(1).strip()[:80] if investor_match else None
            )

            rounds.append(FundingRound(
                series=series,
                amount_usd_millions=amount,
                announced_date=announced,
                lead_investor=lead_investor or None,
                source_url=source_url,
                source_type="crunchbase",
            ))
        return rounds

    # Fallback: scan the document text only if a Funding Rounds marker exists.
    if _FUNDING_SECTION_RE.search(html):
        text = _strip_tags(html)
        # Avoid emitting any rounds when the page explicitly reports none.
        if "no funding rounds" in text.lower():
            return rounds
        series = _detect_series(text)
        if series is not None:
            rounds.append(FundingRound(
                series=series,
                amount_usd_millions=_parse_amount(text),
                announced_date=_parse_date(text),
                source_url=source_url,
                source_type="crunchbase",
            ))
    return rounds


async def _scrape_crunchbase(
    firecrawl: Any, crunchbase_url: str
) -> list[FundingRound]:
    """Scrape Crunchbase org page and parse funding rounds deterministically."""
    try:
        result = await firecrawl.scrape_url(crunchbase_url, only_main_content=False)
    except Exception as e:
        log.debug("Crunchbase scrape failed: %s", e)
        return []
    html = _get_attr(result, "html", "") or ""
    if not html or _is_crunchbase_blocked(html):
        return []
    return _parse_crunchbase_html(html, crunchbase_url)


async def _search_funding_press(firecrawl: Any, company: str) -> list[dict]:
    """Search for funding press releases about the company."""
    query = FUNDING_PRESS_QUERY_TEMPLATE.format(company=company)
    try:
        return await firecrawl.search(query, limit=FUNDING_PRESS_RESULT_LIMIT)
    except Exception as e:
        log.debug("Funding press search failed: %s", e)
        return []


async def _extract_press_rounds(
    results: list[dict],
    extractor: Any,
    company: str,
    domain: str,
    firecrawl: Any,
) -> list[FundingRound]:
    """For each search result, scrape body and call extract_funding_event."""
    rounds: list[FundingRound] = []
    for r in results:
        url = _get_attr(r, "url", "") or ""
        title = _get_attr(r, "title", "") or ""
        snippet = _get_attr(r, "snippet", "") or ""
        body: str | None = None
        try:
            page = await firecrawl.scrape_url(url, only_main_content=True)
            body = _get_attr(page, "markdown", None) or _get_attr(page, "html", None)
            if body and len(body) > 8000:
                body = body[:8000]
        except Exception:
            pass
        event = await extractor.extract_funding_event(
            title=title,
            snippet=snippet,
            target_company=company,
            target_domain=domain,
            body=body,
        )
        if event is None:
            continue
        announced: date | None = None
        if event.announced_date:
            try:
                announced = datetime.strptime(event.announced_date, "%Y-%m-%d").date()
            except ValueError:
                announced = None
        series = event.series if event.series in SERIES_TO_STAGE else "unknown"
        if series == "unknown" and event.series not in ("unknown", None, ""):
            # LLM returned an unrecognized series label; drop rather than emit a noise row
            continue
        rounds.append(FundingRound(
            series=series,
            amount_usd_millions=event.amount_usd_millions,
            announced_date=announced,
            lead_investor=event.lead_investor,
            source_url=url,
            source_title=title,
            source_type="press",
        ))
    return rounds


def _dedupe_rounds(
    crunchbase_rounds: list[FundingRound],
    press_rounds: list[FundingRound],
) -> list[FundingRound]:
    """Crunchbase wins on same series; press rounds with no CB match are kept;
    press rounds deduped by series (first occurrence wins).

    Returns rounds in reverse chronological order (most recent first).
    """
    cb_series = {r.series for r in crunchbase_rounds}
    unique_press: list[FundingRound] = []
    seen_press_series: set[str] = set()
    for r in press_rounds:
        if r.series not in cb_series and r.series not in seen_press_series:
            unique_press.append(r)
            seen_press_series.add(r.series)
    all_rounds = crunchbase_rounds + unique_press

    def _sort_key(r: FundingRound) -> date:
        return r.announced_date or date.min

    return sorted(all_rounds, key=_sort_key, reverse=True)


def _compute_aggregates(
    rounds: list[FundingRound], today: date,
) -> tuple[float | None, int | None, str]:
    """Return (total_raised_usd_millions, last_round_months_ago, implied_stage)."""
    if not rounds:
        return None, None, "bootstrapped"

    # Find most recent by date (rounds already sorted reverse chrono from _dedupe_rounds)
    dated = [r for r in rounds if r.announced_date is not None]
    latest = dated[0] if dated else rounds[0]
    stage = SERIES_TO_STAGE.get(latest.series, "signal_not_recovered")

    last_months: int | None = None
    if latest.announced_date:
        days = (today - latest.announced_date).days
        last_months = max(1, days // 30)

    amounts = [r.amount_usd_millions for r in rounds if r.amount_usd_millions is not None]
    total = round(sum(amounts), 2) if amounts else None

    return total, last_months, stage


def _emit_findings(
    rounds: list[FundingRound],
    last_months: int | None,
    stage: str,
    crunchbase_recovered: bool,
) -> tuple[list[Finding], list[str], list[str]]:
    """Rule-based findings, gaps, discovery_questions."""
    source = SourceCitation(url="rrxray://funding_trajectory", timestamp=datetime.now(UTC))

    findings: list[Finding] = []
    gaps: list[str] = []
    dqs: list[str] = []

    if not rounds or stage == "signal_not_recovered":
        findings.append(Finding(
            text="Funding signal not recovered from public sources.",
            source=source,
        ))
        dqs.append("What is the company's current funding status and capital plan?")
        return findings, gaps, dqs

    latest = rounds[0]
    series_label = SERIES_LABEL_MAP.get(latest.series, latest.series)

    if last_months is not None and last_months <= RECENT_RAISE_THRESHOLD_MONTHS:
        findings.append(Finding(
            text=f"Recently capitalized: {series_label} raise ~{last_months} months ago.",
            source=source,
        ))
    elif last_months is not None and last_months > STRETCHING_RUNWAY_THRESHOLD_MONTHS:
        findings.append(Finding(
            text=(
                f"Funding cadence stretching: last raise ({series_label}) was ~{last_months} months ago. "
                "Runway extension is a live question."
            ),
            source=source,
        ))
    else:
        findings.append(Finding(
            text=f"Most recent funding: {series_label}.",
            source=source,
        ))

    if not crunchbase_recovered:
        gaps.append("Crunchbase profile not located; trajectory derived from press releases only.")

    dqs.append("What is the company's current runway and capital deployment plan?")

    return findings, gaps, dqs


def _write_evidence(
    evidence_dir: Path,
    rounds: list[FundingRound],
    search_results: list[dict],
) -> None:
    """Write funding evidence files."""
    ev = Path(evidence_dir) / "funding_trajectory"
    ev.mkdir(parents=True, exist_ok=True)
    rounds_data = [r.model_dump(mode="json") for r in rounds]
    (ev / "rounds.json").write_text(json.dumps(rounds_data, indent=2, default=str))
    (ev / "press_search.json").write_text(json.dumps(search_results, indent=2))


async def collect(ctx: CollectorContext) -> FundingTrajectoryData:
    """Main collector entry point."""
    today = datetime.now(UTC).date()
    company = ctx.company_name or ctx.domain.split(".")[0].title()
    domain = ctx.domain

    crunchbase_url: str | None = None
    crunchbase_rounds: list[FundingRound] = []
    crunchbase_recovered = False

    try:
        crunchbase_url = await _discover_crunchbase_url(ctx.firecrawl, company, domain)
        if crunchbase_url:
            crunchbase_rounds = await _scrape_crunchbase(ctx.firecrawl, crunchbase_url)
            crunchbase_recovered = len(crunchbase_rounds) > 0 or crunchbase_url is not None
    except Exception as e:
        log.warning("Crunchbase phase failed: %s", e)

    search_results: list[dict] = []
    press_rounds: list[FundingRound] = []
    try:
        search_results = await _search_funding_press(ctx.firecrawl, company)
        press_rounds = await _extract_press_rounds(
            search_results, ctx.extractor, company, domain, ctx.firecrawl
        )
    except Exception as e:
        log.warning("Press funding search phase failed: %s", e)

    rounds = _dedupe_rounds(crunchbase_rounds, press_rounds)
    total_raised, last_months, stage = _compute_aggregates(rounds, today)

    # If we couldn't recover any Crunchbase profile AND no press search results
    # surfaced AND we have no rounds, treat as signal_not_recovered rather than
    # "bootstrapped" (we have no evidence either way).
    if not rounds and crunchbase_url is None and not search_results:
        stage = "signal_not_recovered"

    findings, gaps, dqs = _emit_findings(rounds, last_months, stage, crunchbase_recovered)

    try:
        _write_evidence(ctx.evidence_dir, rounds, search_results)
    except Exception as e:
        log.warning("Evidence write failed: %s", e)

    now = datetime.now(UTC)
    sources = [SourceCitation(url=r.source_url, timestamp=now) for r in rounds]
    if crunchbase_url:
        sources.insert(0, SourceCitation(url=crunchbase_url, timestamp=now))

    return FundingTrajectoryData(
        rounds=rounds,
        total_raised_usd_millions=total_raised,
        last_round_months_ago=last_months,
        implied_stage=stage,
        crunchbase_url=crunchbase_url,
        crunchbase_recovered=crunchbase_recovered,
        findings=findings,
        gaps=gaps,
        discovery_questions=dqs,
        sources=sources,
    )
