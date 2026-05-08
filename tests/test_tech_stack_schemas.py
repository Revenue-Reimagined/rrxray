"""TechStackData / DetectedTool schema round-trip + validation."""
import json
from typing import get_args

import pytest
from pydantic import ValidationError

from rrxray.schemas.tech_stack import Category, DetectedTool, TechStackData


def test_detected_tool_minimal():
    t = DetectedTool(
        name="HubSpot",
        category="marketing_automation",
        confidence="high",
        signature_id="hubspot:strict_js",
        matched_text="https://js.hs-scripts.com/12345.js",
    )
    assert t.name == "HubSpot"
    assert t.confidence == "high"


def test_detected_tool_rejects_invalid_category():
    with pytest.raises(ValidationError):
        DetectedTool(
            name="x",
            category="not_a_category",  # type: ignore[arg-type]
            confidence="high",
            signature_id="x",
            matched_text="x",
        )


def test_detected_tool_rejects_invalid_confidence():
    with pytest.raises(ValidationError):
        DetectedTool(
            name="x",
            category="analytics",
            confidence="medium",  # type: ignore[arg-type]
            signature_id="x",
            matched_text="x",
        )


def test_tech_stack_data_defaults_empty():
    d = TechStackData()
    assert d.detected_tools == []
    assert d.categories_observed == []
    assert d.categories_absent == []
    assert d.findings == []
    assert d.gaps == []
    assert d.discovery_questions == []
    assert d.sources == []


def test_tech_stack_data_round_trips_through_json():
    d = TechStackData(
        detected_tools=[
            DetectedTool(
                name="HubSpot", category="marketing_automation", confidence="high",
                signature_id="hubspot:strict_js", matched_text="js.hs-scripts.com/123.js",
            ),
        ],
        categories_observed=["marketing_automation"],
        categories_absent=["analytics", "tag_manager"],
        gaps=["No analytics detected"],
    )
    serialized = d.model_dump_json()
    restored = TechStackData.model_validate(json.loads(serialized))
    assert len(restored.detected_tools) == 1
    assert restored.detected_tools[0].name == "HubSpot"
    assert restored.categories_observed == ["marketing_automation"]


def test_category_literal_includes_all_nine():
    """Category Literal must include all 9 GTM categories named in the spec."""
    expected = {
        "analytics", "tag_manager", "marketing_automation", "chat",
        "product_analytics", "crm", "cdp", "ab_testing", "attribution",
    }
    actual = set(get_args(Category))
    assert actual == expected, f"Category mismatch: missing={expected - actual}, extra={actual - expected}"
    # Probe each one to confirm pydantic accepts it as a valid value
    for cat in get_args(Category):
        DetectedTool(
            name="probe", category=cat, confidence="high",
            signature_id="x", matched_text="x",
        )


def test_detected_tool_accepts_low_confidence():
    """Both 'high' and 'low' must be accepted as valid confidence values."""
    t = DetectedTool(
        name="HubSpot", category="marketing_automation", confidence="low",
        signature_id="hubspot:loose_form", matched_text="hsforms.net",
    )
    assert t.confidence == "low"
