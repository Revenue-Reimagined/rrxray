"""Catalog integrity tests for funding_trajectory constants."""
from __future__ import annotations

import re

from rrxray.collectors._funding_trajectory_catalog import (
    AMOUNT_RE,
    CRUNCHBASE_BLOCKED_PHRASES,
    CRUNCHBASE_ORG_URL_TEMPLATE,
    CRUNCHBASE_SEARCH_QUERY_TEMPLATE,
    DATE_RE,
    FUNDING_PRESS_QUERY_TEMPLATE,
    FUNDING_PRESS_RESULT_LIMIT,
    RECENT_RAISE_THRESHOLD_MONTHS,
    SERIES_KEYWORDS,
    SERIES_LABEL_MAP,
    SERIES_TO_STAGE,
    STRETCHING_RUNWAY_THRESHOLD_MONTHS,
)


def test_crunchbase_url_template_formats():
    url = CRUNCHBASE_ORG_URL_TEMPLATE.format(slug="acme-corp")
    assert "crunchbase.com/organization/acme-corp" in url


def test_crunchbase_search_query_template():
    query = CRUNCHBASE_SEARCH_QUERY_TEMPLATE.format(company="Acme Inc")
    assert "Acme Inc" in query
    assert "crunchbase.com/organization" in query


def test_press_query_template_has_placeholders():
    query = FUNDING_PRESS_QUERY_TEMPLATE.format(company="Acme Inc")
    assert "Acme Inc" in query
    assert any(kw in query for kw in ("raises", "Series", "funding"))


def test_press_result_limit_is_sensible():
    assert 5 <= FUNDING_PRESS_RESULT_LIMIT <= 20


def test_series_to_stage_covers_all_series():
    required = {
        "pre_seed", "seed", "series_a", "series_b", "series_c",
        "series_d", "series_e_plus", "growth", "private_equity",
        "ipo", "acquisition", "debt", "grant", "unknown",
    }
    assert required.issubset(set(SERIES_TO_STAGE.keys()))


def test_series_to_stage_maps_correctly():
    assert SERIES_TO_STAGE["series_b"] == "early_growth"
    assert SERIES_TO_STAGE["series_c"] == "growth"
    assert SERIES_TO_STAGE["ipo"] == "public"
    assert SERIES_TO_STAGE["acquisition"] == "acquired"
    assert SERIES_TO_STAGE["seed"] == "seed"
    assert SERIES_TO_STAGE["pre_seed"] == "seed"
    assert SERIES_TO_STAGE["series_e_plus"] == "late_growth"
    assert SERIES_TO_STAGE["unknown"] == "signal_not_recovered"


def test_series_label_map_covers_all_series():
    required = {
        "pre_seed", "seed", "series_a", "series_b", "series_c",
        "series_d", "series_e_plus", "growth", "private_equity",
        "ipo", "acquisition", "debt", "grant", "unknown",
    }
    assert required.issubset(set(SERIES_LABEL_MAP.keys()))


def test_amount_re_matches_dollar_amounts():
    assert re.search(AMOUNT_RE, "$25M")
    assert re.search(AMOUNT_RE, "$8.5 million")
    assert re.search(AMOUNT_RE, "$100M")


def test_amount_re_does_not_match_non_dollar():
    assert not re.search(AMOUNT_RE, "raised funding")
    assert not re.search(AMOUNT_RE, "25 employees")


def test_date_re_matches_common_formats():
    assert re.search(DATE_RE, "March 15, 2024")
    assert re.search(DATE_RE, "2024-03-15")
    assert re.search(DATE_RE, "Mar 2024")


def test_blocked_phrases_list_nonempty():
    assert len(CRUNCHBASE_BLOCKED_PHRASES) >= 2
    assert all(isinstance(p, str) for p in CRUNCHBASE_BLOCKED_PHRASES)


def test_thresholds_are_sensible():
    assert 6 <= RECENT_RAISE_THRESHOLD_MONTHS <= 18
    assert 18 <= STRETCHING_RUNWAY_THRESHOLD_MONTHS <= 36


def test_series_keywords_tuple_list():
    assert len(SERIES_KEYWORDS) >= 5
    for item in SERIES_KEYWORDS:
        assert len(item) == 2
        keyword, series = item
        assert isinstance(keyword, str)
        assert series in SERIES_TO_STAGE
