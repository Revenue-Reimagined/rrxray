"""Static catalog data for the leadership_stability collector.

Hardcoded keyword catalogs and threshold constants. No LLM in this module;
catalog data is deterministic.
"""
from __future__ import annotations

from typing import Any

# (canonical, PDL ES-DSL search spec)
# Each search_spec dict has up to three optional keys, consumed by
# PDLClient._build_search_call to construct an Elasticsearch DSL query:
#   - "role":  exact `job_title_role` (e.g. "sales", "marketing")
#   - "levels": list of `job_title_levels` (e.g. ["cxo"], ["vp"], ["owner", "partner"])
#   - "title_keywords": list of lowercase substrings — each is wrapped as
#                       `*<keyword>*` and OR'd as wildcard clauses on
#                       `job_title`. Used to disambiguate among candidates
#                       that share role+level (e.g. CRO vs CMO at `cxo`,
#                       VP Revenue vs VP Sales at `sales/vp`).
#
# Why ES DSL and not SQL: PDL Search SQL is exact-match on lowercased
# `job_title`, which produced 0 results for canonical titles like
# "VP Sales" because PDL stores the lowercased written form ("vice
# president of sales"). The classification taxonomy (role + levels) plus
# wildcard title-narrowing matches PDL's actual indexing pattern.
LEADERSHIP_ROLES: list[tuple[str, dict[str, Any]]] = [
    # CEO: cxo level; title contains "chief executive" or "ceo".
    # (CEOs classify across role buckets — leave role unset and rely on
    #  level + title keywords to disambiguate from other C-suite hits.)
    (
        "ceo",
        {
            "levels": ["cxo"],
            "title_keywords": ["chief executive", "ceo"],
        },
    ),
    # CRO: cxo level; title contains "chief revenue" or "cro".
    # (Many CROs classify as `sales`, but some don't — relax to level-only
    #  with title keywords for resilience.)
    (
        "cro",
        {
            "levels": ["cxo"],
            "title_keywords": ["chief revenue", "cro"],
        },
    ),
    # VP Sales: sales role + vp level. Broad: catches "VP Sales", "VP of
    # Sales", "Head of Sales", "Vice President of Sales".
    (
        "vp_sales",
        {
            "role": "sales",
            "levels": ["vp"],
        },
    ),
    # VP Revenue: sales role + vp level + "revenue" in the title (narrows
    # VP Sales bucket down to revenue-titled VPs).
    (
        "vp_revenue",
        {
            "role": "sales",
            "levels": ["vp"],
            "title_keywords": ["revenue"],
        },
    ),
    # CMO: marketing role + cxo level. Title narrowing optional; the
    # role+level combo is already tight.
    (
        "cmo",
        {
            "role": "marketing",
            "levels": ["cxo"],
        },
    ),
    # VP Marketing: marketing role + vp level.
    (
        "vp_marketing",
        {
            "role": "marketing",
            "levels": ["vp"],
        },
    ),
    # Founder: classifies unevenly across levels (cxo / owner / partner /
    # unclassified) — drop the level filter and rely on title keywords.
    (
        "founder",
        {
            "title_keywords": ["founder", "co-founder"],
        },
    ),
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
