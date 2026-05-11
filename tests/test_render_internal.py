"""Markdown renderer: pure XrayData -> str function with anonymize + voice filters."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from rrxray.rendering.markdown import render_internal
from rrxray.schemas.data import (
    CollectorOutputs,
    InputParams,
    ObservedGtmMotionNarrative,
    RunMetadata,
    SourceCitation,
    SynthesizerOutputs,
    XrayData,
)
from rrxray.schemas.pricing_packaging import PricingPackagingData, PricingTier
from rrxray.voice.anonymizer import AnonymityViolationError, Anonymizer
from rrxray.voice.rr_voice import VoicePostProcessor


def make_data(
    *,
    pricing: PricingPackagingData | None = None,
    narrative: ObservedGtmMotionNarrative | None = None,
) -> XrayData:
    return XrayData(
        domain="example.com",
        company_name="Example Inc.",
        run_metadata=RunMetadata(
            timestamp=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
            tool_version="0.1.0",
            modes_built=["internal"],
            model_used="claude-sonnet-4-6",
        ),
        inputs=InputParams(domain="example.com", mode="internal", model="claude-sonnet-4-6"),
        collectors=CollectorOutputs(pricing_packaging=pricing),
        synthesizers=SynthesizerOutputs(observed_gtm_motion=narrative),
    )


def test_full_skeleton_present():
    data = make_data()
    out = render_internal(data, Anonymizer(), VoicePostProcessor())
    for header in [
        "# GTM X-Ray™:",
        "## 1. Executive Summary",
        "## 2. Section A: Observed GTM Motion",
        "## 3. Section B: Observed Stability and Trajectory",
        "## 4. Section C: External Voice vs. Internal Voice",
        "## 5. Module Detail Appendix",
        "## 6. Discovery Questions",
        "## 7. Sources & Methodology",
    ]:
        assert header in out


def test_unavailable_module_renders_placeholder_string():
    data = make_data()
    out = render_internal(data, Anonymizer(), VoicePostProcessor())
    assert "[Module not available for this domain]" in out


def test_section_a_renders_narrative_when_present():
    narrative = ObservedGtmMotionNarrative(
        narrative_paragraphs=["The motion appears self-serve.", "Pricing is published."],
        gap_bullets=["Pricing has been static for 18 months"],
        findings=[], gaps=[], discovery_questions=["Have you tested price increases?"],
        model_used="claude-sonnet-4-6", cache_hit=False,
    )
    data = make_data(narrative=narrative)
    out = render_internal(data, Anonymizer(), VoicePostProcessor())
    assert "The motion appears self-serve." in out
    assert "→ Pricing has been static for 18 months" in out


def test_pricing_detail_renders_tiers():
    pricing = PricingPackagingData(
        has_public_pricing=True, is_contact_us_gated=False,
        current_pricing_url="https://example.com/pricing",
        current_tiers=[
            PricingTier(name="Starter", price="$0", cadence="month", notes=""),
            PricingTier(name="Pro", price="$50", cadence="per seat per month", notes=""),
        ],
    )
    data = make_data(pricing=pricing)
    out = render_internal(data, Anonymizer(), VoicePostProcessor())
    assert "| Starter |" in out
    assert "| Pro |" in out
    assert "$50" in out


def test_voice_collector_filter_substitutes():
    pricing = PricingPackagingData(
        has_public_pricing=True, is_contact_us_gated=False,
        current_pricing_url="https://example.com/pricing",
        current_tiers=[PricingTier(name="Pro", price="$50", cadence="month",
                                    notes="We leverage data to set prices.")],
    )
    data = make_data(pricing=pricing)
    voice = VoicePostProcessor()
    out = render_internal(data, Anonymizer(), voice)
    # "leverage" must not appear in rendered content; it is allowed in the Voice Adjustments
    # audit section where it documents the substitution (per plan T22 AC #4)
    body = out.split("### Voice Adjustments")[0]
    assert "leverage" not in body
    assert "use" in out  # substituted


def test_anonymize_filter_replaces_registered_name():
    narrative = ObservedGtmMotionNarrative(
        narrative_paragraphs=["Sarah Chen leads sales."],
        gap_bullets=["No SDR support"],
        findings=[], gaps=[], discovery_questions=[],
        model_used="x", cache_hit=False,
    )
    data = make_data(narrative=narrative)
    a = Anonymizer()
    a.register_individual("Sarah Chen", "the current VP of Sales")
    out = render_internal(data, a, VoicePostProcessor())
    assert "Sarah Chen" not in out
    assert "the current VP of Sales leads sales." in out


def test_sources_section_lists_all():
    pricing = PricingPackagingData(
        has_public_pricing=True, is_contact_us_gated=False,
        current_pricing_url="https://example.com/pricing",
    )
    data = make_data(pricing=pricing)
    data.sources = [SourceCitation(
        url="https://example.com/pricing",
        timestamp=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
        evidence_path="pricing_packaging/current.md",
    )]
    out = render_internal(data, Anonymizer(), VoicePostProcessor())
    assert "[https://example.com/pricing](https://example.com/pricing)" in out
    assert "evidence/pricing_packaging/current.md" in out


def test_voice_adjustments_section_present_when_substitutions_happened():
    pricing = PricingPackagingData(
        has_public_pricing=True, is_contact_us_gated=False,
        current_pricing_url="https://example.com/pricing",
        current_tiers=[PricingTier(
            name="Pro", price="$50", cadence="month",
            notes="We leverage data.",
        )],
    )
    data = make_data(pricing=pricing)
    voice = VoicePostProcessor()
    out = render_internal(data, Anonymizer(), voice)
    assert "### Voice Adjustments" in out
    assert "forbidden_word" in out


def test_known_limitations_section_present():
    data = make_data()
    out = render_internal(data, Anonymizer(), VoicePostProcessor())
    assert "### Known Limitations" in out
    assert "LinkedIn" in out


def test_render_raises_if_anonymizer_misses_a_registered_name(monkeypatch):
    """If the renderer's filter is bypassed and a registered name reaches the output, raise."""
    narrative = ObservedGtmMotionNarrative(
        narrative_paragraphs=["text without registered names"],
        gap_bullets=["x"],
        findings=[], gaps=[], discovery_questions=[],
        model_used="x", cache_hit=False,
    )
    data = make_data(narrative=narrative)
    a = Anonymizer()
    a.register_individual("Sarah Chen", "the VP")

    # Manually inject a name into the data after construction
    data.synthesizers.observed_gtm_motion.narrative_paragraphs[0] = "Sarah Chen leads."
    monkeypatch.setattr(a, "anonymize", lambda x: x)  # disable replacement

    with pytest.raises(AnonymityViolationError):
        render_internal(data, a, VoicePostProcessor())


