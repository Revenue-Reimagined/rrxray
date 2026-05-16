"""funding_trajectory collector.

Discovers and parses public funding signals for a company from Crunchbase
(deterministic HTML parsing) and press releases (LLM extraction via
HaikuExtractor). No paid third-party APIs in v1.

LLM-in-collector exception: press release text is genuinely unstructured
natural language; regex coverage of funding-round amounts, dates, and investor
names is too patchy. Mirrors Phase 2.2 extract_exec_change amendment exactly.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Any

from rrxray.collectors._funding_trajectory_catalog import (
    AMOUNT_RE,
    CRUNCHBASE_BLOCKED_PHRASES,
    CRUNCHBASE_SEARCH_QUERY_TEMPLATE,
    DATE_RE,
    SERIES_KEYWORDS,
)
from rrxray.schemas.funding_trajectory import FundingRound

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
