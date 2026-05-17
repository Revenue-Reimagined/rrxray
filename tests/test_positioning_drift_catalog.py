"""Tests for positioning_drift catalog constants."""
from __future__ import annotations

from rrxray.collectors._positioning_drift_catalog import (
    _H1_RE,
    _MD_LINK_RE,
    MAX_HEADLINE_LEN,
    MAX_NAV_ITEMS,
    MAX_SUBNAV_TEXT_LEN,
    MIN_HEADLINE_LEN,
    NAV_SKIP_PATTERNS,
)


def test_constants_positive():
    assert MIN_HEADLINE_LEN > 0
    assert MAX_HEADLINE_LEN > MIN_HEADLINE_LEN
    assert MAX_SUBNAV_TEXT_LEN > 0
    assert MAX_NAV_ITEMS > 0


def test_h1_re_matches_h1():
    m = _H1_RE.search("# The fastest way to close deals\n\nParagraph.")
    assert m is not None
    assert m.group(1) == "The fastest way to close deals"


def test_h1_re_ignores_h2():
    m = _H1_RE.search("## Section Header\n\nParagraph.")
    assert m is None


def test_md_link_re_matches_nav_link():
    m = _MD_LINK_RE.search("[Pricing](/pricing)")
    assert m is not None
    assert m.group(1) == "Pricing"


def test_md_link_re_ignores_long_text():
    # Link text is >40 chars — should not match because pattern caps at 40
    m = _MD_LINK_RE.search("[This is a very long link text that should not be a nav item](/url)")
    assert m is None


def test_nav_skip_patterns_match_login():
    lower = "login"
    assert any(p.search(lower) for p in NAV_SKIP_PATTERNS)


def test_nav_skip_patterns_match_skip_to_content():
    lower = "skip to content"
    assert any(p.search(lower) for p in NAV_SKIP_PATTERNS)


def test_nav_skip_patterns_do_not_match_product():
    lower = "product"
    assert not any(p.search(lower) for p in NAV_SKIP_PATTERNS)
