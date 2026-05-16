"""Schema round-trip and validation tests."""
import json
from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from rrxray.schemas.data import (
    Finding,
    InputParams,
    ModuleFailure,
    RunMetadata,
    VoiceEvent,
    XrayData,
)
from rrxray.schemas.pricing_packaging import (
    PricingChange,
    PricingPackagingData,
    PricingTier,
)


def test_xray_data_round_trips_through_json():
    data = XrayData(
        domain="example.com",
        run_metadata=RunMetadata(
            timestamp=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
            tool_version="0.1.0",
            modes_built=["internal"],
            model_used="claude-sonnet-4-6",
        ),
        inputs=InputParams(domain="example.com", mode="internal", model="claude-sonnet-4-6"),
    )
    serialized = data.model_dump_json()
    restored = XrayData.model_validate(json.loads(serialized))
    assert restored.domain == "example.com"
    assert restored.collectors.pricing_packaging is None
    assert restored.synthesizers.observed_gtm_motion is None
    assert restored.voice_log == []
    assert restored.failures == []


def test_pricing_packaging_data_validates_change_kinds():
    p = PricingPackagingData(
        has_public_pricing=True,
        is_contact_us_gated=False,
        current_pricing_url="https://example.com/pricing",
        current_tiers=[PricingTier(name="Pro", price="$50", cadence="per seat per month", notes="")],
        detected_changes=[
            PricingChange(
                date_observed=date(2025, 11, 1),
                kind="price_increased",
                before="$40",
                after="$50",
            ),
        ],
    )
    assert p.detected_changes[0].kind == "price_increased"


def test_pricing_change_rejects_invalid_kind():
    with pytest.raises(ValidationError):
        PricingChange(date_observed=date.today(), kind="invalid_kind", before="x", after="y")


def test_finding_requires_source():
    with pytest.raises(ValidationError):
        Finding(text="something")  # type: ignore[call-arg]


def test_module_failure_serializable():
    f = ModuleFailure(module="pricing_packaging", kind="collector", error="boom", traceback="...")
    json.dumps(f.model_dump(mode="json"))


def test_voice_event_action_constrained():
    e = VoiceEvent(rule="forbidden_word", original="leverage", replacement="use",
                   context="Section A para 0", action="substitute")
    assert e.action == "substitute"
    with pytest.raises(ValidationError):
        VoiceEvent(rule="x", original="y", replacement=None, context="z", action="bogus")  # type: ignore[arg-type]


def test_collector_outputs_has_tech_stack_field():
    """CollectorOutputs must accept a tech_stack field."""
    from rrxray.schemas.data import CollectorOutputs
    from rrxray.schemas.tech_stack import TechStackData

    co = CollectorOutputs(tech_stack=TechStackData())
    assert co.tech_stack is not None
    assert isinstance(co.tech_stack, TechStackData)


def test_collector_outputs_tech_stack_defaults_none():
    from rrxray.schemas.data import CollectorOutputs

    co = CollectorOutputs()
    assert co.tech_stack is None


def test_collector_outputs_tech_stack_round_trips():
    from rrxray.schemas.data import CollectorOutputs
    from rrxray.schemas.tech_stack import DetectedTool, TechStackData

    co = CollectorOutputs(tech_stack=TechStackData(
        detected_tools=[DetectedTool(
            name="HubSpot", category="marketing_automation", confidence="high",
            signature_id="hubspot:strict_js", matched_text="x",
        )],
    ))
    serialized = co.model_dump_json()
    restored = CollectorOutputs.model_validate(json.loads(serialized))
    assert restored.tech_stack is not None
    assert restored.tech_stack.detected_tools[0].name == "HubSpot"


def test_collector_outputs_has_revenue_motion_field():
    """CollectorOutputs must accept a revenue_motion field."""
    from rrxray.schemas.data import CollectorOutputs
    from rrxray.schemas.revenue_motion import RevenueMotionData

    co = CollectorOutputs(revenue_motion=RevenueMotionData())
    assert co.revenue_motion is not None


def test_collector_outputs_revenue_motion_defaults_none():
    from rrxray.schemas.data import CollectorOutputs
    co = CollectorOutputs()
    assert co.revenue_motion is None


