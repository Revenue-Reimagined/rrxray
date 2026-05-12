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


def test_role_specs_are_pdl_es_dsl_specs():
    """Each role canonical maps to a PDL ES-DSL search spec dict with at least
    one of `role`, `levels`, or `title_keywords`. List values must be
    non-empty lowercase strings. The PDL client wraps title_keywords as
    wildcard clauses itself, so entries must be plain (no `*` characters).
    """
    valid_keys = {"role", "levels", "title_keywords"}
    for canonical, spec in LEADERSHIP_ROLES:
        assert isinstance(spec, dict), (
            f"{canonical}: spec must be a dict, got {type(spec).__name__}"
        )
        # At least one filter clause; otherwise PDL would return all-people-at-company.
        assert any(k in spec for k in valid_keys), (
            f"{canonical}: spec must have at least one of {valid_keys}; got {spec!r}"
        )
        if "role" in spec:
            assert isinstance(spec["role"], str) and spec["role"], (
                f"{canonical}: spec['role'] must be a non-empty string"
            )
        if "levels" in spec:
            levels = spec["levels"]
            assert isinstance(levels, list) and levels, (
                f"{canonical}: spec['levels'] must be a non-empty list"
            )
            for lv in levels:
                assert isinstance(lv, str) and lv, (
                    f"{canonical}: level entries must be non-empty strings"
                )
        if "title_keywords" in spec:
            kws = spec["title_keywords"]
            assert isinstance(kws, list) and kws, (
                f"{canonical}: spec['title_keywords'] must be a non-empty list"
            )
            for kw in kws:
                assert isinstance(kw, str) and kw, (
                    f"{canonical}: title_keyword entries must be non-empty strings"
                )
                assert "*" not in kw, (
                    f"{canonical}: title_keywords are plain substrings, not wildcards: {kw!r}"
                )


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
