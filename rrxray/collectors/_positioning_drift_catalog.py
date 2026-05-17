"""Constants for the positioning_drift collector."""
from __future__ import annotations

import re

# Extraction thresholds
MIN_HEADLINE_LEN = 10
MAX_HEADLINE_LEN = 200
MAX_SUBNAV_TEXT_LEN = 40
MAX_NAV_ITEMS = 12

# Regex: first H1 line (not H2+)
_H1_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)

# Regex: markdown link with text up to MAX_SUBNAV_TEXT_LEN chars
_MD_LINK_RE = re.compile(r"\[([^\]]{1,40})\]\([^\)]+\)")

# Nav link texts to skip (login, utility, skip-link patterns)
_NAV_SKIP_RAW = [
    r"^skip\b",
    r"^login$",
    r"^log\s?in$",
    r"^sign\s?in$",
    r"^sign\s?up$",
    r"^get\s+started$",
    r"cookie",
    r"^accessibility",
    r"^privacy",
    r"^terms",
    r"^\d+$",          # pure numbers
]
NAV_SKIP_PATTERNS: list[re.Pattern] = [re.compile(p, re.IGNORECASE) for p in _NAV_SKIP_RAW]
