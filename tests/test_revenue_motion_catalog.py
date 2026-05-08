"""Catalog integrity tests."""
import re

from rrxray.collectors._revenue_motion_catalog import (
    ATS_PATTERNS,
    ROLE_CATEGORIES,
    ROLE_KEYWORDS,
)


def test_role_categories_has_eight_entries():
    assert len(ROLE_CATEGORIES) == 8
    expected = {
        "ae", "sdr", "revops", "csm",
        "sales_leadership", "marketing_leadership",
        "marketing_ops", "other",
    }
    assert set(ROLE_CATEGORIES) == expected


def test_role_keywords_all_have_required_keys():
    for entry in ROLE_KEYWORDS:
        assert "category" in entry
        assert "keywords" in entry
        assert isinstance(entry["keywords"], list)
        assert len(entry["keywords"]) > 0


def test_role_keywords_categories_are_valid():
    valid = set(ROLE_CATEGORIES)
    for entry in ROLE_KEYWORDS:
        assert entry["category"] in valid, (
            f"unknown category {entry['category']}"
        )


def test_role_keywords_cover_major_categories():
    """Spec mandate: every major revenue role category should have keywords."""
    covered = {entry["category"] for entry in ROLE_KEYWORDS}
    required = {"ae", "sdr", "revops", "csm", "sales_leadership"}
    missing = required - covered
    assert not missing, f"required categories missing: {missing}"


def test_ats_patterns_has_four_platforms():
    """Lever, Greenhouse, Ashby, Workable — the four most common B2B SaaS ATS platforms."""
    assert len(ATS_PATTERNS) >= 4
    names = {p["name"] for p in ATS_PATTERNS}
    expected = {"lever", "greenhouse", "ashby", "workable"}
    assert expected.issubset(names)


def test_ats_patterns_are_valid_regex():
    for entry in ATS_PATTERNS:
        re.compile(entry["url_pattern"])


def test_ats_patterns_match_real_urls():
    """Each ATS pattern should match a typical URL for that platform."""
    test_cases = [
        ("lever", "https://jobs.lever.co/swayable", True),
        ("greenhouse", "https://boards.greenhouse.io/linear", True),
        ("ashby", "https://example.ashbyhq.com", True),
        ("workable", "https://apply.workable.com/example", True),
        ("lever", "https://example.com/careers", False),
    ]
    for platform, url, should_match in test_cases:
        pattern = next(p for p in ATS_PATTERNS if p["name"] == platform)
        m = re.search(pattern["url_pattern"], url)
        if should_match:
            assert m is not None, f"{platform} pattern should match {url}"
        else:
            assert m is None, f"{platform} pattern should NOT match {url}"
