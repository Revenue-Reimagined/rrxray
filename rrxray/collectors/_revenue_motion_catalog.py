"""Role-taxonomy and ATS-pattern catalogs for the revenue_motion collector.

Hardcoded keyword catalog matches the Phase 2.1a tech_stack pattern: deterministic,
no LLM in collector path, easy to extend by appending entries. When new role title
patterns surface that don't match, append them here.

Adding a role keyword: append a dict to ROLE_KEYWORDS (entries are processed in order;
more specific patterns first beat generic ones).

Adding an ATS platform: append a dict to ATS_PATTERNS with name + url_pattern (regex).
"""
from __future__ import annotations

ROLE_CATEGORIES: list[str] = [
    "ae",
    "sdr",
    "revops",
    "csm",
    "sales_leadership",
    "marketing_leadership",
    "marketing_ops",
    "other",
]


# Order matters: more specific titles checked first
ROLE_KEYWORDS: list[dict] = [
    # AE titles (specific multi-word first)
    {"category": "ae", "keywords": [
        "enterprise account executive",
        "strategic account executive",
        "mid-market account executive",
        "senior account executive",
        "account executive",
        "sales representative",
    ]},
    {"category": "ae", "keywords": [
        "AE", "enterprise AE", "strategic AE", "founding AE",
    ]},

    # SDR titles
    {"category": "sdr", "keywords": [
        "sales development representative",
        "business development representative",
        "outbound SDR",
        "inbound SDR",
    ]},
    {"category": "sdr", "keywords": ["SDR", "BDR"]},

    # RevOps
    {"category": "revops", "keywords": [
        "revenue operations",
        "sales operations",
        "go-to-market operations",
        "GTM operations",
    ]},
    {"category": "revops", "keywords": ["RevOps", "SalesOps"]},

    # CSM
    {"category": "csm", "keywords": [
        "customer success manager",
        "customer success",
        "account manager",
        "post-sales",
        "renewals manager",
    ]},
    {"category": "csm", "keywords": ["CSM"]},

    # Sales leadership (specific titles)
    {"category": "sales_leadership", "keywords": [
        "chief revenue officer",
        "VP of sales",
        "VP sales",
        "head of sales",
        "director of sales",
        "VP revenue",
        "VP of revenue",
        "head of revenue",
    ]},
    {"category": "sales_leadership", "keywords": ["CRO"]},

    # Marketing leadership
    {"category": "marketing_leadership", "keywords": [
        "chief marketing officer",
        "VP marketing",
        "VP of marketing",
        "head of marketing",
        "director of marketing",
    ]},
    {"category": "marketing_leadership", "keywords": ["CMO"]},

    # Marketing ops
    {"category": "marketing_ops", "keywords": [
        "marketing operations",
        "marketing ops",
        "demand generation",
        "demand gen",
    ]},
]


# ATS platform detection patterns. Each entry's url_pattern is a regex applied
# (case-insensitive) against any link href found in scraped careers-page HTML.
ATS_PATTERNS: list[dict[str, str]] = [
    {"name": "lever", "url_pattern": r"jobs\.lever\.co/([a-z0-9-]+)"},
    {"name": "greenhouse", "url_pattern": r"boards\.greenhouse\.io/([a-z0-9-]+)"},
    {"name": "ashby", "url_pattern": r"([a-z0-9-]+)\.ashbyhq\.com"},
    {"name": "workable", "url_pattern": r"apply\.workable\.com/([a-z0-9-]+)"},
]
