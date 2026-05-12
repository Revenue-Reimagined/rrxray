"""PDLClient: thin async wrapper around peopledatalabs-python for Search + Enrichment."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from rrxray.services.cache import DiskCache
from rrxray.services.pdl_client import (
    PDLClient,
    PDLEnrichment,
    PDLError,
)

FIXTURES = Path(__file__).parent / "fixtures" / "synthetic" / "leadership_stability"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def fake_sdk():
    """A MagicMock standing in for the peopledatalabs PDLPY client."""
    sdk = MagicMock()
    sdk.person = MagicMock()
    sdk.person.search = MagicMock()
    sdk.person.enrichment = MagicMock()
    return sdk


@pytest.fixture
def client(tmp_path, fake_sdk):
    cache = DiskCache(dir=tmp_path / "pdl", mode="live")
    return PDLClient(api_key="test-key", cache=cache, _sdk_factory=lambda: fake_sdk)


def test_search_people_returns_search_results(client, fake_sdk):
    response = _load_fixture("pdl_search_cro_response.json")
    fake_sdk.person.search.return_value = MagicMock(json=lambda: response, status_code=200)

    results = asyncio.run(client.search_people(
        company_domain="acme.com",
        search_spec={"role": "sales", "levels": ["cxo"]},
        size=3,
    ))

    assert len(results) == 2
    assert results[0].full_name == "Jane Doe"
    assert results[0].linkedin_url == "https://www.linkedin.com/in/jane-doe-cro"
    assert results[0].current_title == "Chief Revenue Officer"
    assert results[0].job_start_date == "2024-03-01"
    assert results[0].match_score == 0.94


def test_search_people_caches_by_company_and_spec(client, fake_sdk):
    response = _load_fixture("pdl_search_cro_response.json")
    fake_sdk.person.search.return_value = MagicMock(json=lambda: response, status_code=200)

    asyncio.run(client.search_people("acme.com", {"role": "sales", "levels": ["cxo"]}))
    asyncio.run(client.search_people("acme.com", {"role": "sales", "levels": ["cxo"]}))

    assert fake_sdk.person.search.call_count == 1


def test_search_people_raises_on_sdk_error(client, fake_sdk):
    fake_sdk.person.search.side_effect = RuntimeError("simulated SDK failure")

    with pytest.raises(PDLError):
        asyncio.run(client.search_people("acme.com", {"role": "sales", "levels": ["cxo"]}))


def test_search_people_handles_empty_match(client, fake_sdk):
    response = _load_fixture("pdl_search_no_match_response.json")
    fake_sdk.person.search.return_value = MagicMock(json=lambda: response, status_code=200)

    results = asyncio.run(client.search_people("obscure.com", {"role": "sales", "levels": ["cxo"]}))
    assert results == []


def test_search_people_builds_es_dsl_with_role_and_levels(client, fake_sdk):
    """Spec with `role` + `levels` must produce a bool/must ES DSL query with
    job_company_website + job_title_role + job_title_levels term/terms clauses
    and pass it to the SDK as `query=<dict>`."""
    response = _load_fixture("pdl_search_no_match_response.json")
    fake_sdk.person.search.return_value = MagicMock(json=lambda: response, status_code=200)

    asyncio.run(client.search_people(
        company_domain="swayable.com",
        search_spec={"role": "sales", "levels": ["vp"]},
        size=3,
    ))

    fake_sdk.person.search.assert_called_once()
    kwargs = fake_sdk.person.search.call_args.kwargs
    assert "query" in kwargs, f"SDK call must pass `query=<dict>`; got kwargs={kwargs}"
    assert "sql" not in kwargs, "SQL query path must be removed"
    query = kwargs["query"]
    assert query == {
        "bool": {
            "must": [
                {"term": {"job_company_website": "swayable.com"}},
                {"term": {"job_title_role": "sales"}},
                {"terms": {"job_title_levels": ["vp"]}},
            ],
        },
    }
    assert kwargs.get("size") == 3
    assert kwargs.get("pretty") is True


def test_search_people_builds_es_dsl_with_levels_only(client, fake_sdk):
    """A spec with only `levels` (e.g. CEO disambiguated solely by title_keywords)
    must omit the role clause."""
    response = _load_fixture("pdl_search_no_match_response.json")
    fake_sdk.person.search.return_value = MagicMock(json=lambda: response, status_code=200)

    asyncio.run(client.search_people(
        company_domain="acme.com",
        search_spec={"levels": ["cxo"]},
        size=5,
    ))

    query = fake_sdk.person.search.call_args.kwargs["query"]
    assert query == {
        "bool": {
            "must": [
                {"term": {"job_company_website": "acme.com"}},
                {"terms": {"job_title_levels": ["cxo"]}},
            ],
        },
    }


def test_search_people_builds_es_dsl_with_title_keywords_only(client, fake_sdk):
    """A spec with `title_keywords` only (e.g. founder, which classifies
    unevenly across levels) must produce a nested bool/should with wildcard
    clauses on job_title — each keyword wrapped as `*<lowercase>*`."""
    response = _load_fixture("pdl_search_no_match_response.json")
    fake_sdk.person.search.return_value = MagicMock(json=lambda: response, status_code=200)

    asyncio.run(client.search_people(
        company_domain="acme.com",
        search_spec={"title_keywords": ["founder", "co-founder"]},
        size=3,
    ))

    query = fake_sdk.person.search.call_args.kwargs["query"]
    assert query == {
        "bool": {
            "must": [
                {"term": {"job_company_website": "acme.com"}},
                {"bool": {"should": [
                    {"wildcard": {"job_title": "*founder*"}},
                    {"wildcard": {"job_title": "*co-founder*"}},
                ]}},
            ],
        },
    }


def test_search_people_builds_es_dsl_with_all_three_fields(client, fake_sdk):
    """Full spec: role + levels + title_keywords (e.g. vp_revenue narrowing
    inside the vp/sales bucket)."""
    response = _load_fixture("pdl_search_no_match_response.json")
    fake_sdk.person.search.return_value = MagicMock(json=lambda: response, status_code=200)

    asyncio.run(client.search_people(
        company_domain="acme.com",
        search_spec={"role": "sales", "levels": ["vp"], "title_keywords": ["revenue"]},
        size=3,
    ))

    query = fake_sdk.person.search.call_args.kwargs["query"]
    assert query == {
        "bool": {
            "must": [
                {"term": {"job_company_website": "acme.com"}},
                {"term": {"job_title_role": "sales"}},
                {"terms": {"job_title_levels": ["vp"]}},
                {"bool": {"should": [
                    {"wildcard": {"job_title": "*revenue*"}},
                ]}},
            ],
        },
    }


def test_search_people_lowercases_company_domain(client, fake_sdk):
    """PDL indexes job_company_website lowercased; pass-through must do
    the same so a domain entered as "Swayable.COM" still matches."""
    response = _load_fixture("pdl_search_no_match_response.json")
    fake_sdk.person.search.return_value = MagicMock(json=lambda: response, status_code=200)

    asyncio.run(client.search_people(
        company_domain="Swayable.COM",
        search_spec={"levels": ["cxo"]},
    ))

    query = fake_sdk.person.search.call_args.kwargs["query"]
    domain_clause = query["bool"]["must"][0]
    assert domain_clause == {"term": {"job_company_website": "swayable.com"}}


def test_enrich_person_by_linkedin_url(client, fake_sdk):
    response = _load_fixture("pdl_enrich_external_hire.json")
    fake_sdk.person.enrichment.return_value = MagicMock(json=lambda: response, status_code=200)

    result = asyncio.run(client.enrich_person(
        linkedin_url="https://www.linkedin.com/in/jane-doe-cro",
    ))

    assert isinstance(result, PDLEnrichment)
    assert result.full_name == "Jane Doe"
    assert result.current_title == "Chief Revenue Officer"
    assert result.job_start_date == "2024-03-01"
    assert result.previous_companies == ["Salesforce", "Oracle"]
    assert result.previous_titles == ["VP of Enterprise Sales", "Senior Account Executive"]
    assert len(result.experience) == 3


def test_enrich_person_by_name_and_company_fallback(client, fake_sdk):
    response = _load_fixture("pdl_enrich_external_hire.json")
    fake_sdk.person.enrichment.return_value = MagicMock(json=lambda: response, status_code=200)

    result = asyncio.run(client.enrich_person(
        name="Jane Doe", company_domain="acme.com",
    ))

    assert result is not None
    assert result.full_name == "Jane Doe"


def test_enrich_person_returns_none_on_no_match(client, fake_sdk):
    # PDL returns 404 (no match) — our wrapper converts to None, not an error.
    fake_sdk.person.enrichment.return_value = MagicMock(
        json=lambda: {"status": 404, "data": None}, status_code=404,
    )

    result = asyncio.run(client.enrich_person(linkedin_url="https://example.com/notfound"))
    assert result is None


def test_enrich_person_raises_on_sdk_error(client, fake_sdk):
    fake_sdk.person.enrichment.side_effect = RuntimeError("simulated failure")

    with pytest.raises(PDLError):
        asyncio.run(client.enrich_person(linkedin_url="https://example.com/x"))


def test_enrich_person_caches_by_linkedin_url(client, fake_sdk):
    response = _load_fixture("pdl_enrich_external_hire.json")
    fake_sdk.person.enrichment.return_value = MagicMock(json=lambda: response, status_code=200)

    url = "https://www.linkedin.com/in/jane-doe-cro"
    asyncio.run(client.enrich_person(linkedin_url=url))
    asyncio.run(client.enrich_person(linkedin_url=url))

    assert fake_sdk.person.enrichment.call_count == 1


def test_sdk_exception_does_not_leak_api_key_in_search(client, fake_sdk, caplog):
    """If the underlying PDL SDK raises an exception whose message includes
    the API key (some HTTP libs echo headers/URLs), neither the resulting
    PDLError string nor the warning log line should contain the key."""
    api_key = "test-key"
    fake_sdk.person.search.side_effect = RuntimeError(
        f"GET /v5/person/search?api_key={api_key} failed with 401"
    )

    with (
        pytest.raises(PDLError) as exc_info,
        caplog.at_level("WARNING", logger="rrxray.pdl"),
    ):
        asyncio.run(client.search_people("acme.com", {"role": "sales", "levels": ["cxo"]}))

    assert api_key not in str(exc_info.value), (
        f"PDLError message leaked api_key: {exc_info.value}"
    )
    leaking_records = [r for r in caplog.records if api_key in r.getMessage()]
    assert not leaking_records, (
        f"Warning log leaked api_key: {[r.getMessage() for r in leaking_records]}"
    )


def test_sdk_exception_does_not_leak_api_key_in_enrich(client, fake_sdk, caplog):
    """Same guard for the enrich path."""
    api_key = "test-key"
    fake_sdk.person.enrichment.side_effect = RuntimeError(
        f"Authorization header: Bearer {api_key}"
    )

    with (
        pytest.raises(PDLError) as exc_info,
        caplog.at_level("WARNING", logger="rrxray.pdl"),
    ):
        asyncio.run(client.enrich_person(linkedin_url="https://example.com/x"))

    assert api_key not in str(exc_info.value), (
        f"PDLError message leaked api_key: {exc_info.value}"
    )
    leaking_records = [r for r in caplog.records if api_key in r.getMessage()]
    assert not leaking_records, (
        f"Warning log leaked api_key: {[r.getMessage() for r in leaking_records]}"
    )


def test_search_people_allows_valid_input(client, fake_sdk):
    """Sanity check: a valid domain + spec produces a successful search."""
    response = _load_fixture("pdl_search_cro_response.json")
    fake_sdk.person.search.return_value = MagicMock(json=lambda: response, status_code=200)

    results = asyncio.run(client.search_people(
        "acme.com", {"role": "sales", "levels": ["cxo"]},
    ))
    assert len(results) == 2


def test_search_people_rejects_empty_spec(client, fake_sdk):
    """A spec with no filtering clauses (no role / levels / title_keywords)
    would degenerate to "all people at company_domain", which is too broad
    and burns budget. Reject it."""
    with pytest.raises(PDLError):
        asyncio.run(client.search_people("acme.com", {}))


def test_enrich_person_sorts_experience_reverse_chrono_for_previous_companies(client, fake_sdk):
    """PDL does not guarantee experience ordering; orchestrator relies on
    previous_companies[0] being the *most recent* prior employer. Build a
    response with shuffled (oldest-first, missing-date mixed) experience and
    assert previous_companies[0]/previous_titles[0] are the most recent."""
    shuffled_response = {
        "status": 200,
        "data": {
            "full_name": "Shuffle Person",
            "linkedin_url": "https://www.linkedin.com/in/shuffle",
            "job_title": "Chief Revenue Officer",
            "job_company_name": "Acme",
            "job_start_date": "2024-03-01",
            "experience": [
                # Oldest first
                {
                    "company": {"name": "Oldest Co"},
                    "title": {"name": "Junior Account Exec"},
                    "start_date": "2010-01-01",
                    "end_date": "2014-12-31",
                },
                # Missing end_date (current role) in the middle
                {
                    "company": {"name": "Acme"},
                    "title": {"name": "Chief Revenue Officer"},
                    "start_date": "2024-03-01",
                    "end_date": None,
                },
                # Missing dates entirely
                {
                    "company": {"name": "Mystery Co"},
                    "title": {"name": "Advisor"},
                },
                # Most recent prior employer (newest end_date)
                {
                    "company": {"name": "Most Recent Prior"},
                    "title": {"name": "VP of Sales"},
                    "start_date": "2020-06-01",
                    "end_date": "2024-02-15",
                },
                # Middle-aged
                {
                    "company": {"name": "Middle Co"},
                    "title": {"name": "Senior Manager"},
                    "start_date": "2015-01-01",
                    "end_date": "2020-05-30",
                },
            ],
        },
    }
    fake_sdk.person.enrichment.return_value = MagicMock(
        json=lambda: shuffled_response, status_code=200,
    )

    result = asyncio.run(client.enrich_person(
        linkedin_url="https://www.linkedin.com/in/shuffle",
    ))

    assert result is not None
    # Most recent prior employer (by end_date desc) must be first
    assert result.previous_companies[0] == "Most Recent Prior"
    assert result.previous_titles[0] == "VP of Sales"
    # Subsequent should be Middle Co then Oldest Co (reverse-chrono by end_date)
    assert result.previous_companies[1] == "Middle Co"
    assert result.previous_companies[2] == "Oldest Co"