def test_tech_stack_module_detail_renders_with_detections():
    """When tech_stack has detected_tools, the Tech Stack subsection renders the table."""
    from rrxray.schemas.tech_stack import DetectedTool, TechStackData

    tech = TechStackData(
        detected_tools=[
            DetectedTool(
                name="HubSpot", category="marketing_automation", confidence="high",
                signature_id="hubspot:strict_js", matched_text="js.hs-scripts.com/x.js",
            ),
            DetectedTool(
                name="Pendo", category="product_analytics", confidence="high",
                signature_id="pendo:strict_agent", matched_text="cdn.pendo.io",
            ),
        ],
        categories_observed=["marketing_automation", "product_analytics"],
        categories_absent=["analytics", "tag_manager", "chat", "crm", "cdp", "ab_testing", "attribution"],
    )
    data = make_data()
    data.collectors.tech_stack = tech
    out = render_internal(data, Anonymizer(), VoicePostProcessor())
    assert "### Tech Stack" in out
    assert "HubSpot" in out
    assert "Pendo" in out
    assert "marketing_automation" in out


def test_tech_stack_module_detail_omits_when_no_collector():
    """When tech_stack collector did not run, the Tech Stack subsection is absent."""
    data = make_data()
    out = render_internal(data, Anonymizer(), VoicePostProcessor())
    assert "### Tech Stack" not in out


