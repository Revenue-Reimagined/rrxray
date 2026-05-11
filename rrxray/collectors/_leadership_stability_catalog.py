"""Static catalog data for the leadership_stability collector.

Hardcoded keyword catalogs and threshold constants. No LLM in this module;
catalog data is deterministic.
"""
from __future__ import annotations

# (canonical, PDL role-title alternatives)
# Used as `role_canonicals` argument to LeadershipEnrichment.find_and_enrich_incumbents;
# each list of titles becomes an OR'd title clause in the PDL Person Search query.
LEADERSHIP_ROLES: list[tuple[str, list[str]]] = [
    ("ceo",          ["CEO", "Chief Executive Officer"]),
    ("cro",          ["CRO", "Chief Revenue Officer"]),
    ("vp_sales",     ["VP Sales", "VP of Sales", "Head of Sales"]),
    ("vp_revenue",   ["VP Revenue", "VP of Revenue", "Head of Revenue"]),
    ("cmo",          ["CMO", "Chief Marketing Officer"]),
    ("vp_marketing", ["VP Marketing", "VP of Marketing", "Head of Marketing"]),
    ("founder",      ["Founder", "Co-founder", "Co-Founder"]),
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
