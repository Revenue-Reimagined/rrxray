"""Catalog integrity tests."""
import re

from rrxray.collectors._content_demand_catalog import (
    CONTENT_CATEGORIES,
    CONTENT_KEYWORDS,
    LEAD_MAGNET_CTA_PATTERNS,
    PODCAST_PATTERNS,
    SUBSTACK_PATTERN,
)


def test_content_categories_has_eight_entries():
    assert len(CONTENT_CATEGORIES) == 8
    expected = {
        "thought_leadership", "seo_listicle", "case_study",
        "product_announcement", "founder_essay", "tutorial",
        "news_pr", "other",
    }
    assert set(CONTENT_CATEGORIES) == expected


def test_content_keywords_all_have_required_keys():
    for entry in CONTENT_KEYWORDS:
        assert "category" in entry
        assert "keywords" in entry
        assert isinstance(entry["keywords"], list)
        assert len(entry["keywords"]) >= 3


def test_content_keywords_categories_are_valid():
    valid = set(CONTENT_CATEGORIES)
    for entry in CONTENT_KEYWORDS:
        assert entry["category"] in valid, f"unknown category {entry['category']}"


def test_content_keywords_seo_listicle_checked_first():
    """Order matters: more specific patterns should appear first in the list."""
    first_category = CONTENT_KEYWORDS[0]["category"]
    assert first_category == "seo_listicle"


def test_lead_magnet_cta_patterns_have_seven_asset_types():
    asset_types = {p["asset_type"] for p in LEAD_MAGNET_CTA_PATTERNS}
    expected = {"ebook", "whitepaper", "guide", "template", "calculator", "report", "webinar"}
    assert asset_types == expected


def test_podcast_patterns_compile_and_match():
    by_platform = {p["platform"]: p["url_pattern"] for p in PODCAST_PATTERNS}
    apple = re.compile(by_platform["apple_podcasts"])
    spotify = re.compile(by_platform["spotify"])
    assert apple.search("https://podcasts.apple.com/us/podcast/abc-show")
    assert spotify.search("https://open.spotify.com/show/abc123XYZ")


def test_substack_pattern_compiles_and_matches():
    p = re.compile(SUBSTACK_PATTERN)
    assert p.search("https://example.substack.com/archive")
    assert not p.search("https://example.com/blog")
