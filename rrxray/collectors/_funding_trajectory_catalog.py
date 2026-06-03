"""Constants for the funding_trajectory collector."""
from __future__ import annotations

import re

CRUNCHBASE_ORG_URL_TEMPLATE = "https://www.crunchbase.com/organization/{slug}"
CRUNCHBASE_SEARCH_QUERY_TEMPLATE = 'site:crunchbase.com/organization "{company}"'

FUNDING_PRESS_QUERY_TEMPLATE = (
    '"{company}" (raises OR "raised Series" OR "Series A" OR "Series B" OR '
    '"Series C" OR "Series D" OR funding OR "led by" OR "lead investor")'
)

FUNDING_PRESS_RESULT_LIMIT = 10

SERIES_TO_STAGE: dict[str, str] = {
    "pre_seed": "seed",
    "seed": "seed",
    "series_a": "early_growth",
    "series_b": "early_growth",
    "series_c": "growth",
    "series_d": "growth",
    "series_e_plus": "late_growth",
    "growth": "late_growth",
    "private_equity": "late_growth",
    "ipo": "public",
    "acquisition": "acquired",
    "debt": "signal_not_recovered",
    "grant": "signal_not_recovered",
    "unknown": "signal_not_recovered",
}

SERIES_LABEL_MAP: dict[str, str] = {
    "pre_seed": "pre-seed",
    "seed": "Seed",
    "series_a": "Series A",
    "series_b": "Series B",
    "series_c": "Series C",
    "series_d": "Series D",
    "series_e_plus": "Series E+",
    "growth": "Growth",
    "private_equity": "Private Equity",
    "ipo": "IPO",
    "acquisition": "Acquisition",
    "debt": "Debt",
    "grant": "Grant",
    "unknown": "Unknown",
}

AMOUNT_RE = re.compile(
    r"\$\s*(\d+(?:\.\d+)?)\s*(?:M|million|B|billion)",
    re.IGNORECASE,
)

DATE_RE = re.compile(
    r"(?:"
    r"\d{4}-\d{2}-\d{2}"
    r"|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2},?\s+\d{4}"
    r"|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{4}"
    r")",
    re.IGNORECASE,
)

CRUNCHBASE_BLOCKED_PHRASES = [
    "cf-browser-verification",
    "access denied",
    "captcha",
    "checking your browser",
    "cloudflare",
    "please verify",
]

RECENT_RAISE_THRESHOLD_MONTHS = 12
STRETCHING_RUNWAY_THRESHOLD_MONTHS = 24

SERIES_KEYWORDS: list[tuple[str, str]] = [
    ("Series E", "series_e_plus"),
    ("Series D", "series_d"),
    ("Series C", "series_c"),
    ("Series B", "series_b"),
    ("Series A", "series_a"),
    ("Seed", "seed"),
    ("Pre-Seed", "pre_seed"),
    ("Pre Seed", "pre_seed"),
    ("Growth", "growth"),
    ("Private Equity", "private_equity"),
    ("IPO", "ipo"),
    ("Acquisition", "acquisition"),
    ("Debt", "debt"),
    ("Grant", "grant"),
]
