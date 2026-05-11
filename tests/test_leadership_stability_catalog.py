"""Catalog integrity tests for leadership_stability."""
from __future__ import annotations

from rrxray.collectors._leadership_stability_catalog import (
    FOUNDED_YEAR_PATTERNS,
    LEADERSHIP_ROLES,
    PRESS_ACTION_QUERIES,
    PRESS_LOOKBACK_MONTHS,
    RECENT_THRESHOLD_DAYS,
    ROLE_DISPLAY,
)


def test_seven_canonical_roles():
    canonicals = [c for c, _ in LEADERSHIP_ROLES]
    assert canonicals == ["ceo", "cro", "vp_sales", "vp_revenue", "cmo", "vp_marketing", "founder"]


def test_three_action_query_groups():
    actions = [a for a, _ in PRESS_ACTION_QUERIES]
    assert set(actions) == {"hire", "departure", "promotion"}


def test_role_display_covers_all_canonicals():
    for canonical, _ in LEADERSHIP_ROLES:
        assert canonical in ROLE_DISPLAY, f"missing display for {canonical}"


def test_thresholds_are_sensible():
    assert PRESS_LOOKBACK_MONTHS == 18
    assert RECENT_THRESHOLD_DAYS == 270


def test_role_titles_are_pdl_search_alternatives():
    """Each role canonical maps to a non-empty list of plain role-title strings
    (used as OR alternatives in PDL Person Search). No quote characters; the
    PDL search builder wraps them itself.
    """
    for canonical, titles in LEADERSHIP_ROLES:
        assert isinstance(titles, list), f"{canonical}: titles must be a list, got {type(titles).__name__}"
        assert titles, f"{canonical}: titles list must be non-empty"
        for t in titles:
            assert isinstance(t, str) and t, f"{canonical}: title entries must be non-empty strings"
            assert '"' not in t, f"{canonical}: PDL titles are plain (not pre-quoted): {t!r}"


def test_founded_year_patterns_match_common_phrasings():
    import re
    text_samples = [
        ("Founded in 2018 by...", "2018"),
        ("Since 2015, we've...", "2015"),
        ("Founded 2020.", "2020"),
        ("Established in 2010", "2010"),
        ("Established 2012", "2012"),
    ]
    for text, expected_year in text_samples:
        matched = False
        for pat in FOUNDED_YEAR_PATTERNS:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                assert m.group(1) == expected_year, f"{text!r} matched {pat} but got {m.group(1)}"
                matched = True
                break
        assert matched, f"No pattern matched {text!r}"