def test_collector_outputs_all_three_collectors_round_trip():
    import json

    from rrxray.schemas.data import CollectorOutputs
    from rrxray.schemas.pricing_packaging import PricingPackagingData
    from rrxray.schemas.revenue_motion import JobPosting, RevenueMotionData
    from rrxray.schemas.tech_stack import DetectedTool, TechStackData

    co = CollectorOutputs(
        pricing_packaging=PricingPackagingData(
            has_public_pricing=True, is_contact_us_gated=False,
            current_pricing_url="https://example.com/pricing",
        ),
        tech_stack=TechStackData(
            detected_tools=[DetectedTool(
                name="HubSpot", category="marketing_automation", confidence="high",
                signature_id="hubspot:strict_js", matched_text="x",
            )],
        ),
        revenue_motion=RevenueMotionData(
            careers_page_url="https://example.com/careers",
            open_roles=[JobPosting(title="AE", category="ae", source="company_careers")],
        ),
    )
    serialized = co.model_dump_json()
    restored = CollectorOutputs.model_validate(json.loads(serialized))
    assert restored.pricing_packaging is not None
    assert restored.tech_stack is not None
    assert restored.revenue_motion is not None
    assert restored.revenue_motion.open_roles[0].title == "AE"


def test_collector_outputs_has_content_demand_field():
    """CollectorOutputs must accept a content_demand field."""
    from rrxray.schemas.content_demand import ContentDemandData
    from rrxray.schemas.data import CollectorOutputs

    co = CollectorOutputs(content_demand=ContentDemandData())
    assert co.content_demand is not None


def test_collector_outputs_content_demand_defaults_none():
    from rrxray.schemas.data import CollectorOutputs
    co = CollectorOutputs()
    assert co.content_demand is None


def test_collector_outputs_four_section_a_collectors_round_trip():
    import json

    from rrxray.schemas.content_demand import BlogPost, ContentDemandData
    from rrxray.schemas.data import CollectorOutputs
    from rrxray.schemas.pricing_packaging import PricingPackagingData
    from rrxray.schemas.revenue_motion import JobPosting, RevenueMotionData
    from rrxray.schemas.tech_stack import DetectedTool, TechStackData

    co = CollectorOutputs(
        pricing_packaging=PricingPackagingData(
            has_public_pricing=True, is_contact_us_gated=False,
            current_pricing_url="https://example.com/pricing",
        ),
        tech_stack=TechStackData(
            detected_tools=[DetectedTool(
                name="HubSpot", category="marketing_automation", confidence="high",
                signature_id="hubspot:strict_js", matched_text="x",
            )],
        ),
        revenue_motion=RevenueMotionData(
            careers_page_url="https://example.com/careers",
            open_roles=[JobPosting(title="AE", category="ae", source="company_careers")],
        ),
        content_demand=ContentDemandData(
            blog_index_url="https://example.com/blog",
            blog_posts=[BlogPost(title="The Future of X", category="thought_leadership")],
        ),
    )
    serialized = co.model_dump_json()
    restored = CollectorOutputs.model_validate(json.loads(serialized))
    assert restored.content_demand is not None
    assert restored.content_demand.blog_posts[0].title == "The Future of X"


def test_collector_outputs_funding_trajectory_field():
    from rrxray.schemas.data import CollectorOutputs
    from rrxray.schemas.funding_trajectory import FundingTrajectoryData
    out = CollectorOutputs()
    assert out.funding_trajectory is None
    data = FundingTrajectoryData(implied_stage="early_growth")
    out.funding_trajectory = data
    assert out.funding_trajectory.implied_stage == "early_growth"


def test_xraydata_round_trips_funding_trajectory():
    from rrxray.schemas.funding_trajectory import FundingRound, FundingTrajectoryData
    from rrxray.schemas.data import CollectorOutputs
    r = FundingRound(series="series_b", amount_usd_millions=25.0, source_url="https://x", source_type="crunchbase")
    ft = FundingTrajectoryData(rounds=[r], implied_stage="early_growth")
    out = CollectorOutputs(funding_trajectory=ft)
    dumped = out.model_dump_json()
    restored = CollectorOutputs.model_validate_json(dumped)
    assert restored.funding_trajectory.implied_stage == "early_growth"
    assert len(restored.funding_trajectory.rounds) == 1
