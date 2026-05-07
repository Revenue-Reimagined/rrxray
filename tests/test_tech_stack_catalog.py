"""Catalog integrity tests: every signature is well-formed and compiles."""
import re

from rrxray.collectors._tech_stack_catalog import CATEGORIES, SIGNATURES


def test_catalog_has_at_least_30_signatures():
    """Spec mandate: ~40 signatures spanning all categories. Allow some leeway."""
    assert len(SIGNATURES) >= 30


def test_categories_constant_has_nine_entries():
    expected = {
        "analytics", "tag_manager", "marketing_automation", "chat",
        "product_analytics", "crm", "cdp", "ab_testing", "attribution",
    }
    assert set(CATEGORIES) == expected
    assert len(CATEGORIES) == 9


def test_every_signature_has_required_keys():
    required = {"tool", "category", "id", "pattern", "confidence"}
    for sig in SIGNATURES:
        missing = required - set(sig.keys())
        assert not missing, f"signature {sig.get('id')!r} missing keys: {missing}"


def test_every_category_in_signatures_is_valid():
    valid = set(CATEGORIES)
    for sig in SIGNATURES:
        assert sig["category"] in valid, (
            f"signature {sig['id']!r} has invalid category {sig['category']!r}"
        )


def test_every_confidence_is_high_or_low():
    for sig in SIGNATURES:
        assert sig["confidence"] in ("high", "low"), (
            f"signature {sig['id']!r} has invalid confidence {sig['confidence']!r}"
        )


def test_signature_ids_are_unique():
    ids = [sig["id"] for sig in SIGNATURES]
    assert len(ids) == len(set(ids)), (
        f"duplicate signature ids: {[i for i in ids if ids.count(i) > 1]}"
    )


def test_every_pattern_compiles():
    for sig in SIGNATURES:
        try:
            re.compile(sig["pattern"], re.IGNORECASE)
        except re.error as e:
            raise AssertionError(
                f"signature {sig['id']!r} has invalid pattern {sig['pattern']!r}: {e}"
            ) from e


def test_catalog_covers_all_nine_categories():
    """Every category should have at least one signature so absence-detection works."""
    covered = {sig["category"] for sig in SIGNATURES}
    missing = set(CATEGORIES) - covered
    assert not missing, f"categories with no signatures: {missing}"


def test_catalog_includes_specs_named_tools():
    """Spec named: Segment, GTM, HubSpot, Marketo, Intercom, Drift, Pendo, Salesforce W2L."""
    tool_names = {sig["tool"] for sig in SIGNATURES}
    expected = {
        "Segment", "Google Tag Manager", "HubSpot", "Marketo",
        "Intercom", "Drift", "Pendo", "Salesforce Web-to-Lead",
    }
    missing = expected - tool_names
    assert not missing, f"spec-named tools missing from catalog: {missing}"


def test_catalog_includes_dom_level_loose_signatures():
    """Catalog must include DOM-level loose signatures for tools whose script tags get stripped."""
    dom_loose_ids = [s["id"] for s in SIGNATURES if "loose_dom" in s["id"] or "loose_noscript" in s["id"] or "loose_inline" in s["id"]]
    assert len(dom_loose_ids) >= 10, (
        f"expected at least 10 DOM-level loose signatures (catch tools whose <script> tags "
        f"get stripped by Firecrawl); got {len(dom_loose_ids)}: {dom_loose_ids}"
    )


def test_catalog_grew_to_at_least_45_entries():
    """Phase 2.1a-fix added DOM signatures; total catalog size should be 45+."""
    assert len(SIGNATURES) >= 45
