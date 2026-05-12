"""Schema round-trip + validation for leadership_stability data shapes."""
from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from rrxray.schemas.leadership_stability import (
    CurrentIncumbent,
    ExecAction,
    ExecChange,
    FounderTenure,
    LeadershipStabilityData,
    NameRegistration,
)


def test_exec_change_minimal():
    e = ExecChange(
        name="Jane Doe",
        role_canonical="cro",
        role_raw="Chief Revenue Officer",
        action=ExecAction.HIRE,
        press_url="https://example.com/press/1",
        press_title="Acme Names Jane Doe as CRO",
    )
    assert e.name == "Jane Doe"
    assert e.action == ExecAction.HIRE
    assert e.occurred_at is None


def test_exec_change_validates_canonical_role():
    with pytest.raises(ValidationError):
        ExecChange(
            name="x",
            role_canonical="not_a_role",  # type: ignore[arg-type]
            role_raw="x",
            action=ExecAction.HIRE,
            press_url="x",
            press_title="x",
        )


def test_current_incumbent_default_high_confidence():
    c = CurrentIncumbent(name="Bob", role_canonical="cmo", role_raw="CMO")
    assert c.confidence == "high"


def test_founder_tenure_default_unknown_source():
    f = FounderTenure()
    assert f.source == "unknown"
    assert f.inferred_year is None


def test_name_registration_default_whitelist_false():
    """Default whitelist is False (safer default) per spec."""
    n = NameRegistration(name="Bob Smith", role_descriptor="Acme's CMO")
    assert n.whitelist is False


def test_leadership_stability_data_defaults_empty():
    d = LeadershipStabilityData()
    assert d.exec_changes == []
    assert d.current_incumbents == []
    assert d.founder_tenure is None
    assert d.name_registrations == []
    assert d.findings == []
    assert d.gaps == []
    assert d.discovery_questions == []
    assert d.sources == []


def test_leadership_stability_data_round_trips():
    d = LeadershipStabilityData(
        exec_changes=[
            ExecChange(
                name="Jane Doe",
                role_canonical="cro",
                role_raw="Chief Revenue Officer",
                action=ExecAction.HIRE,
                press_url="https://example.com/p/1",
                press_title="Acme Names Jane Doe as CRO",
            ),
        ],
        current_incumbents=[
            CurrentIncumbent(name="Jane Doe", role_canonical="cro", role_raw="CRO", confidence="high"),
        ],
        founder_tenure=FounderTenure(inferred_year=2018, source="about_page", raw_evidence="Founded in 2018"),
        name_registrations=[
            NameRegistration(name="Jane Doe", role_descriptor="Acme's CRO", whitelist=True),
        ],
    )
    serialized = d.model_dump_json()
    restored = LeadershipStabilityData.model_validate(json.loads(serialized))
    assert len(restored.exec_changes) == 1
    assert restored.exec_changes[0].name == "Jane Doe"
    assert restored.founder_tenure.inferred_year == 2018
    assert restored.name_registrations[0].whitelist is True


def test_current_incumbent_enrichment_fields_default_none():
    """Phase 2.2-deep: tenure_months / years_at_company / prior_employer / prior_role default to None."""
    from rrxray.schemas.leadership_stability import CurrentIncumbent
    c = CurrentIncumbent(name="Jane", role_canonical="cro", role_raw="CRO")
    assert c.tenure_months is None
    assert c.years_at_company is None
    assert c.prior_employer is None
    assert c.prior_role is None


def test_current_incumbent_round_trips_with_enrichment_fields():
    import json

    from rrxray.schemas.leadership_stability import CurrentIncumbent
    c = CurrentIncumbent(
        name="Jane", role_canonical="cro", role_raw="CRO",
        tenure_months=14, years_at_company=14,
        prior_employer="Salesforce", prior_role="VP of Enterprise Sales",
    )
    restored = CurrentIncumbent.model_validate(json.loads(c.model_dump_json()))
    assert restored.tenure_months == 14
    assert restored.prior_employer == "Salesforce"
    assert restored.prior_role == "VP of Enterprise Sales"


def test_exec_change_enrichment_fields_default_none():
    from rrxray.schemas.leadership_stability import ExecAction, ExecChange
    e = ExecChange(
        name="Jane", role_canonical="cro", role_raw="CRO",
        action=ExecAction.HIRE, press_url="x", press_title="y",
    )
    assert e.prior_employer is None
    assert e.prior_role is None
    assert e.years_at_company is None


def test_leadership_enrichment_metadata_default_disabled():
    from rrxray.schemas.leadership_stability import LeadershipEnrichmentMetadata
    m = LeadershipEnrichmentMetadata()
    assert m.spend_dollars == 0.0
    assert m.aborted_reason == "disabled"


def test_leadership_enrichment_metadata_accepts_all_aborted_reasons():
    import pytest
    from pydantic import ValidationError

    from rrxray.schemas.leadership_stability import LeadershipEnrichmentMetadata
    for reason in ["completed", "cost_cap", "circuit_breaker", "disabled"]:
        m = LeadershipEnrichmentMetadata(aborted_reason=reason)
        assert m.aborted_reason == reason
    with pytest.raises(ValidationError):
        LeadershipEnrichmentMetadata(aborted_reason="invalid_value")


def test_leadership_stability_data_round_trips_with_enrichment_metadata():
    import json

    from rrxray.schemas.leadership_stability import (
        LeadershipEnrichmentMetadata,
        LeadershipStabilityData,
    )
    d = LeadershipStabilityData(
        enrichment_metadata=LeadershipEnrichmentMetadata(
            spend_dollars=2.40, aborted_reason="completed",
        ),
    )
    restored = LeadershipStabilityData.model_validate(json.loads(d.model_dump_json()))
    assert restored.enrichment_metadata.spend_dollars == 2.40
    assert restored.enrichment_metadata.aborted_reason == "completed"