def test_tech_stack_module_detail_renders_categories_lists():
    """categories_observed and categories_absent show up in render."""
    from rrxray.schemas.tech_stack import DetectedTool, TechStackData

    tech = TechStackData(
        detected_tools=[DetectedTool(
            name="HubSpot", category="marketing_automation", confidence="high",
            signature_id="hubspot:strict_js", matched_text="x",
        )],
        categories_observed=["marketing_automation"],
        categories_absent=["analytics", "crm"],
    )
    data = make_data()
    data.collectors.tech_stack = tech
    out = render_internal(data, Anonymizer(), VoicePostProcessor())
    assert "marketing_automation" in out
    assert "analytics" in out  # in absent list
    assert "crm" in out  # in absent list


def test_tech_stack_renders_findings_with_voice_collector_filter():
    """Findings text passes through voice_collector filter."""
    from rrxray.schemas._shared import Finding, SourceCitation
    from rrxray.schemas.tech_stack import DetectedTool, TechStackData

    tech = TechStackData(
        detected_tools=[DetectedTool(
            name="HubSpot", category="marketing_automation", confidence="high",
            signature_id="hubspot:strict_js", matched_text="x",
        )],
        findings=[Finding(
            text="We leverage marketing automation for nurture.",  # forbidden word
            source=SourceCitation(
                url="https://example.com",
                timestamp=datetime(2026, 5, 7, 12, 0, tzinfo=UTC),
            ),
        )],
    )
    data = make_data()
    data.collectors.tech_stack = tech
    out = render_internal(data, Anonymizer(), VoicePostProcessor())
    # Voice substitution: "leverage" becomes "use" in the body before Voice Adjustments
    body = out.split("### Voice Adjustments")[0]
    assert "leverage" not in body
    assert "use marketing automation" in body or "use" in body


def test_revenue_motion_module_detail_renders():
    from rrxray.schemas.revenue_motion import JobPosting, RevenueMotionData

    rm = RevenueMotionData(
        careers_page_url="https://example.com/careers",
        ats_platform="lever",
        open_roles=[
            JobPosting(title="Senior AE", category="ae", source="company_careers"),
            JobPosting(title="SDR", category="sdr", source="company_careers"),
        ],
        role_counts={"ae": 1, "sdr": 1},
        ae_to_sdr_ratio=1.0,
        linkedin_employee_count=247,
    )
    data = make_data()
    data.collectors.revenue_motion = rm
    out = render_internal(data, Anonymizer(), VoicePostProcessor())
    assert "### Revenue Motion" in out
    assert "Senior AE" in out
    assert "lever" in out.lower()
    assert "247" in out


def test_revenue_motion_module_detail_omits_when_no_collector():
    data = make_data()
    out = render_internal(data, Anonymizer(), VoicePostProcessor())
    assert "### Revenue Motion" not in out


