"""LeadershipEnrichment: orchestrates PDL Search → Enrich per role with cost cap + circuit breaker."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from rrxray.schemas.leadership_stability import ExecAction, ExecChange
from rrxray.services.leadership_enrichment import (
    EnrichedLeadership,
    LeadershipEnrichment,
    _years_at_company,
)
from rrxray.services.pdl_client import (
    PDLEnrichment,
    PDLError,
    PDLSearchResult,
)

LEADERSHIP_ROLES_FIXTURE = [
    ("ceo", ["CEO", "Chief Executive Officer"]),
    ("cro", ["CRO", "Chief Revenue Officer"]),
    ("vp_sales", ["VP Sales", "VP of Sales"]),
]


@pytest.fixture
def fake_pdl():
    pdl = MagicMock()
    pdl.search_people = AsyncMock()
    pdl.enrich_person = AsyncMock()
    return pdl


def _search_result(name, linkedin_url, title="CRO", score=0.9):
    return PDLSearchResult(
        full_name=name, linkedin_url=linkedin_url,
        current_title=title, match_score=score,
        job_company_name="Acme", job_start_date="2024-03-01",
    )


def _enrichment(name, linkedin_url, start_date="2024-03-01", prior_company="Salesforce"):
    return PDLEnrichment(
        full_name=name, linkedin_url=linkedin_url,
        current_title="Chief Revenue Officer",
        job_company_name="Acme", job_start_date=start_date,
        previous_companies=[prior_company] if prior_company else [],
        previous_titles=["VP of Enterprise Sales"] if prior_company else [],
        experience=[
            {"company": {"name": "Acme"}, "title": {"name": "Chief Revenue Officer"},
             "start_date": start_date, "end_date": None},
        ] + ([{"company": {"name": prior_company}, "title": {"name": "VP of Enterprise Sales"},
              "start_date": "2020-01-01", "end_date": "2024-02-29"}] if prior_company else []),
    )


def test_find_and_enrich_incumbents_runs_search_then_enrich_per_role(fake_pdl):
    fake_pdl.search_people.side_effect = [
        [],  # no CEO
        [_search_result("Jane Doe", "https://www.linkedin.com/in/jane-doe-cro")],
        [],  # no VP Sales
    ]
    fake_pdl.enrich_person.return_value = _enrichment(
        "Jane Doe", "https://www.linkedin.com/in/jane-doe-cro",
    )

    orch = LeadershipEnrichment(pdl=fake_pdl, cost_cap_dollars=5.0)
    result = asyncio.run(orch.find_and_enrich_incumbents(
        company_name="Acme", company_domain="acme.com",
        role_canonicals=LEADERSHIP_ROLES_FIXTURE,
    ))

    assert isinstance(result, EnrichedLeadership)
    assert fake_pdl.search_people.call_count == 3
    assert fake_pdl.enrich_person.call_count == 1
    assert len(result.incumbents) == 1
    inc = result.incumbents[0]
    assert inc.name == "Jane Doe"
    assert inc.role_canonical == "cro"
    assert inc.prior_employer == "Salesforce"
    assert result.aborted_reason == "completed"
    # 3 searches x 0.20 + 1 enrich x 0.20 = 0.80
    assert abs(result.spend_dollars - 0.80) < 0.01


def test_find_and_enrich_incumbents_dedupes_same_linkedin_across_roles(fake_pdl):
    # Same person returned for both ceo + founder queries
    same_url = "https://www.linkedin.com/in/founder-ceo"
    fake_pdl.search_people.side_effect = [
        [_search_result("Founder Person", same_url, title="CEO and Founder")],  # ceo
        [_search_result("Founder Person", same_url, title="CEO and Founder")],  # founder
    ]
    fake_pdl.enrich_person.return_value = _enrichment(
        "Founder Person", same_url, prior_company=None,
    )

    orch = LeadershipEnrichment(pdl=fake_pdl, cost_cap_dollars=5.0)
    result = asyncio.run(orch.find_and_enrich_incumbents(
        company_name="Acme", company_domain="acme.com",
        role_canonicals=[("ceo", ["CEO"]), ("founder", ["Founder"])],
    ))

    # Two incumbents (one per role) but only ONE enrichment call (deduped by linkedin_url)
    assert len(result.incumbents) == 2
    assert {i.role_canonical for i in result.incumbents} == {"ceo", "founder"}
    assert fake_pdl.enrich_person.call_count == 1


def test_find_and_enrich_incumbents_continues_on_per_role_failure(fake_pdl):
    fake_pdl.search_people.side_effect = [
        PDLError("simulated search failure for ceo"),
        [_search_result("Jane Doe", "https://www.linkedin.com/in/jane-doe-cro")],
        [],
    ]
    fake_pdl.enrich_person.return_value = _enrichment(
        "Jane Doe", "https://www.linkedin.com/in/jane-doe-cro",
    )

    orch = LeadershipEnrichment(pdl=fake_pdl, cost_cap_dollars=5.0)
    result = asyncio.run(orch.find_and_enrich_incumbents(
        company_name="Acme", company_domain="acme.com",
        role_canonicals=LEADERSHIP_ROLES_FIXTURE,
    ))

    # CEO failure logged; CRO succeeded; VP Sales empty. Circuit breaker did not trip (only 1 failure).
    assert len(result.incumbents) == 1
    assert result.incumbents[0].role_canonical == "cro"
    assert result.aborted_reason == "completed"


def test_cost_cap_halts_further_calls_preserves_prior_data(fake_pdl):
    # Each search costs 0.20; cap at 0.50 allows 2 searches before halt
    fake_pdl.search_people.side_effect = [
        [_search_result("A", "https://www.linkedin.com/in/a")],
        [_search_result("B", "https://www.linkedin.com/in/b")],
        # Third search should be skipped due to cap
    ]
    fake_pdl.enrich_person.return_value = _enrichment("A", "https://www.linkedin.com/in/a")

    orch = LeadershipEnrichment(pdl=fake_pdl, cost_cap_dollars=0.50)
    result = asyncio.run(orch.find_and_enrich_incumbents(
        company_name="Acme", company_domain="acme.com",
        role_canonicals=LEADERSHIP_ROLES_FIXTURE,
    ))

    # 2 searches x 0.20 = 0.40; next search would be 0.60 > cap -> skipped
    assert fake_pdl.search_people.call_count == 2
    assert result.aborted_reason == "cost_cap"
    # We still have whatever incumbents the first 2 searches yielded
    assert len(result.incumbents) >= 1


def test_circuit_breaker_opens_after_three_consecutive_failures(fake_pdl):
    fake_pdl.search_people.side_effect = [
        PDLError("fail 1"),
        PDLError("fail 2"),
        PDLError("fail 3"),
        # 4th call should be short-circuited; mock would return [] if reached
        [_search_result("D", "https://www.linkedin.com/in/d")],
    ]

    orch = LeadershipEnrichment(pdl=fake_pdl, cost_cap_dollars=5.0)
    role_set = [
        ("ceo", ["CEO"]), ("cro", ["CRO"]),
        ("vp_sales", ["VP Sales"]), ("cmo", ["CMO"]),
    ]
    result = asyncio.run(orch.find_and_enrich_incumbents(
        company_name="Acme", company_domain="acme.com",
        role_canonicals=role_set,
    ))

    # 3 failures trip the breaker; 4th call never happens
    assert fake_pdl.search_people.call_count == 3
    assert result.aborted_reason == "circuit_breaker"
    assert result.incumbents == []


def test_empty_match_does_not_increment_failure_counter(fake_pdl):
    fake_pdl.search_people.side_effect = [
        [],  # empty, NOT a failure
        [],
        [],
        [_search_result("D", "https://www.linkedin.com/in/d")],
    ]
    fake_pdl.enrich_person.return_value = _enrichment("D", "https://www.linkedin.com/in/d")

    orch = LeadershipEnrichment(pdl=fake_pdl, cost_cap_dollars=5.0)
    role_set = [
        ("ceo", ["CEO"]), ("cro", ["CRO"]),
        ("vp_sales", ["VP Sales"]), ("cmo", ["CMO"]),
    ]
    result = asyncio.run(orch.find_and_enrich_incumbents(
        company_name="Acme", company_domain="acme.com",
        role_canonicals=role_set,
    ))

    # 4 searches all complete; circuit breaker does NOT trip (empty result != failure)
    assert fake_pdl.search_people.call_count == 4
    assert result.aborted_reason == "completed"
    assert len(result.incumbents) == 1


def test_enrich_press_change_names_shares_cost_cap_with_incumbent_path(fake_pdl):
    # Cap allows 1 enrich (0.20) after incumbent path
    fake_pdl.enrich_person.side_effect = [
        _enrichment("Jane", "https://www.linkedin.com/in/jane"),
        # Second enrich would exceed cap if cap=0.20 and prior_spend=0
    ]

    orch = LeadershipEnrichment(pdl=fake_pdl, cost_cap_dollars=0.20)
    changes = [
        ExecChange(name="Jane", role_canonical="cro", role_raw="CRO",
                   action=ExecAction.HIRE, press_url="u1", press_title="t1"),
        ExecChange(name="Bob", role_canonical="cmo", role_raw="CMO",
                   action=ExecAction.HIRE, press_url="u2", press_title="t2"),
    ]
    enriched = asyncio.run(orch.enrich_press_change_names(
        exec_changes=changes, company_domain="acme.com",
    ))

    # First call hit cap; second skipped
    assert fake_pdl.enrich_person.call_count == 1
    assert enriched[0].prior_employer == "Salesforce"
    assert enriched[1].prior_employer is None  # not enriched (cap)


def test_enrich_press_change_names_returns_unmutated_on_no_pdl_match(fake_pdl):
    fake_pdl.enrich_person.return_value = None  # PDL no-match

    orch = LeadershipEnrichment(pdl=fake_pdl, cost_cap_dollars=5.0)
    changes = [ExecChange(
        name="Unknown", role_canonical="cro", role_raw="CRO",
        action=ExecAction.HIRE, press_url="u", press_title="t",
    )]
    enriched = asyncio.run(orch.enrich_press_change_names(
        exec_changes=changes, company_domain="acme.com",
    ))

    assert enriched[0].prior_employer is None
    assert enriched[0].name == "Unknown"


def test_years_at_company_ignores_experience_with_empty_website():
    """`"" in "anything"` is True, so the prior substring-match treated
    every experience entry with empty `company.website` as a match for
    the prospect's domain — pulling in older tenures and inflating
    years_at_company. Tighten the match: empty website must NOT match.

    Construct a PDLEnrichment with one OLD experience entry that has
    `company.website=""` (would falsely match under substring rule) and
    one CURRENT entry whose website explicitly matches `acme.com`. The
    correct years_at_company must come from the matching entry only."""
    enr = PDLEnrichment(
        full_name="Test",
        linkedin_url="https://example.com/x",
        current_title="CRO",
        job_company_name="Acme",
        job_start_date="2024-03-01",
        experience=[
            # Old role with empty website. Under the buggy substring rule
            # this falsely matches acme.com and earliest_start collapses
            # to 2010-01-01 → inflated tenure ~15 years.
            {
                "company": {"name": "Old Company", "website": ""},
                "title": {"name": "VP of Sales"},
                "start_date": "2010-01-01",
                "end_date": "2020-12-31",
            },
            # Current role at Acme with a proper website.
            {
                "company": {"name": "Acme", "website": "acme.com"},
                "title": {"name": "CRO"},
                "start_date": "2024-03-01",
                "end_date": None,
            },
        ],
    )

    years = _years_at_company(enr, "acme.com")
    # Should be derived from the 2024-03-01 entry only (~1-2 years as of
    # 2026-05-11), NOT inflated to 15+ years by the empty-website match.
    assert years is not None
    assert years < 5, (
        f"years_at_company={years} — buggy empty-website match inflated tenure"
    )


def test_years_at_company_matches_only_on_normalized_bare_domain():
    """Match should normalize protocol/www/trailing slash on both sides,
    then compare equal. Substring matches that would have falsely
    matched (e.g. `acme.com` substring inside `notacme.com`) should not."""
    enr = PDLEnrichment(
        full_name="Test",
        linkedin_url="https://example.com/x",
        current_title="CRO",
        job_company_name="Acme",
        job_start_date="2024-03-01",
        experience=[
            # False-positive substring: 'acme.com' is a substring of 'notacme.com'
            {
                "company": {"name": "Not Acme", "website": "notacme.com"},
                "title": {"name": "Other Role"},
                "start_date": "2010-01-01",
                "end_date": "2020-12-31",
            },
            # Legit match w/ protocol + www prefix
            {
                "company": {"name": "Acme", "website": "https://www.acme.com/"},
                "title": {"name": "CRO"},
                "start_date": "2024-03-01",
                "end_date": None,
            },
        ],
    )
    years = _years_at_company(enr, "acme.com")
    assert years is not None
    assert years < 5


def test_enrich_press_change_names_circuit_break_with_duplicate_changes(fake_pdl):
    """Pydantic BaseModel.__eq__ is field-equality, so two identical
    ExecChange instances compare equal. The previous implementation
    used `exec_changes.index(change) + 1` to slice "remaining
    unprocessed" on circuit-break — `.index()` returns the *first*
    matching index, so the slice was wrong when duplicates appeared.

    Trip the circuit breaker partway through a list whose first three
    entries are identical, and assert the resulting "remaining" tail
    is sliced from the actual position, not the first match."""
    # Two identical changes at positions 0 and 1, then unique changes at 2..4
    dup_change = ExecChange(
        name="Dup Person", role_canonical="cro", role_raw="CRO",
        action=ExecAction.HIRE, press_url="u-dup", press_title="t-dup",
    )
    unique_changes = [
        ExecChange(
            name=f"Unique {i}", role_canonical="cro", role_raw="CRO",
            action=ExecAction.HIRE, press_url=f"u-{i}", press_title=f"t-{i}",
        )
        for i in range(3)
    ]
    # exec_changes = [dup, dup, unique0, unique1, unique2]
    # We expect 3 failures starting from idx=0, tripping the breaker after
    # processing change at idx=2 (the 3rd consecutive failure). The bug:
    # at idx=2, `enriched` currently has the failed-and-appended entry, and
    # the buggy "remaining" slice starts at exec_changes.index(unique0)+1
    # = 3. That happens to be correct for unique0 (the first occurrence),
    # so to actually expose the bug we need the *failing* change to be a
    # duplicate.
    exec_changes = [dup_change, dup_change, dup_change, unique_changes[0], unique_changes[1]]
    fake_pdl.enrich_person.side_effect = [
        PDLError("fail 1"),
        PDLError("fail 2"),
        PDLError("fail 3"),
        # Circuit should be tripped by now; this would only be called if the bug let it through
        None,
        None,
    ]

    orch = LeadershipEnrichment(pdl=fake_pdl, cost_cap_dollars=5.0)
    enriched = asyncio.run(orch.enrich_press_change_names(
        exec_changes=exec_changes, company_domain="acme.com",
    ))

    # Circuit breaker tripped at the 3rd failure (idx=2). Expected behavior:
    # the failing change at idx=2 was appended, and the remaining
    # exec_changes[3:] = [unique_changes[0], unique_changes[1]] are copied
    # over unmutated.
    assert len(enriched) == 5, (
        f"Expected 5 entries after circuit-break (3 failed + 2 unprocessed), "
        f"got {len(enriched)}. The .index(change) bug returns the index of the "
        f"first duplicate, producing a wrong slice."
    )
    # Last two entries must be the unique changes in original order
    assert enriched[3].name == "Unique 0"
    assert enriched[4].name == "Unique 1"
    # Only the 3 attempted calls happened (4th and 5th never reached)
    assert fake_pdl.enrich_person.call_count == 3


def test_enrichment_metadata_records_spend_dollars(fake_pdl):
    fake_pdl.search_people.return_value = [
        _search_result("Jane", "https://www.linkedin.com/in/jane"),
    ]
    fake_pdl.enrich_person.return_value = _enrichment(
        "Jane", "https://www.linkedin.com/in/jane",
    )

    orch = LeadershipEnrichment(pdl=fake_pdl, cost_cap_dollars=5.0)
    asyncio.run(orch.find_and_enrich_incumbents(
        company_name="Acme", company_domain="acme.com",
        role_canonicals=[("cro", ["CRO"])],
    ))

    meta = orch.metadata
    # 1 search (0.20) + 1 enrich (0.20) = 0.40
    assert abs(meta.spend_dollars - 0.40) < 0.01
    assert meta.aborted_reason == "completed"
