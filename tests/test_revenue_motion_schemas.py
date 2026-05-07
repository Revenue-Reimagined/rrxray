"""RevenueMotionData / JobPosting schema round-trip + validation."""
import json
from typing import get_args

import pytest
from pydantic import ValidationError

from rrxray.schemas.revenue_motion import JobPosting, RevenueMotionData, RoleCategory


def test_job_posting_minimal():
    j = JobPosting(
        title="Senior Account Executive",
        category="ae",
        source="company_careers",
    )
    assert j.title == "Senior Account Executive"
    assert j.category == "ae"
    assert j.source == "company_careers"
    assert j.url is None
    assert j.location is None


def test_job_posting_rejects_invalid_category():
    with pytest.raises(ValidationError):
        JobPosting(
            title="x", category="not_a_category",  # type: ignore[arg-type]
            source="company_careers",
        )


def test_job_posting_rejects_invalid_source():
    with pytest.raises(ValidationError):
        JobPosting(
            title="x", category="ae", source="not_a_source",  # type: ignore[arg-type]
        )


def test_revenue_motion_data_defaults_empty():
    d = RevenueMotionData()
    assert d.careers_page_url is None
    assert d.ats_platform is None
    assert d.open_roles == []
    assert d.role_counts == {}
    assert d.ae_to_sdr_ratio is None
    assert d.linkedin_employee_count is None
    assert d.linkedin_job_count is None
    assert d.findings == []
    assert d.gaps == []
    assert d.discovery_questions == []
    assert d.sources == []


def test_revenue_motion_data_round_trips():
    d = RevenueMotionData(
        careers_page_url="https://example.com/careers",
        ats_platform="lever",
        open_roles=[
            JobPosting(title="AE", category="ae", source="company_careers"),
            JobPosting(title="SDR", category="sdr", source="company_careers"),
        ],
        role_counts={"ae": 1, "sdr": 1},
        ae_to_sdr_ratio=1.0,
        linkedin_employee_count=247,
    )
    serialized = d.model_dump_json()
    restored = RevenueMotionData.model_validate(json.loads(serialized))
    assert restored.careers_page_url == "https://example.com/careers"
    assert restored.ats_platform == "lever"
    assert len(restored.open_roles) == 2
    assert restored.linkedin_employee_count == 247


def test_role_category_literal_includes_all_eight():
    """RoleCategory Literal must include all 8 categories named in the spec."""
    expected = {
        "ae", "sdr", "revops", "csm",
        "sales_leadership", "marketing_leadership",
        "marketing_ops", "other",
    }
    actual = set(get_args(RoleCategory))
    assert actual == expected, f"missing={expected - actual}, extra={actual - expected}"