def test_leadership_stability_module_detail_renders():
    """Module Detail Appendix renders Leadership Stability subsection with full data."""
    from datetime import UTC, date, datetime

    from rrxray.rendering.markdown import render_internal
    from rrxray.schemas.data import (
        CollectorOutputs,
        InputParams,
        RunMetadata,
        XrayData,
    )
    from rrxray.schemas.leadership_stability import (
        CurrentIncumbent,
        ExecAction,
        ExecChange,
        FounderTenure,
        LeadershipStabilityData,
        NameRegistration,
    )
    from rrxray.voice.anonymizer import Anonymizer
    from rrxray.voice.rr_voice import VoicePostProcessor

    anonymizer = Anonymizer()
    voice = VoicePostProcessor()

    ls_data = LeadershipStabilityData(
        exec_changes=[
            ExecChange(
                name="Jane Doe", role_canonical="cro", role_raw="CRO",
                action=ExecAction.HIRE,
                occurred_at=date(2025, 9, 1),
                press_url="https://example.com/p/1",
                press_title="Acme Names Jane Doe as CRO",
            ),
        ],
        current_incumbents=[
            CurrentIncumbent(name="Jane Doe", role_canonical="cro", role_raw="CRO"),
            CurrentIncumbent(name="Bob Smith", role_canonical="cmo", role_raw="CMO"),
        ],
        founder_tenure=FounderTenure(inferred_year=2018, source="about_page"),
        name_registrations=[
            NameRegistration(name="Jane Doe", role_descriptor="Acme's CRO", whitelist=True),
            NameRegistration(name="Bob Smith", role_descriptor="Acme's CMO", whitelist=False),
        ],
    )

    # Apply registrations to anonymizer (mirrors what pipeline does)
    for reg in ls_data.name_registrations:
        anonymizer.register_individual(reg.name, reg.role_descriptor)
        if reg.whitelist:
            anonymizer.whitelist_from_press(reg.name)

    data = XrayData(
        domain="example.com",
        run_metadata=RunMetadata(
            timestamp=datetime.now(UTC),
            tool_version="0.1",
            modes_built=["internal"],
            model_used="claude-sonnet-4-6",
        ),
        inputs=InputParams(domain="example.com"),
        collectors=CollectorOutputs(leadership_stability=ls_data),
    )

    rendered = render_internal(data, anonymizer, voice)

    assert "Leadership Stability" in rendered
    assert "Founder tenure" in rendered
    assert "Current incumbents" in rendered
    # Whitelisted name: passes through
    assert "Jane Doe" in rendered
    # Non-whitelisted LinkedIn-only name: replaced with role descriptor
    assert "Bob Smith" not in rendered
    assert "Acme's CMO" in rendered


def test_leadership_stability_module_detail_omits_when_no_collector():
    """Module Detail Appendix omits Leadership Stability section when collector is None."""
    from datetime import UTC, datetime

    from rrxray.rendering.markdown import render_internal
    from rrxray.schemas.data import (
        CollectorOutputs,
        InputParams,
        RunMetadata,
        XrayData,
    )
    from rrxray.voice.anonymizer import Anonymizer
    from rrxray.voice.rr_voice import VoicePostProcessor

    data = XrayData(
        domain="example.com",
        run_metadata=RunMetadata(
            timestamp=datetime.now(UTC),
            tool_version="0.1",
            modes_built=["internal"],
            model_used="claude-sonnet-4-6",
        ),
        inputs=InputParams(domain="example.com"),
        collectors=CollectorOutputs(),  # no leadership_stability
    )

    rendered = render_internal(data, Anonymizer(), VoicePostProcessor())
    assert "Leadership Stability" not in rendered
    assert "Founder tenure" not in rendered


