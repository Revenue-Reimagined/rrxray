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
        role_titles=["CRO", "Chief Revenue Officer"],
        size=3,
    ))

    assert len(results) == 2
    assert results[0].full_name == "Jane Doe"
    assert results[0].linkedin_url == "https://www.linkedin.com/in/jane-doe-cro"
    assert results[0].current_title == "Chief Revenue Officer"
    assert results[0].job_start_date == "2024-03-01"
    assert results[0].match_score == 0.94


def test_search_people_caches_by_company_and_role(client, fake_sdk):
    response = _load_fixture("pdl_search_cro_response.json")
    fake_sdk.person.search.return_value = MagicMock(json=lambda: response, status_code=200)

    asyncio.run(client.search_people("acme.com", ["CRO"]))
    asyncio.run(client.search_people("acme.com", ["CRO"]))

    assert fake_sdk.person.search.call_count == 1


def test_search_people_raises_on_sdk_error(client, fake_sdk):
    fake_sdk.person.search.side_effect = RuntimeError("simulated SDK failure")

    with pytest.raises(PDLError):
        asyncio.run(client.search_people("acme.com", ["CRO"]))


def test_search_people_handles_empty_match(client, fake_sdk):
    response = _load_fixture("pdl_search_no_match_response.json")
    fake_sdk.person.search.return_value = MagicMock(json=lambda: response, status_code=200)

    results = asyncio.run(client.search_people("obscure.com", ["CRO"]))
    assert results == []


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
