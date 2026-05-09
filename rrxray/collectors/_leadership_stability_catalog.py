"""Static catalog data for the leadership_stability collector.

Hardcoded keyword catalogs and threshold constants. No LLM in this module;
catalog data is deterministic.
"""
from __future__ import annotations

# (canonical, LinkedIn search keyword fragment)
LEADERSHIP_ROLES: list[tuple[str, str]] = [
    ("ceo",            '"CEO"'),
    ("cro",            '"CRO" OR "Chief Revenue Officer"'),
    ("vp_sales",       '"VP Sales" OR "VP of Sales" OR "Head of Sales"'),
    ("vp_revenue",     '"VP Revenue" OR "VP of Revenue" OR "Head of Revenue"'),
    ("cmo",            '"CMO" OR "Chief Marketing Officer"'),
    ("vp_marketing",   '"VP Marketing" OR "VP of Marketing" OR "Head of Marketing"'),
    ("founder",        '"Founder" OR "Co-founder"'),
]


# (action label, query keywords for Google search)
PRESS_ACTION_QUERIES: list[tuple[str, str]] = [
    ("hire",      "appoints OR names OR hires OR welcomes OR joins"),
    ("departure", 'departs OR resigns OR "steps down" OR "stepping down"'),
    ("promotion", "promoted OR promotion"),
]


# canonical → display string for findings text + role descriptors
ROLE_DISPLAY: dict[str, str] = {
    "ceo":          "CEO",
    "cro":          "CRO",
    "vp_sales":     "VP Sales",
    "vp_revenue":   "VP Revenue",
    "cmo":          "CMO",
    "vp_marketing": "VP Marketing",
    "founder":      "founder",
}


PRESS_LOOKBACK_MONTHS: int = 18
RECENT_THRESHOLD_DAYS: int = 270  # ~9 months


# Regex patterns for inferring founding year from /about page copy.
FOUNDED_YEAR_PATTERNS: list[str] = [
    r"founded\s+in\s+(\d{4})",
    r"since\s+(\d{4})",
    r"founded\s+(\d{4})",
    r"established\s+in\s+(\d{4})",
    r"established\s+(\d{4})",
]