def test_render_anonymizes_linkedin_names_preserves_press_names():
    """LinkedIn-only names get replaced; press-whitelisted names pass through."""
    from datetime import UTC, datetime

    from rrxray.rendering.markdown import render_internal
    from rrxray.schemas.data import (
        CollectorOutputs,
        InputParams,
        RunMetadata,
        XrayData,
    )
    from rrxray.schemas.leadership_stability import (
        CurrentIncumbent,
        LeadershipStabilityData,
        NameRegistration,
    )
    from rrxray.voice.anonymizer import Anonymizer
    from rrxray.voice.rr_voice import VoicePostProcessor

    anonymizer = Anonymizer()
    anonymizer.register_individual("Press Person", "Acme's CRO")
    anonymizer.whitelist_from_press("Press Person")
    anonymizer.register_individual("LinkedIn Person", "Acme's CMO")
    # NOT whitelisted

    ls = LeadershipStabilityData(
        current_incumbents=[
            CurrentIncumbent(name="Press Person", role_canonical="cro", role_raw="CRO"),
            CurrentIncumbent(name="LinkedIn Person", role_canonical="cmo", role_raw="CMO"),
        ],
        name_registrations=[
            NameRegistration(name="Press Person", role_descriptor="Acme's CRO", whitelist=True),
            NameRegistration(name="LinkedIn Person", role_descriptor="Acme's CMO", whitelist=False),
        ],
    )
    data = XrayData(
        domain="example.com",
        run_metadata=RunMetadata(
            timestamp=datetime.now(UTC),
            tool_version="0.1",
            modes_built=["internal"],
            model_used="claude-sonnet-4-6",
        ),
        inputs=InputParams(domain="example.com"),
        collectors=CollectorOutputs(leadership_stability=ls),
    )

    rendered = render_internal(data, anonymizer, VoicePostProcessor())
    assert "Press Person" in rendered
    assert "LinkedIn Person" not in rendered
    assert "Acme's CMO" in rendered


def test_synth_findings_render_in_section_b():
    """Synthesizer findings on observed_stability_trajectory render in Section B."""
    from datetime import UTC, datetime

    from rrxray.rendering.markdown import render_internal
    from rrxray.schemas._shared import Finding, SourceCitation
    from rrxray.schemas.data import (
        CollectorOutputs,
        InputParams,
        ObservedStabilityTrajectoryNarrative,
        RunMetadata,
        SynthesizerOutputs,
        XrayData,
    )
    from rrxray.voice.anonymizer import Anonymizer
    from rrxray.voice.rr_voice import VoicePostProcessor

    narrative = ObservedStabilityTrajectoryNarrative(
        narrative_paragraphs=["Stability appears mixed."],
        findings=[
            Finding(
                text="Recent CRO turnover suggests motion redesign in flight.",
                source=SourceCitation(
                    url="https://example.com/press/cro",
                    timestamp=datetime(2026, 5, 1, tzinfo=UTC),
                ),
            ),
        ],
        gaps=[],
        discovery_questions=[],
        model_used="claude-sonnet-4-6",
        cache_hit=False,
    )

    data = XrayData(
        domain="example.com",
        run_metadata=RunMetadata(
            timestamp=datetime.now(UTC),
            tool_version="0.1",
            modes_built=["internal"],
            model_used="claude-sonnet-4-6",
        ),
        inputs=InputParams(domain="example.com"),
        collectors=CollectorOutputs(),
        synthesizers=SynthesizerOutputs(observed_stability_trajectory=narrative),
    )

    rendered = render_internal(data, Anonymizer(), VoicePostProcessor())
    # Section B finding text appears in render
    assert "Recent CRO turnover suggests motion redesign in flight." in rendered
    # Source URL is linked
    assert "https://example.com/press/cro" in rendered


def test_em_dashes_absent_from_leadership_stability_detail():
    """Rendered Leadership Stability detail must not contain em-dash characters."""
    from datetime import UTC, datetime

    from rrxray.rendering.markdown import render_internal
    from rrxray.schemas.data import (
        CollectorOutputs,
        InputParams,
        RunMetadata,
        XrayData,
    )
    from rrxray.schemas.leadership_stability import (
        CurrentIncumbent,
        LeadershipStabilityData,
    )
    from rrxray.voice.anonymizer import Anonymizer
    from rrxray.voice.rr_voice import VoicePostProcessor

    # Minimal data: one incumbent with no linkedin_url (triggers former em-dash placeholder)
    ls = LeadershipStabilityData(
        current_incumbents=[
            CurrentIncumbent(
                name="x", role_canonical="cro", role_raw="CRO", linkedin_url=None,
            ),
        ],
    )
    data = XrayData(
        domain="example.com",
        run_metadata=RunMetadata(
            timestamp=datetime.now(UTC),
            tool_version="0.1",
            modes_built=["internal"],
            model_used="claude-sonnet-4-6",
        ),
        inputs=InputParams(domain="example.com"),
        collectors=CollectorOutputs(leadership_stability=ls),
    )

    rendered = render_internal(data, Anonymizer(), VoicePostProcessor())
    # Isolate the leadership stability section to avoid false positives from
    # other parts of the report
    ls_section = rendered.split("### Leadership Stability", 1)[1]
    # Drop trailing sections (anything after the next top-level Section header)
    ls_section = ls_section.split("\n## ", 1)[0]
    assert "—" not in ls_section


def test_leadership_stability_module_detail_renders_tenure_and_prior_employer():
    from datetime import UTC, datetime

    from rrxray.rendering.markdown import render_internal
    from rrxray.schemas.data import (
        CollectorOutputs,
        InputParams,
        RunMetadata,
        XrayData,
    )
    from rrxray.schemas.leadership_stability import (
        CurrentIncumbent,
        LeadershipEnrichmentMetadata,
        LeadershipStabilityData,
        NameRegistration,
    )
    from rrxray.voice.anonymizer import Anonymizer
    from rrxray.voice.rr_voice import VoicePostProcessor

    anonymizer = Anonymizer()
    anonymizer.register_individual("Jane Doe", "Acme's CRO")
    # NOT whitelisted (PDL-sourced, not press)

    ls = LeadershipStabilityData(
        current_incumbents=[
            CurrentIncumbent(
                name="Jane Doe", role_canonical="cro", role_raw="CRO",
                tenure_months=14, years_at_company=14,
                prior_employer="Salesforce", prior_role="VP of Enterprise Sales",
            ),
        ],
        name_registrations=[
            NameRegistration(name="Jane Doe", role_descriptor="Acme's CRO", whitelist=False),
        ],
        enrichment_metadata=LeadershipEnrichmentMetadata(
            spend_dollars=2.40, aborted_reason="completed",
        ),
    )
    data = XrayData(
        domain="acme.com",
        run_metadata=RunMetadata(
            timestamp=datetime.now(UTC), tool_version="0.1",
            modes_built=["internal"], model_used="claude-opus-4-7",
        ),
        inputs=InputParams(domain="acme.com"),
        collectors=CollectorOutputs(leadership_stability=ls),
    )
    rendered = render_internal(data, anonymizer, VoicePostProcessor())

    # Tenure column rendered
    assert "14 months" in rendered or "~14 months" in rendered
    # Prior employer shown
    assert "Salesforce" in rendered
    # Name anonymized (not whitelisted)
    assert "Jane Doe" not in rendered
    assert "Acme's CRO" in rendered


def test_module_detail_renders_enrichment_metadata_line():
    from datetime import UTC, datetime

    from rrxray.rendering.markdown import render_internal
    from rrxray.schemas.data import (
        CollectorOutputs,
        InputParams,
        RunMetadata,
        XrayData,
    )
    from rrxray.schemas.leadership_stability import (
        LeadershipEnrichmentMetadata,
        LeadershipStabilityData,
    )
    from rrxray.voice.anonymizer import Anonymizer
    from rrxray.voice.rr_voice import VoicePostProcessor

    ls = LeadershipStabilityData(
        enrichment_metadata=LeadershipEnrichmentMetadata(
            spend_dollars=2.83, aborted_reason="cost_cap",
        ),
    )
    data = XrayData(
        domain="acme.com",
        run_metadata=RunMetadata(
            timestamp=datetime.now(UTC), tool_version="0.1",
            modes_built=["internal"], model_used="claude-opus-4-7",
        ),
        inputs=InputParams(domain="acme.com"),
        collectors=CollectorOutputs(leadership_stability=ls),
    )
    rendered = render_internal(data, Anonymizer(), VoicePostProcessor())

    assert "$2.83" in rendered or "2.83" in rendered
    assert "cost_cap" in rendered
