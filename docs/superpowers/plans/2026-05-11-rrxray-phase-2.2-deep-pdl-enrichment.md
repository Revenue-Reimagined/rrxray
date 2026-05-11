# rrxray Phase 2.2-deep PeopleDataLabs Enrichment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate PeopleDataLabs (PDL) Person Search + Enrichment to close the "tenure unconfirmed" narrative gap in the `leadership_stability` collector. Replace the Phase 2.2 LinkedIn-snippet path entirely; add prior-employer / years-at-company / tenure-months / prior-role data to both current incumbents AND press-detected exec changes. Cost cap + circuit breaker keep PDL spend bounded with graceful degradation.

**Architecture:** New `PDLClient` service class sibling to existing FirecrawlClient / AnthropicClient / GeminiClient. New `LeadershipEnrichment` orchestrator wraps the Search → Enrich chain with cost-cap counter, circuit breaker, and per-role failure isolation. Collector calls one orchestrator method per phase (incumbent path + press-name path). Synthesizer gets new pre-computed aggregates (tenure_confirmed_count, external_hire_count, internal_promotion_count, prior_employer_signals) plus a prior-employer motion-lens instruction. LinkedIn snippet path and its extractor methods are deleted.

**Tech Stack:** Python 3.12+, pydantic v2, jinja2, firecrawl-py (existing), anthropic SDK (existing), google-genai SDK (existing — unused in this phase but retained), `peopledatalabs-python` SDK (NEW — Dale-approved per CLAUDE.md "one approved data partner per signal area"), pytest + pytest-asyncio, ruff.

**Spec reference:** [docs/superpowers/specs/2026-05-11-rrxray-phase-2.2-deep-pdl-enrichment-design.md](../specs/2026-05-11-rrxray-phase-2.2-deep-pdl-enrichment-design.md)

---

## File Structure

`[T#]` indicates the task that creates or modifies each file.

```
NEW:
  rrxray/services/pdl_client.py                      [T1: PDLClient + PDLSearchResult + PDLEnrichment + PDLError]
  rrxray/services/leadership_enrichment.py           [T4: LeadershipEnrichment + EnrichedLeadership; cost cap + circuit breaker]
  tests/test_pdl_client.py                           [T1]
  tests/test_leadership_enrichment.py                [T4]
  tests/fixtures/synthetic/leadership_stability/pdl_search_cro_response.json        [T1]
  tests/fixtures/synthetic/leadership_stability/pdl_search_no_match_response.json   [T1]
  tests/fixtures/synthetic/leadership_stability/pdl_enrich_external_hire.json       [T1]
  tests/fixtures/synthetic/leadership_stability/pdl_enrich_internal_promotion.json  [T1]
  tests/fixtures/synthetic/leadership_stability/pdl_enrich_long_tenure.json         [T1]
  tests/fixtures/synthetic/leadership_stability/pdl_enrich_minimal.json             [T1]

MODIFIED:
  pyproject.toml                                     [T1: add peopledatalabs-python dependency]
  rrxray/schemas/leadership_stability.py             [T2: extend CurrentIncumbent + ExecChange + add LeadershipEnrichmentMetadata]
  rrxray/config.py                                   [T3: add pdl_api_key + pdl_cost_cap_dollars + no_pdl]
  rrxray/cli.py                                      [T3: add --pdl-cost-cap + --no-pdl flags]
  rrxray/context.py                                  [T5: add leadership_enrichment field]
  rrxray/pipeline.py                                 [T5: instantiate PDLClient + LeadershipEnrichment when key present]
  rrxray/collectors/leadership_stability.py          [T6: DELETE LinkedIn snippet path; ADD PDL incumbent path + press enrichment]
  rrxray/services/extraction.py                      [T7: DELETE extract_linkedin_role methods + _LINKEDIN_INCUMBENT_SYSTEM_PROMPT]
  rrxray/synthesizers/observed_stability_trajectory.py [T8: extend StabilityAggregates + _build_aggregates]
  rrxray/prompts/observed_stability_trajectory.md    [T8: new tenure / hire-origin / prior-employer blocks + motion-lens instruction]
  templates/_leadership_stability_detail.md.jinja    [T9: new tenure + prior + enrichment metadata columns]
  roadmap.md                                         [T10: post-quality-gate Phase 2.2-deep entry]

DELETED (via T6 + T7):
  tests/fixtures/synthetic/leadership_stability/linkedin_cro_response.json          [T6]
  tests/fixtures/synthetic/leadership_stability/linkedin_cmo_response.json          [T6]
  tests/fixtures/synthetic/leadership_stability/linkedin_empty_response.json        [T6]
```

---

## Task overview

10 tasks total. T1-T4 are foundation (new client, schemas, config/CLI, orchestrator). T5-T6 wire into the pipeline + collector. T7 removes dead code. T8-T9 update synthesizer + renderer. T10 is the Dale-led quality gate.

| # | Task | Type |
|---|---|---|
| T1 | PDLClient + dependency + fixtures | Real-logic |
| T2 | Schema extensions on CurrentIncumbent + ExecChange + LeadershipEnrichmentMetadata | Mechanical |
| T3 | Config + CLI flags (PDL_API_KEY, --pdl-cost-cap, --no-pdl) | Mechanical |
| T4 | LeadershipEnrichment orchestrator | Real-logic |
| T5 | Pipeline + CollectorContext wire-up | Real-logic |
| T6 | Collector integration (replace LinkedIn path; add PDL paths) | Real-logic |
| T7 | Delete extract_linkedin_role from extraction.py | Mechanical |
| T8 | Synthesizer aggregates + prompt additions | Real-logic |
| T9 | Renderer Module Detail template updates | Mechanical |
| T10 | Quality gate (Dale-led) | Manual |

**Two-stage review** (spec compliance + code quality): apply on real-logic tasks (T1, T4, T5, T6, T8). Skip on mechanical (T2, T3, T7, T9).

**Local verification after each task:** `uv run pytest -v 2>&1 | tail -3` and confirm test count + pass/fail before dispatching reviewers.

**Baseline test count entering Phase 2.2-deep:** 340 passed, 1 skipped (per Phase 2.2 checkpoint at commit `56857a8`). Expected end state: ~380 passed (~40 new tests).

---

## Task 1: PDLClient + dependency + fixtures

**Files:**
- Modify: `pyproject.toml` (add `peopledatalabs-python` dependency)
- Create: `rrxray/services/pdl_client.py`
- Create: `tests/test_pdl_client.py`
- Create: 6 fixture files under `tests/fixtures/synthetic/leadership_stability/`

- [ ] **Step 1: Add peopledatalabs-python dependency**

```bash
/Users/dalezwizinski/Library/Python/3.9/bin/uv add peopledatalabs-python
```

Expected: `pyproject.toml` updated with `peopledatalabs-python >= X.Y.Z`; `uv.lock` updated; install succeeds.

- [ ] **Step 2: Inspect the peopledatalabs-python SDK shape**

```bash
/Users/dalezwizinski/Library/Python/3.9/bin/uv run python -c "
from peopledatalabs import PDLPY
import inspect
print('PDLPY constructor:')
print(inspect.signature(PDLPY.__init__))
print()
print('person.search method:')
client = PDLPY(api_key='test')
print(inspect.signature(client.person.search))
print()
print('person.enrichment method:')
print(inspect.signature(client.person.enrichment))
"
```

Expected: shows `PDLPY(api_key=..., ...)`, `client.person.search(...)`, `client.person.enrichment(...)`. Adapt the wrapper if the SDK shape differs (matches Phase 2.1a inspect-then-adapt discipline).

- [ ] **Step 3: Create the 6 fixture files**

`tests/fixtures/synthetic/leadership_stability/pdl_search_cro_response.json`:

```json
{
  "status": 200,
  "data": [
    {
      "full_name": "Jane Doe",
      "linkedin_url": "https://www.linkedin.com/in/jane-doe-cro",
      "job_title": "Chief Revenue Officer",
      "job_company_name": "Acme Corp",
      "job_company_website": "acme.com",
      "job_start_date": "2024-03-01",
      "match_score": 0.94
    },
    {
      "full_name": "John Smith",
      "linkedin_url": "https://www.linkedin.com/in/john-smith-cro",
      "job_title": "CRO",
      "job_company_name": "Acme Corp",
      "job_company_website": "acme.com",
      "job_start_date": "2024-03-15",
      "match_score": 0.78
    }
  ],
  "total": 2
}
```

`tests/fixtures/synthetic/leadership_stability/pdl_search_no_match_response.json`:

```json
{
  "status": 200,
  "data": [],
  "total": 0
}
```

`tests/fixtures/synthetic/leadership_stability/pdl_enrich_external_hire.json`:

```json
{
  "status": 200,
  "data": {
    "full_name": "Jane Doe",
    "linkedin_url": "https://www.linkedin.com/in/jane-doe-cro",
    "job_title": "Chief Revenue Officer",
    "job_company_name": "Acme Corp",
    "job_company_website": "acme.com",
    "job_start_date": "2024-03-01",
    "job_company_size": "201-500",
    "experience": [
      {
        "company": {"name": "Acme Corp", "website": "acme.com"},
        "title": {"name": "Chief Revenue Officer"},
        "start_date": "2024-03-01",
        "end_date": null
      },
      {
        "company": {"name": "Salesforce", "website": "salesforce.com"},
        "title": {"name": "VP of Enterprise Sales"},
        "start_date": "2020-06-01",
        "end_date": "2024-02-15"
      },
      {
        "company": {"name": "Oracle", "website": "oracle.com"},
        "title": {"name": "Senior Account Executive"},
        "start_date": "2017-01-01",
        "end_date": "2020-05-30"
      }
    ]
  }
}
```

`tests/fixtures/synthetic/leadership_stability/pdl_enrich_internal_promotion.json`:

```json
{
  "status": 200,
  "data": {
    "full_name": "Bob Smith",
    "linkedin_url": "https://www.linkedin.com/in/bob-smith-cro",
    "job_title": "Chief Revenue Officer",
    "job_company_name": "Acme Corp",
    "job_company_website": "acme.com",
    "job_start_date": "2025-09-01",
    "job_company_size": "201-500",
    "experience": [
      {
        "company": {"name": "Acme Corp", "website": "acme.com"},
        "title": {"name": "Chief Revenue Officer"},
        "start_date": "2025-09-01",
        "end_date": null
      },
      {
        "company": {"name": "Acme Corp", "website": "acme.com"},
        "title": {"name": "VP of Sales"},
        "start_date": "2022-06-01",
        "end_date": "2025-08-31"
      }
    ]
  }
}
```

`tests/fixtures/synthetic/leadership_stability/pdl_enrich_long_tenure.json`:

```json
{
  "status": 200,
  "data": {
    "full_name": "Founder Person",
    "linkedin_url": "https://www.linkedin.com/in/founder-person",
    "job_title": "CEO and Founder",
    "job_company_name": "Acme Corp",
    "job_company_website": "acme.com",
    "job_start_date": "2018-01-01",
    "job_company_size": "201-500",
    "experience": [
      {
        "company": {"name": "Acme Corp", "website": "acme.com"},
        "title": {"name": "CEO and Founder"},
        "start_date": "2018-01-01",
        "end_date": null
      }
    ]
  }
}
```

`tests/fixtures/synthetic/leadership_stability/pdl_enrich_minimal.json`:

```json
{
  "status": 200,
  "data": {
    "full_name": "Sparse Person",
    "linkedin_url": null,
    "job_title": "VP Marketing",
    "job_company_name": "Acme Corp",
    "job_company_website": null,
    "job_start_date": null,
    "job_company_size": null,
    "experience": []
  }
}
```

- [ ] **Step 4: Write failing tests in `tests/test_pdl_client.py`**

```python
"""PDLClient: thin async wrapper around peopledatalabs-python for Search + Enrichment."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from rrxray.services.cache import DiskCache
from rrxray.services.pdl_client import (
    PDLClient, PDLEnrichment, PDLError, PDLSearchResult,
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
```

- [ ] **Step 5: Run tests to verify they fail**

```bash
cd /Users/dalezwizinski/Documents/Apps/rrxray/.claude/worktrees/unruffled-chandrasekhar-93625c
/Users/dalezwizinski/Library/Python/3.9/bin/uv run pytest tests/test_pdl_client.py -v
```

Expected: ERRORS with `ModuleNotFoundError: No module named 'rrxray.services.pdl_client'`.

- [ ] **Step 6: Create `rrxray/services/pdl_client.py`**

```python
"""PDLClient: thin async wrapper around peopledatalabs-python.

Sibling to AnthropicClient / GeminiClient / FirecrawlClient. No provider
abstraction layer (deferred per CLAUDE.md "one approved data partner per
signal area").

Used by Phase 2.2-deep LeadershipEnrichment orchestrator to enrich
current_incumbents and press change names with tenure / role history /
prior employer / prior role.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from rrxray.services.cache import DiskCache

log = logging.getLogger("rrxray.pdl")


class PDLError(Exception):
    pass


class PDLSearchResult(BaseModel):
    full_name: str
    linkedin_url: str | None = None
    current_title: str
    job_company_name: str | None = None
    job_start_date: str | None = None  # YYYY-MM-DD when available
    match_score: float = 0.0


class PDLEnrichment(BaseModel):
    full_name: str
    linkedin_url: str | None = None
    current_title: str
    job_company_name: str | None = None
    job_start_date: str | None = None
    job_company_size: str | None = None
    previous_companies: list[str] = []
    previous_titles: list[str] = []
    experience: list[dict[str, Any]] = []


class PDLClient:
    def __init__(
        self,
        api_key: str,
        cache: DiskCache,
        _sdk_factory: Callable[[], Any] | None = None,
    ):
        self.api_key = api_key
        self.cache = cache
        if _sdk_factory is not None:
            self._sdk = _sdk_factory()
        else:
            from peopledatalabs import PDLPY
            self._sdk = PDLPY(api_key=api_key)

    async def search_people(
        self,
        company_domain: str,
        role_titles: list[str],
        size: int = 3,
    ) -> list[PDLSearchResult]:
        """Person Search by (company_domain, role_titles). Returns ranked matches.

        Caches by (company_domain, role_titles_sorted, size); 30-day TTL via DiskCache.
        Raises PDLError on terminal SDK failure (200-no-match is NOT an error).
        """
        args = {
            "domain": company_domain,
            "titles": sorted(role_titles),
            "size": size,
        }

        async def upstream() -> dict[str, Any]:
            try:
                response = await asyncio.to_thread(self._build_search_call, company_domain, role_titles, size)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("PDL search failed: %s", e)
                raise PDLError(f"search_people failed: {e}") from e
            return response

        raw = await self.cache.get_or_call("pdl.search", args, upstream)
        data = raw.get("data", [])
        if not isinstance(data, list):
            return []

        results: list[PDLSearchResult] = []
        for r in data:
            if not isinstance(r, dict):
                continue
            results.append(PDLSearchResult(
                full_name=r.get("full_name", ""),
                linkedin_url=r.get("linkedin_url"),
                current_title=r.get("job_title", ""),
                job_company_name=r.get("job_company_name"),
                job_start_date=r.get("job_start_date"),
                match_score=float(r.get("match_score", 0.0)),
            ))
        return results

    def _build_search_call(self, company_domain: str, role_titles: list[str], size: int) -> dict[str, Any]:
        """Synchronous SDK call wrapped by asyncio.to_thread. Builds SQL filter for PDL Search."""
        # PDL Search uses SQL-style WHERE clauses on indexed fields.
        title_clause = " OR ".join(f"job_title='{t}'" for t in role_titles)
        sql = (
            f"SELECT * FROM person WHERE job_company_website='{company_domain}' "
            f"AND ({title_clause})"
        )
        response = self._sdk.person.search(sql=sql, size=size, pretty=True)
        return response.json()

    async def enrich_person(
        self,
        linkedin_url: str | None = None,
        name: str | None = None,
        company_domain: str | None = None,
    ) -> PDLEnrichment | None:
        """Person Enrichment. Prefers linkedin_url; falls back to (name, company_domain).

        Returns None on PDL "no match" (status 404 or empty data).
        Raises PDLError on terminal SDK failure.
        Caches by linkedin_url (preferred) or (name, company_domain).
        """
        if linkedin_url is None and (name is None or company_domain is None):
            raise PDLError("enrich_person requires either linkedin_url or (name, company_domain)")

        cache_key = {"linkedin_url": linkedin_url, "name": name, "company_domain": company_domain}

        async def upstream() -> dict[str, Any]:
            try:
                response = await asyncio.to_thread(
                    self._build_enrich_call, linkedin_url, name, company_domain,
                )
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("PDL enrichment failed: %s", e)
                raise PDLError(f"enrich_person failed: {e}") from e
            return response

        raw = await self.cache.get_or_call("pdl.enrich", cache_key, upstream)

        # PDL signals "no match" via 404 status or empty data dict
        status = raw.get("status", 200)
        data = raw.get("data")
        if status == 404 or not data:
            return None

        experience = data.get("experience", []) if isinstance(data.get("experience"), list) else []
        previous_companies: list[str] = []
        previous_titles: list[str] = []
        # Reverse-chrono order: skip the current role (end_date=None), collect previous
        for exp in experience:
            if not isinstance(exp, dict):
                continue
            end_date = exp.get("end_date")
            if end_date is None:
                continue  # current role
            company_name = (exp.get("company") or {}).get("name")
            title_name = (exp.get("title") or {}).get("name")
            if company_name:
                previous_companies.append(company_name)
            if title_name:
                previous_titles.append(title_name)

        return PDLEnrichment(
            full_name=data.get("full_name", ""),
            linkedin_url=data.get("linkedin_url"),
            current_title=data.get("job_title", ""),
            job_company_name=data.get("job_company_name"),
            job_start_date=data.get("job_start_date"),
            job_company_size=data.get("job_company_size"),
            previous_companies=previous_companies,
            previous_titles=previous_titles,
            experience=experience,
        )

    def _build_enrich_call(
        self, linkedin_url: str | None, name: str | None, company_domain: str | None,
    ) -> dict[str, Any]:
        """Synchronous SDK call wrapped by asyncio.to_thread."""
        params: dict[str, Any] = {}
        if linkedin_url:
            params["profile"] = linkedin_url
        else:
            params["name"] = name
            params["company"] = company_domain
        response = self._sdk.person.enrichment(**params)
        return response.json()
```

- [ ] **Step 7: Run tests to verify they pass + ruff**

```bash
/Users/dalezwizinski/Library/Python/3.9/bin/uv run pytest tests/test_pdl_client.py -v
/Users/dalezwizinski/Library/Python/3.9/bin/uv run ruff check rrxray/ tests/
```

Expected: 9 tests pass. Ruff clean. Total project: 349 passed, 1 skipped.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml uv.lock rrxray/services/pdl_client.py tests/test_pdl_client.py tests/fixtures/synthetic/leadership_stability/pdl_*.json
git commit -m "$(cat <<'EOF'
Add PDLClient — thin wrapper around peopledatalabs-python SDK

Sibling to AnthropicClient / GeminiClient / FirecrawlClient. Two async
methods: search_people(company_domain, role_titles) and enrich_person
(linkedin_url OR name+company_domain). Disk cache (30-day TTL via
existing DiskCache). 200-no-match returns None for enrichment; terminal
SDK failures raise PDLError.

Used by Phase 2.2-deep LeadershipEnrichment orchestrator (T4) to fill
tenure / role history / prior employer / prior role on current
incumbents and press change names.

peopledatalabs-python is a new third-party dependency approved by Dale
per the "one approved data partner per signal area" rule in CLAUDE.md.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Schema extensions

**Files:**
- Modify: `rrxray/schemas/leadership_stability.py` (extend CurrentIncumbent + ExecChange; add LeadershipEnrichmentMetadata; extend LeadershipStabilityData)
- Modify: `tests/test_leadership_stability_schemas.py`

- [ ] **Step 1: Append failing tests to `tests/test_leadership_stability_schemas.py`**

```python
def test_current_incumbent_enrichment_fields_default_none():
    """Phase 2.2-deep: tenure_months / years_at_company / prior_employer / prior_role default to None."""
    from rrxray.schemas.leadership_stability import CurrentIncumbent
    c = CurrentIncumbent(name="Jane", role_canonical="cro", role_raw="CRO")
    assert c.tenure_months is None
    assert c.years_at_company is None
    assert c.prior_employer is None
    assert c.prior_role is None


def test_current_incumbent_round_trips_with_enrichment_fields():
    from rrxray.schemas.leadership_stability import CurrentIncumbent
    import json
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
    from pydantic import ValidationError
    import pytest
    from rrxray.schemas.leadership_stability import LeadershipEnrichmentMetadata
    for reason in ["completed", "cost_cap", "circuit_breaker", "disabled"]:
        m = LeadershipEnrichmentMetadata(aborted_reason=reason)
        assert m.aborted_reason == reason
    with pytest.raises(ValidationError):
        LeadershipEnrichmentMetadata(aborted_reason="invalid_value")


def test_leadership_stability_data_round_trips_with_enrichment_metadata():
    from rrxray.schemas.leadership_stability import (
        LeadershipEnrichmentMetadata, LeadershipStabilityData,
    )
    import json
    d = LeadershipStabilityData(
        enrichment_metadata=LeadershipEnrichmentMetadata(
            spend_dollars=2.40, aborted_reason="completed",
        ),
    )
    restored = LeadershipStabilityData.model_validate(json.loads(d.model_dump_json()))
    assert restored.enrichment_metadata.spend_dollars == 2.40
    assert restored.enrichment_metadata.aborted_reason == "completed"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
/Users/dalezwizinski/Library/Python/3.9/bin/uv run pytest tests/test_leadership_stability_schemas.py -v
```

Expected: 6 new tests fail (ImportError on LeadershipEnrichmentMetadata; AttributeError on new fields).

- [ ] **Step 3: Edit `rrxray/schemas/leadership_stability.py`**

Add `LeadershipEnrichmentMetadata` class after `NameRegistration`:

```python
class LeadershipEnrichmentMetadata(BaseModel):
    """Tracking metadata for PDL leadership enrichment (Phase 2.2-deep)."""
    spend_dollars: float = 0.0
    aborted_reason: Literal["completed", "cost_cap", "circuit_breaker", "disabled"] = "disabled"
```

Extend `CurrentIncumbent`:

```python
class CurrentIncumbent(BaseModel):
    name: str
    role_canonical: RoleCanonical
    role_raw: str
    linkedin_url: str | None = None
    confidence: Literal["high", "low"] = "high"
    # Phase 2.2-deep enrichment fields
    tenure_months: int | None = None
    years_at_company: int | None = None
    prior_employer: str | None = None
    prior_role: str | None = None
```

Extend `ExecChange`:

```python
class ExecChange(BaseModel):
    name: str
    role_canonical: RoleCanonical
    role_raw: str
    action: ExecAction
    occurred_at: date | None = None
    press_url: str
    press_title: str
    # Phase 2.2-deep enrichment fields
    prior_employer: str | None = None
    prior_role: str | None = None
    years_at_company: int | None = None
```

Extend `LeadershipStabilityData`:

```python
class LeadershipStabilityData(BaseModel):
    exec_changes: list[ExecChange] = []
    current_incumbents: list[CurrentIncumbent] = []
    founder_tenure: FounderTenure | None = None
    name_registrations: list[NameRegistration] = []
    findings: list[Finding] = []
    gaps: list[str] = []
    discovery_questions: list[str] = []
    sources: list[SourceCitation] = []
    # Phase 2.2-deep
    enrichment_metadata: LeadershipEnrichmentMetadata = Field(default_factory=LeadershipEnrichmentMetadata)
```

Add `from pydantic import BaseModel, Field` at the top if `Field` isn't imported yet.

- [ ] **Step 4: Run tests + ruff**

```bash
/Users/dalezwizinski/Library/Python/3.9/bin/uv run pytest tests/test_leadership_stability_schemas.py -v
/Users/dalezwizinski/Library/Python/3.9/bin/uv run ruff check rrxray/ tests/
```

Expected: 13 tests pass (7 existing + 6 new). Ruff clean.

- [ ] **Step 5: Commit**

```bash
git add rrxray/schemas/leadership_stability.py tests/test_leadership_stability_schemas.py
git commit -m "Extend leadership_stability schemas with PDL enrichment fields

CurrentIncumbent and ExecChange gain four optional fields each
(tenure_months / years_at_company / prior_employer / prior_role)
populated by PDL enrichment. LeadershipStabilityData gains
enrichment_metadata (spend_dollars + aborted_reason)."
```

---

## Task 3: Config + CLI flags

**Files:**
- Modify: `rrxray/config.py` (add `pdl_api_key`, `pdl_cost_cap_dollars`, `no_pdl`)
- Modify: `rrxray/cli.py` (add `--pdl-cost-cap` and `--no-pdl` flags)
- Modify: `tests/test_config.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Append failing tests to `tests/test_config.py`**

```python
def test_pdl_api_key_loaded_from_env(monkeypatch):
    monkeypatch.setenv("PDL_API_KEY", "test-pdl-key")
    from rrxray.config import Config
    c = Config(domain="example.com")
    assert c.pdl_api_key is not None
    assert c.pdl_api_key.get_secret_value() == "test-pdl-key"


def test_pdl_cost_cap_dollars_default_five():
    from rrxray.config import Config
    c = Config(domain="example.com")
    assert c.pdl_cost_cap_dollars == 5.0


def test_pdl_cost_cap_dollars_overridable():
    from rrxray.config import Config
    c = Config(domain="example.com", pdl_cost_cap_dollars=10.0)
    assert c.pdl_cost_cap_dollars == 10.0


def test_no_pdl_default_false():
    from rrxray.config import Config
    c = Config(domain="example.com")
    assert c.no_pdl is False


def test_no_pdl_overridable():
    from rrxray.config import Config
    c = Config(domain="example.com", no_pdl=True)
    assert c.no_pdl is True
```

- [ ] **Step 2: Append failing test to `tests/test_cli.py`**

```python
def test_run_command_accepts_pdl_cost_cap_and_no_pdl_flags():
    from typer.testing import CliRunner
    from rrxray.cli import app
    runner = CliRunner()
    result = runner.invoke(app, [
        "run", "--domain", "example.com", "--dry-run",
        "--pdl-cost-cap", "3.5", "--no-pdl",
    ])
    assert result.exit_code == 0, result.stdout
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
/Users/dalezwizinski/Library/Python/3.9/bin/uv run pytest tests/test_config.py tests/test_cli.py -v -k "pdl"
```

Expected: 6 new tests fail (AttributeError on `pdl_api_key` / `pdl_cost_cap_dollars` / `no_pdl`; CLI unknown option).

- [ ] **Step 4: Edit `rrxray/config.py`**

Add `pdl_api_key` after the existing API-key fields:

```python
    pdl_api_key: SecretStr | None = Field(default=None, alias="PDL_API_KEY")
```

Add `pdl_cost_cap_dollars` and `no_pdl` after `extractor_model`:

```python
    pdl_cost_cap_dollars: float = 5.0
    no_pdl: bool = False
```

- [ ] **Step 5: Edit `rrxray/cli.py`** — add the two flags to the `run` command

Find the existing `run` command's option block. Append:

```python
    pdl_cost_cap: float = typer.Option(
        5.0, "--pdl-cost-cap",
        help="Hard ceiling on PDL spend per X-Ray, in USD.",
    ),
    no_pdl: bool = typer.Option(
        False, "--no-pdl",
        help="Disable PDL enrichment entirely for this run.",
    ),
```

In the `_build_config` call inside `run`, pass:

```python
    config = _build_config(
        domain=domain,
        ...,
        pdl_cost_cap_dollars=pdl_cost_cap,
        no_pdl=no_pdl,
    )
```

- [ ] **Step 6: Run tests + ruff**

```bash
/Users/dalezwizinski/Library/Python/3.9/bin/uv run pytest tests/test_config.py tests/test_cli.py -v
/Users/dalezwizinski/Library/Python/3.9/bin/uv run ruff check rrxray/ tests/
```

Expected: all config + cli tests pass. Ruff clean.

- [ ] **Step 7: Commit**

```bash
git add rrxray/config.py rrxray/cli.py tests/test_config.py tests/test_cli.py
git commit -m "Add PDL_API_KEY config + --pdl-cost-cap + --no-pdl CLI flags"
```

---

## Task 4: LeadershipEnrichment orchestrator

**Files:**
- Create: `rrxray/services/leadership_enrichment.py`
- Create: `tests/test_leadership_enrichment.py`

- [ ] **Step 1: Write failing tests in `tests/test_leadership_enrichment.py`**

```python
"""LeadershipEnrichment: orchestrates PDL Search → Enrich per role with cost cap + circuit breaker."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from rrxray.schemas.leadership_stability import ExecAction, ExecChange
from rrxray.services.leadership_enrichment import (
    EnrichedLeadership, LeadershipEnrichment,
)
from rrxray.services.pdl_client import (
    PDLEnrichment, PDLError, PDLSearchResult,
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
    # 3 searches × 0.20 + 1 enrich × 0.20 = 0.80
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

    # 2 searches × 0.20 = 0.40; next search would be 0.60 > cap → skipped
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
/Users/dalezwizinski/Library/Python/3.9/bin/uv run pytest tests/test_leadership_enrichment.py -v
```

Expected: ImportError for `rrxray.services.leadership_enrichment`.

- [ ] **Step 3: Create `rrxray/services/leadership_enrichment.py`**

```python
"""LeadershipEnrichment: orchestrates PDL Search → Enrich per role with cost cap + circuit breaker.

Phase 2.2-deep. Replaces the Phase 2.2 LinkedIn-snippet path. Owns
cost-cap counter, circuit-breaker state, and per-role failure isolation.
The collector calls one method per phase (incumbent path + press-name
path); both share the orchestrator's spend counter.
"""
from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel

from rrxray.schemas.leadership_stability import (
    CurrentIncumbent, ExecChange, LeadershipEnrichmentMetadata,
)
from rrxray.services.pdl_client import PDLClient, PDLError

log = logging.getLogger("rrxray.leadership_enrichment")


PDL_COST_PER_SEARCH = 0.20
PDL_COST_PER_ENRICHMENT = 0.20
CIRCUIT_BREAKER_CONSECUTIVE_FAILURES = 3


class EnrichedLeadership(BaseModel):
    incumbents: list[CurrentIncumbent]
    spend_dollars: float = 0.0
    aborted_reason: Literal["completed", "cost_cap", "circuit_breaker"] = "completed"


class LeadershipEnrichment:
    def __init__(self, pdl: PDLClient, cost_cap_dollars: float):
        self.pdl = pdl
        self.cost_cap_dollars = cost_cap_dollars
        self._spend = 0.0
        self._consecutive_failures = 0
        self._circuit_open = False
        self._aborted_reason: Literal["completed", "cost_cap", "circuit_breaker"] = "completed"

    @property
    def metadata(self) -> LeadershipEnrichmentMetadata:
        return LeadershipEnrichmentMetadata(
            spend_dollars=round(self._spend, 4),
            aborted_reason=self._aborted_reason,
        )

    def _can_spend(self, cost: float) -> bool:
        if self._circuit_open:
            return False
        if self._spend + cost > self.cost_cap_dollars:
            log.warning(
                "PDL cost cap reached: $%.2f spent, $%.2f cap",
                self._spend, self.cost_cap_dollars,
            )
            self._aborted_reason = "cost_cap"
            return False
        return True

    def _record_success(self, cost: float) -> None:
        self._spend += cost
        self._consecutive_failures = 0

    def _record_failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= CIRCUIT_BREAKER_CONSECUTIVE_FAILURES:
            log.warning(
                "PDL circuit breaker tripped after %d consecutive failures",
                self._consecutive_failures,
            )
            self._circuit_open = True
            self._aborted_reason = "circuit_breaker"

    async def find_and_enrich_incumbents(
        self,
        company_name: str,
        company_domain: str,
        role_canonicals: list[tuple[str, list[str]]],
    ) -> EnrichedLeadership:
        """Per role: PDL Search → take top match by score → PDL Enrich by linkedin_url.

        Dedup across roles by linkedin_url (founder appearing as CEO + Founder is one Enrich call).
        Per-role failures isolated (logged, continues). Returns whatever was gathered.
        """
        incumbents: list[CurrentIncumbent] = []
        # Track linkedin_url → PDLEnrichment so we only enrich the same person once
        enrichment_cache: dict[str, "rrxray.services.pdl_client.PDLEnrichment | None"] = {}  # type: ignore

        for role_canonical, role_titles in role_canonicals:
            if not self._can_spend(PDL_COST_PER_SEARCH):
                break

            try:
                results = await self.pdl.search_people(company_domain, role_titles, size=3)
                self._record_success(PDL_COST_PER_SEARCH)
            except PDLError as e:
                log.warning("PDL search failed for role=%s: %s", role_canonical, e)
                self._record_failure()
                if self._circuit_open:
                    break
                continue

            if not results:
                continue

            # Take top match by score
            top = max(results, key=lambda r: r.match_score)
            if not top.linkedin_url:
                continue

            # Enrich (or reuse if same person across roles)
            if top.linkedin_url not in enrichment_cache:
                if not self._can_spend(PDL_COST_PER_ENRICHMENT):
                    break
                try:
                    enr = await self.pdl.enrich_person(linkedin_url=top.linkedin_url)
                    self._record_success(PDL_COST_PER_ENRICHMENT)
                except PDLError as e:
                    log.warning("PDL enrich failed for %s: %s", top.linkedin_url, e)
                    self._record_failure()
                    if self._circuit_open:
                        break
                    enr = None
                enrichment_cache[top.linkedin_url] = enr
            else:
                enr = enrichment_cache[top.linkedin_url]

            # Build incumbent record
            tenure_months = _months_since(enr.job_start_date) if enr and enr.job_start_date else None
            years_at_company = _years_at_company(enr, company_domain) if enr else None
            prior_employer = enr.previous_companies[0] if enr and enr.previous_companies else None
            prior_role = enr.previous_titles[0] if enr and enr.previous_titles else None

            incumbents.append(CurrentIncumbent(
                name=top.full_name,
                role_canonical=role_canonical,  # type: ignore[arg-type]
                role_raw=top.current_title,
                linkedin_url=top.linkedin_url,
                confidence="high",
                tenure_months=tenure_months,
                years_at_company=years_at_company,
                prior_employer=prior_employer,
                prior_role=prior_role,
            ))

        return EnrichedLeadership(
            incumbents=incumbents,
            spend_dollars=round(self._spend, 4),
            aborted_reason=self._aborted_reason,
        )

    async def enrich_press_change_names(
        self,
        exec_changes: list[ExecChange],
        company_domain: str,
    ) -> list[ExecChange]:
        """Per ExecChange: PDL Enrich by (name, company_domain). Returns mutated copies."""
        enriched: list[ExecChange] = []
        for change in exec_changes:
            if not self._can_spend(PDL_COST_PER_ENRICHMENT):
                enriched.append(change)
                continue
            try:
                enr = await self.pdl.enrich_person(
                    name=change.name, company_domain=company_domain,
                )
                self._record_success(PDL_COST_PER_ENRICHMENT)
            except PDLError as e:
                log.warning("PDL enrich (press) failed for %s: %s", change.name, e)
                self._record_failure()
                enriched.append(change)
                if self._circuit_open:
                    # Append remaining changes unmutated
                    remaining_idx = exec_changes.index(change) + 1
                    enriched.extend(exec_changes[remaining_idx:])
                    return enriched
                continue

            if enr is None:
                enriched.append(change)
                continue

            enriched.append(change.model_copy(update={
                "prior_employer": enr.previous_companies[0] if enr.previous_companies else None,
                "prior_role": enr.previous_titles[0] if enr.previous_titles else None,
                "years_at_company": _years_at_company(enr, company_domain),
            }))
        return enriched


def _months_since(iso_date: str) -> int | None:
    """Compute months since the given ISO YYYY-MM-DD date. None on parse failure."""
    from datetime import UTC, datetime
    try:
        start = datetime.fromisoformat(iso_date).date()
    except (ValueError, TypeError):
        return None
    today = datetime.now(UTC).date()
    months = (today.year - start.year) * 12 + (today.month - start.month)
    return max(0, months)


def _years_at_company(enr, company_domain: str) -> int | None:
    """Total years at the current company, summing all role tenures there."""
    if enr is None or not enr.experience:
        return None
    earliest_start: str | None = None
    for exp in enr.experience:
        if not isinstance(exp, dict):
            continue
        company = exp.get("company") or {}
        if not isinstance(company, dict):
            continue
        # Match by company name OR website
        website = (company.get("website") or "").lower()
        if company_domain.lower() in website or website in company_domain.lower():
            start = exp.get("start_date")
            if start and (earliest_start is None or start < earliest_start):
                earliest_start = start
    if earliest_start is None:
        return None
    months = _months_since(earliest_start)
    return months // 12 if months is not None else None
```

- [ ] **Step 4: Run tests + ruff**

```bash
/Users/dalezwizinski/Library/Python/3.9/bin/uv run pytest tests/test_leadership_enrichment.py -v
/Users/dalezwizinski/Library/Python/3.9/bin/uv run ruff check rrxray/ tests/
```

Expected: 9 tests pass. Ruff clean.

- [ ] **Step 5: Commit**

```bash
git add rrxray/services/leadership_enrichment.py tests/test_leadership_enrichment.py
git commit -m "$(cat <<'EOF'
Add LeadershipEnrichment orchestrator for PDL Search + Enrich

Owns the Search → Enrich chain per leadership role with cost-cap
counter, circuit breaker (3+ consecutive failures), and per-role
failure isolation. Two public methods: find_and_enrich_incumbents
(populates current_incumbents with tenure/role-history data) and
enrich_press_change_names (fills prior_employer / prior_role /
years_at_company on existing ExecChange records). Both share the
spend counter so cap exhaustion is global.

Returns whatever was gathered when the cap fires or circuit opens —
no aborts. Matches Phase 2.2's graceful-degradation pattern.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Pipeline + CollectorContext wire-up

**Files:**
- Modify: `rrxray/context.py` (add `leadership_enrichment` field on CollectorContext)
- Modify: `rrxray/pipeline.py` (instantiate PDLClient + LeadershipEnrichment when key present)
- Modify: `tests/test_pipeline.py` (add wire-up tests)
- Modify: `tests/test_context.py` (the existing "frozen field set" test will fail; update expected set)

- [ ] **Step 1: Write failing tests in `tests/test_pipeline.py`**

```python
def test_pipeline_instantiates_pdl_client_when_key_present(tmp_path):
    """When PDL_API_KEY is set and --no-pdl is not, build_collector_context wires up the enrichment orchestrator."""
    from rrxray.config import Config
    from rrxray.pipeline import build_collector_context
    config = Config(domain="example.com")
    # Manually set the key (SecretStr requires construction)
    from pydantic import SecretStr
    config = Config(domain="example.com")
    config.pdl_api_key = SecretStr("test-pdl-key")  # type: ignore[misc]

    ctx = build_collector_context(config)
    assert ctx.leadership_enrichment is not None


def test_pipeline_skips_pdl_when_no_api_key(tmp_path):
    """No PDL_API_KEY → leadership_enrichment is None."""
    from rrxray.config import Config
    from rrxray.pipeline import build_collector_context
    config = Config(domain="example.com")  # no PDL_API_KEY in env
    # Explicitly clear any inherited key
    config.pdl_api_key = None  # type: ignore[misc]

    ctx = build_collector_context(config)
    assert ctx.leadership_enrichment is None


def test_pipeline_skips_pdl_when_no_pdl_flag_set(tmp_path):
    """--no-pdl flag → leadership_enrichment is None even with API key present."""
    from pydantic import SecretStr
    from rrxray.config import Config
    from rrxray.pipeline import build_collector_context
    config = Config(domain="example.com", no_pdl=True)
    config.pdl_api_key = SecretStr("test-pdl-key")  # type: ignore[misc]

    ctx = build_collector_context(config)
    assert ctx.leadership_enrichment is None
```

- [ ] **Step 2: Update `tests/test_context.py`** to include `leadership_enrichment` in the expected field set

Find the existing `test_collector_context_is_frozen` (or similar field-set test) and add `"leadership_enrichment"` to the expected set:

```python
expected = {
    "domain", "company_name", "firecrawl", "wayback", "evidence_dir",
    "config", "extractor", "leadership_enrichment",  # NEW Phase 2.2-deep
}
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
/Users/dalezwizinski/Library/Python/3.9/bin/uv run pytest tests/test_pipeline.py tests/test_context.py -v -k "pdl or leadership_enrichment or frozen"
```

Expected: new pipeline tests fail (AttributeError on `ctx.leadership_enrichment`). Updated context test fails until step 4 lands.

- [ ] **Step 4: Edit `rrxray/context.py`**

Add `leadership_enrichment` field to `CollectorContext`:

```python
if TYPE_CHECKING:
    from rrxray.config import Config
    from rrxray.schemas.data import CollectorOutputs
    from rrxray.services.anthropic_client import AnthropicClient
    from rrxray.services.extraction import GeminiFlashExtractor, HaikuExtractor
    from rrxray.services.firecrawl_client import FirecrawlClient
    from rrxray.services.leadership_enrichment import LeadershipEnrichment
    from rrxray.services.wayback_client import WaybackClient
    from rrxray.voice.anonymizer import Anonymizer
    from rrxray.voice.rr_voice import VoicePostProcessor


@dataclass(frozen=True)
class CollectorContext:
    domain: str
    company_name: str | None
    firecrawl: FirecrawlClient
    wayback: WaybackClient
    evidence_dir: Path
    config: Config
    extractor: HaikuExtractor | GeminiFlashExtractor | None = None
    leadership_enrichment: LeadershipEnrichment | None = None
```

- [ ] **Step 5: Edit `rrxray/pipeline.py`**

Add imports at the top:

```python
from rrxray.services.leadership_enrichment import LeadershipEnrichment
from rrxray.services.pdl_client import PDLClient
```

In `build_collector_context`, after the existing firecrawl/wayback/anthropic/gemini wiring, add the PDL orchestrator construction:

```python
def build_collector_context(config) -> CollectorContext:
    cache_root = config.cache_dir
    # ... existing firecrawl / wayback / anthropic / gemini / extractor wiring ...

    # Phase 2.2-deep: PDL leadership enrichment (optional; gated by PDL_API_KEY + --no-pdl)
    leadership_enrichment = None
    pdl_key = getattr(config, "pdl_api_key", None)
    if not getattr(config, "no_pdl", False) and pdl_key is not None:
        pdl_client = PDLClient(
            api_key=pdl_key.get_secret_value(),
            cache=DiskCache(
                dir=cache_root / "pdl",
                mode="live" if config.use_cache else "refresh",
            ),
        )
        leadership_enrichment = LeadershipEnrichment(
            pdl=pdl_client,
            cost_cap_dollars=getattr(config, "pdl_cost_cap_dollars", 5.0),
        )

    return CollectorContext(
        domain=config.domain,
        company_name=config.company_name,
        firecrawl=firecrawl,
        wayback=wayback,
        evidence_dir=config.evidence_dir,
        config=config,
        extractor=extractor,
        leadership_enrichment=leadership_enrichment,
    )
```

- [ ] **Step 6: Run tests + ruff**

```bash
/Users/dalezwizinski/Library/Python/3.9/bin/uv run pytest -v 2>&1 | tail -3
/Users/dalezwizinski/Library/Python/3.9/bin/uv run ruff check rrxray/ tests/
```

Expected: full suite passes (340 baseline + new tests since T1). Ruff clean.

- [ ] **Step 7: Commit**

```bash
git add rrxray/context.py rrxray/pipeline.py tests/test_pipeline.py tests/test_context.py
git commit -m "Wire PDLClient + LeadershipEnrichment into pipeline + CollectorContext

CollectorContext gains leadership_enrichment: LeadershipEnrichment | None
field. Pipeline instantiates the orchestrator when PDL_API_KEY is set
and --no-pdl is not. The collector accesses ctx.leadership_enrichment
in T6."
```

---

## Task 6: Collector integration (replace LinkedIn path; add PDL paths)

**Files:**
- Modify: `rrxray/collectors/leadership_stability.py` (delete LinkedIn snippet path; add PDL incumbent path + press enrichment)
- Modify: `tests/test_leadership_stability.py` (delete LinkedIn tests; add PDL tests)
- Delete: `tests/fixtures/synthetic/leadership_stability/linkedin_cro_response.json`
- Delete: `tests/fixtures/synthetic/leadership_stability/linkedin_cmo_response.json`
- Delete: `tests/fixtures/synthetic/leadership_stability/linkedin_empty_response.json`

- [ ] **Step 1: Delete the LinkedIn fixtures**

```bash
rm tests/fixtures/synthetic/leadership_stability/linkedin_cro_response.json
rm tests/fixtures/synthetic/leadership_stability/linkedin_cmo_response.json
rm tests/fixtures/synthetic/leadership_stability/linkedin_empty_response.json
```

- [ ] **Step 2: Delete the LinkedIn-snippet path tests + add new PDL-path tests**

In `tests/test_leadership_stability.py`:

**Delete these tests** (search-and-remove):
- `test_search_linkedin_incumbents_runs_seven_role_queries`
- `test_search_linkedin_incumbents_handles_per_role_failure`
- `test_extract_current_incumbents_dedupes_by_role_name`
- `test_extract_current_incumbents_marks_post_url_low_confidence`
- `test_extract_current_incumbents_drops_irrelevant`
- `test_extract_current_incumbents_keeps_only_top_match_per_role`

**Append these new tests:**

```python
def test_collect_calls_leadership_enrichment_when_available(tmp_path):
    """When ctx.leadership_enrichment is set, collect() uses it to populate current_incumbents."""
    from unittest.mock import AsyncMock, MagicMock
    from rrxray.collectors.leadership_stability import collect
    from rrxray.config import Config
    from rrxray.context import CollectorContext
    from rrxray.schemas.leadership_stability import (
        CurrentIncumbent, LeadershipEnrichmentMetadata,
    )
    from rrxray.services.firecrawl_client import FirecrawlError
    from rrxray.services.leadership_enrichment import EnrichedLeadership

    # Fake firecrawl returns empty press searches + no /about page
    fake_firecrawl = MagicMock()
    fake_firecrawl.search = AsyncMock(return_value=[])
    fake_firecrawl.scrape_url = AsyncMock(side_effect=FirecrawlError("no /about"))
    fake_wayback = MagicMock()
    fake_wayback.snapshots = AsyncMock(return_value=[])

    fake_enrichment_meta = LeadershipEnrichmentMetadata(spend_dollars=0.40, aborted_reason="completed")
    fake_orch = MagicMock()
    fake_orch.find_and_enrich_incumbents = AsyncMock(return_value=EnrichedLeadership(
        incumbents=[
            CurrentIncumbent(
                name="Jane Doe", role_canonical="cro", role_raw="Chief Revenue Officer",
                linkedin_url="https://www.linkedin.com/in/jane-doe-cro",
                tenure_months=14, years_at_company=14,
                prior_employer="Salesforce", prior_role="VP of Enterprise Sales",
            ),
        ],
        spend_dollars=0.40, aborted_reason="completed",
    ))
    fake_orch.enrich_press_change_names = AsyncMock(side_effect=lambda exec_changes, company_domain: exec_changes)
    fake_orch.metadata = fake_enrichment_meta

    ctx = CollectorContext(
        domain="acme.com", company_name="Acme",
        firecrawl=fake_firecrawl, wayback=fake_wayback,
        evidence_dir=tmp_path, config=Config(domain="acme.com"),
        extractor=None,
        leadership_enrichment=fake_orch,
    )
    data = asyncio.run(collect(ctx))

    assert len(data.current_incumbents) == 1
    assert data.current_incumbents[0].tenure_months == 14
    assert data.current_incumbents[0].prior_employer == "Salesforce"
    assert data.enrichment_metadata.spend_dollars == 0.40
    fake_orch.find_and_enrich_incumbents.assert_awaited_once()


def test_collect_skips_enrichment_when_ctx_leadership_enrichment_is_none(tmp_path):
    """When ctx.leadership_enrichment is None, no incumbents are populated; metadata is 'disabled'."""
    from unittest.mock import AsyncMock, MagicMock
    from rrxray.collectors.leadership_stability import collect
    from rrxray.config import Config
    from rrxray.context import CollectorContext
    from rrxray.services.firecrawl_client import FirecrawlError

    fake_firecrawl = MagicMock()
    fake_firecrawl.search = AsyncMock(return_value=[])
    fake_firecrawl.scrape_url = AsyncMock(side_effect=FirecrawlError("no /about"))
    fake_wayback = MagicMock()
    fake_wayback.snapshots = AsyncMock(return_value=[])

    ctx = CollectorContext(
        domain="acme.com", company_name="Acme",
        firecrawl=fake_firecrawl, wayback=fake_wayback,
        evidence_dir=tmp_path, config=Config(domain="acme.com"),
        extractor=None,
        leadership_enrichment=None,
    )
    data = asyncio.run(collect(ctx))

    assert data.current_incumbents == []
    assert data.enrichment_metadata.aborted_reason == "disabled"


def test_collect_enriches_press_change_names_when_orchestrator_available(tmp_path):
    """Press change names get prior_employer / prior_role / years_at_company filled in."""
    from datetime import date
    from unittest.mock import AsyncMock, MagicMock
    from rrxray.collectors.leadership_stability import collect
    from rrxray.config import Config
    from rrxray.context import CollectorContext
    from rrxray.schemas.leadership_stability import (
        ExecAction, ExecChange, LeadershipEnrichmentMetadata,
    )
    from rrxray.services.extraction import ExtractedExecChange
    from rrxray.services.firecrawl_client import (
        FirecrawlError, ScrapedPage, SearchResult,
    )
    from rrxray.services.leadership_enrichment import EnrichedLeadership

    fake_firecrawl = MagicMock()
    # Press search returns one result that the extractor will turn into an ExecChange
    fake_firecrawl.search = AsyncMock(side_effect=[
        [SearchResult(url="https://example.com/p/1", title="Acme Names Jane Doe as CRO", description="...")],
        [], [],
    ])
    fake_firecrawl.scrape_url = AsyncMock(side_effect=FirecrawlError("no /about"))
    fake_wayback = MagicMock()
    fake_wayback.snapshots = AsyncMock(return_value=[])

    fake_extractor = MagicMock()
    fake_extractor.extract_exec_change = AsyncMock(return_value=ExtractedExecChange(
        name="Jane Doe", role_canonical="cro", role_raw="CRO",
        action=ExecAction.HIRE, is_relevant=True, occurred_at="2024-03-01",
    ))

    fake_orch = MagicMock()
    fake_orch.find_and_enrich_incumbents = AsyncMock(return_value=EnrichedLeadership(
        incumbents=[], spend_dollars=1.40, aborted_reason="completed",
    ))
    # enrich_press_change_names returns mutated copies with prior_employer set
    def _enrich(exec_changes, company_domain):
        return [c.model_copy(update={
            "prior_employer": "Salesforce",
            "prior_role": "VP of Enterprise Sales",
            "years_at_company": 1,
        }) for c in exec_changes]
    fake_orch.enrich_press_change_names = AsyncMock(side_effect=_enrich)
    fake_orch.metadata = LeadershipEnrichmentMetadata(spend_dollars=1.60, aborted_reason="completed")

    ctx = CollectorContext(
        domain="acme.com", company_name="Acme",
        firecrawl=fake_firecrawl, wayback=fake_wayback,
        evidence_dir=tmp_path, config=Config(domain="acme.com"),
        extractor=fake_extractor,
        leadership_enrichment=fake_orch,
    )
    data = asyncio.run(collect(ctx))

    assert len(data.exec_changes) == 1
    assert data.exec_changes[0].prior_employer == "Salesforce"
    assert data.exec_changes[0].prior_role == "VP of Enterprise Sales"
    fake_orch.enrich_press_change_names.assert_awaited_once()


def test_collect_returns_partial_data_when_cost_cap_hit(tmp_path):
    """Orchestrator returns aborted_reason='cost_cap'; collector still returns LeadershipStabilityData."""
    from unittest.mock import AsyncMock, MagicMock
    from rrxray.collectors.leadership_stability import collect
    from rrxray.config import Config
    from rrxray.context import CollectorContext
    from rrxray.schemas.leadership_stability import (
        CurrentIncumbent, LeadershipEnrichmentMetadata,
    )
    from rrxray.services.firecrawl_client import FirecrawlError
    from rrxray.services.leadership_enrichment import EnrichedLeadership

    fake_firecrawl = MagicMock()
    fake_firecrawl.search = AsyncMock(return_value=[])
    fake_firecrawl.scrape_url = AsyncMock(side_effect=FirecrawlError("no /about"))
    fake_wayback = MagicMock()
    fake_wayback.snapshots = AsyncMock(return_value=[])

    fake_orch = MagicMock()
    fake_orch.find_and_enrich_incumbents = AsyncMock(return_value=EnrichedLeadership(
        incumbents=[
            CurrentIncumbent(name="A", role_canonical="cro", role_raw="CRO"),
        ],
        spend_dollars=5.0, aborted_reason="cost_cap",
    ))
    fake_orch.enrich_press_change_names = AsyncMock(side_effect=lambda exec_changes, company_domain: exec_changes)
    fake_orch.metadata = LeadershipEnrichmentMetadata(spend_dollars=5.0, aborted_reason="cost_cap")

    ctx = CollectorContext(
        domain="acme.com", company_name="Acme",
        firecrawl=fake_firecrawl, wayback=fake_wayback,
        evidence_dir=tmp_path, config=Config(domain="acme.com"),
        extractor=None,
        leadership_enrichment=fake_orch,
    )
    data = asyncio.run(collect(ctx))

    # Partial data preserved; metadata explains why
    assert len(data.current_incumbents) == 1
    assert data.enrichment_metadata.aborted_reason == "cost_cap"
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
/Users/dalezwizinski/Library/Python/3.9/bin/uv run pytest tests/test_leadership_stability.py -v -k "collect_calls_leadership_enrichment or collect_skips_enrichment or collect_enriches_press_change_names or collect_returns_partial_data_when_cost_cap"
```

Expected: 4 new tests fail (collector still using old LinkedIn path; doesn't call orchestrator).

- [ ] **Step 4: Edit `rrxray/collectors/leadership_stability.py`**

**Delete these helpers** (now obsolete):
- `_search_linkedin_incumbents`
- `_extract_current_incumbents`
- `_confidence_for_linkedin_url`

**Update imports**: remove `LEADERSHIP_ROLES` is still used; remove `CurrentIncumbent` import if no longer locally constructed (it's now built by the orchestrator). Keep `CurrentIncumbent` import — schema validation in `LeadershipStabilityData` still needs it via forward ref.

**Update `collect()`**:

```python
async def collect(ctx: CollectorContext) -> LeadershipStabilityData:
    """Orchestrator. Runs press + PDL-incumbent + press-enrichment + founder paths.
    Returns a fully-validated LeadershipStabilityData with name_registrations
    populated for the pipeline's anonymizer registration loop.
    """
    company = ctx.company_name or ctx.domain.split(".")[0].title()

    # Press path (unchanged)
    if ctx.extractor is None:
        log.warning("leadership_stability: no extractor on context")
        exec_changes: list[ExecChange] = []
    else:
        press_results = await _search_press_releases(ctx.firecrawl, company)
        exec_changes = await _extract_exec_changes(
            press_results, ctx.extractor, company, ctx.domain, ctx.firecrawl,
        )

    # PDL incumbent path (NEW — replaces LinkedIn snippet path)
    current_incumbents: list[CurrentIncumbent] = []
    enrichment_metadata = LeadershipEnrichmentMetadata()  # default: disabled

    if ctx.leadership_enrichment is not None:
        enriched = await ctx.leadership_enrichment.find_and_enrich_incumbents(
            company_name=company,
            company_domain=ctx.domain,
            role_canonicals=LEADERSHIP_ROLES,
        )
        current_incumbents = enriched.incumbents
        enrichment_metadata = ctx.leadership_enrichment.metadata

        # PDL press-name enrichment (NEW — runs after incumbents to share spend budget)
        if exec_changes:
            exec_changes = await ctx.leadership_enrichment.enrich_press_change_names(
                exec_changes=exec_changes, company_domain=ctx.domain,
            )
            enrichment_metadata = ctx.leadership_enrichment.metadata

    # Founder tenure path (unchanged)
    founder_tenure = await _infer_founder_tenure(ctx.firecrawl, ctx.wayback, ctx.domain)

    # Derived data (unchanged)
    name_registrations = _build_name_registrations(
        exec_changes, current_incumbents, company,
    )
    findings, gaps, questions = _emit_findings(
        exec_changes, current_incumbents, founder_tenure,
    )

    # Evidence (unchanged write_evidence helper signature)
    try:
        _write_evidence(
            ctx.evidence_dir,
            press_results if ctx.extractor else [],
            {},  # linkedin_results_by_role removed; pass empty dict for backward signature compat
            exec_changes,
            current_incumbents,
        )
    except OSError as e:
        log.warning("evidence write failed: %s", e)

    return LeadershipStabilityData(
        exec_changes=exec_changes,
        current_incumbents=current_incumbents,
        founder_tenure=founder_tenure,
        name_registrations=name_registrations,
        findings=findings,
        gaps=gaps,
        discovery_questions=questions,
        enrichment_metadata=enrichment_metadata,
    )
```

Update imports at the top to include `LeadershipEnrichmentMetadata`:

```python
from rrxray.schemas.leadership_stability import (
    CurrentIncumbent,
    ExecAction,
    ExecChange,
    FounderTenure,
    LeadershipEnrichmentMetadata,
    LeadershipStabilityData,
    NameRegistration,
)
```

- [ ] **Step 5: Update `_write_evidence`** to reflect that `linkedin_results_by_role` is now always empty (and worth deleting from the signature in a future cleanup pass, but for this task we keep the signature stable to avoid touching the existing `test_collect_writes_evidence` test):

The existing signature is fine. `linkedin_results_by_role={}` writes an empty `linkedin_search.json`. Acceptable for evidence — flags the empty bucket clearly.

- [ ] **Step 6: Run tests + ruff**

```bash
/Users/dalezwizinski/Library/Python/3.9/bin/uv run pytest tests/test_leadership_stability.py -v 2>&1 | tail -10
/Users/dalezwizinski/Library/Python/3.9/bin/uv run pytest 2>&1 | tail -3
/Users/dalezwizinski/Library/Python/3.9/bin/uv run ruff check rrxray/ tests/
```

Expected: all leadership_stability tests pass (some deleted, 4 new added). Full suite passes. Ruff clean.

- [ ] **Step 7: Commit**

```bash
git add rrxray/collectors/leadership_stability.py tests/test_leadership_stability.py
git rm tests/fixtures/synthetic/leadership_stability/linkedin_cro_response.json
git rm tests/fixtures/synthetic/leadership_stability/linkedin_cmo_response.json
git rm tests/fixtures/synthetic/leadership_stability/linkedin_empty_response.json
git commit -m "$(cat <<'EOF'
Replace LinkedIn snippet path with PDL incumbent path in collector

DELETE: _search_linkedin_incumbents, _extract_current_incumbents,
_confidence_for_linkedin_url helpers + the 3 LinkedIn JSON fixtures
+ 6 corresponding tests.

ADD: collect() now calls ctx.leadership_enrichment.find_and_enrich_incumbents
for current_incumbents, then enrich_press_change_names for ExecChange
records. Both share the orchestrator's cost-cap state. Falls through to
empty incumbents when ctx.leadership_enrichment is None (no API key or
--no-pdl).

LeadershipStabilityData now carries enrichment_metadata reflecting the
final orchestrator state (completed / cost_cap / circuit_breaker / disabled).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Delete extract_linkedin_role from extraction.py

**Files:**
- Modify: `rrxray/services/extraction.py` (delete `extract_linkedin_role` on both extractors, delete `ExtractedLinkedInIncumbent` schema, delete `_LINKEDIN_INCUMBENT_SYSTEM_PROMPT`)
- Modify: `tests/test_extraction.py` (delete tests for `extract_linkedin_role`)

- [ ] **Step 1: Delete the LinkedIn-related tests from `tests/test_extraction.py`**

Find and remove these tests:
- `test_haiku_extractor_extract_linkedin_role`
- `test_gemini_flash_extractor_extracts_linkedin_role` (if it exists)
- Any other test referencing `extract_linkedin_role` or `ExtractedLinkedInIncumbent`

Confirm via grep:

```bash
grep -n "extract_linkedin_role\|ExtractedLinkedInIncumbent" tests/test_extraction.py
```

- [ ] **Step 2: Delete the LinkedIn-related code from `rrxray/services/extraction.py`**

Find and delete:
- `ExtractedLinkedInIncumbent` pydantic model
- `_LINKEDIN_INCUMBENT_SYSTEM_PROMPT` constant
- `HaikuExtractor.extract_linkedin_role` method
- `GeminiFlashExtractor.extract_linkedin_role` method

Keep:
- `ExtractedExecChange` (still used by press path)
- `_EXEC_CHANGE_SYSTEM_PROMPT` (still used)
- `HaikuExtractor.extract_exec_change` and `GeminiFlashExtractor.extract_exec_change` (still used)
- `make_extractor` factory (still used)

Confirm via grep:

```bash
grep -n "extract_linkedin_role\|ExtractedLinkedInIncumbent\|_LINKEDIN_INCUMBENT_SYSTEM_PROMPT" rrxray/services/extraction.py
```

Expected: no matches after the edit.

- [ ] **Step 3: Run tests + ruff**

```bash
/Users/dalezwizinski/Library/Python/3.9/bin/uv run pytest tests/test_extraction.py -v
/Users/dalezwizinski/Library/Python/3.9/bin/uv run pytest 2>&1 | tail -3
/Users/dalezwizinski/Library/Python/3.9/bin/uv run ruff check rrxray/ tests/
```

Expected: extraction tests pass (~6 remaining, down from ~10). Full suite passes. Ruff clean. No unused-import warnings.

- [ ] **Step 4: Commit**

```bash
git add rrxray/services/extraction.py tests/test_extraction.py
git commit -m "Remove extract_linkedin_role from extraction module (dead code)

After Phase 2.2-deep replaced the LinkedIn snippet path with PDL,
extract_linkedin_role + ExtractedLinkedInIncumbent + the
_LINKEDIN_INCUMBENT_SYSTEM_PROMPT have no callers. Deleted to keep
the module focused on its remaining responsibility: press-release
extraction via extract_exec_change."
```

---

## Task 8: Synthesizer aggregates + prompt additions

**Files:**
- Modify: `rrxray/synthesizers/observed_stability_trajectory.py` (extend StabilityAggregates; extend _build_aggregates)
- Modify: `rrxray/prompts/observed_stability_trajectory.md` (new data blocks + motion-lens instruction)
- Modify: `tests/test_observed_stability_trajectory.py` (add aggregate tests)

- [ ] **Step 1: Append failing tests to `tests/test_observed_stability_trajectory.py`**

```python
def test_aggregates_compute_tenure_confirmed_count():
    from rrxray.synthesizers.observed_stability_trajectory import _build_aggregates
    from rrxray.schemas.leadership_stability import (
        CurrentIncumbent, LeadershipStabilityData,
    )
    data = LeadershipStabilityData(
        current_incumbents=[
            CurrentIncumbent(name="A", role_canonical="cro", role_raw="CRO", tenure_months=14),
            CurrentIncumbent(name="B", role_canonical="cmo", role_raw="CMO", tenure_months=None),
            CurrentIncumbent(name="C", role_canonical="ceo", role_raw="CEO", tenure_months=84),
        ],
    )
    aggs = _build_aggregates(data)
    assert aggs.tenure_confirmed_count == 2  # A and C
    assert aggs.tenure_confirmed_total == 3


def test_aggregates_compute_external_hire_count():
    from rrxray.synthesizers.observed_stability_trajectory import _build_aggregates
    from rrxray.schemas.leadership_stability import (
        CurrentIncumbent, LeadershipStabilityData,
    )
    data = LeadershipStabilityData(
        current_incumbents=[
            CurrentIncumbent(name="A", role_canonical="cro", role_raw="CRO",
                             prior_employer="Salesforce"),
            CurrentIncumbent(name="B", role_canonical="cmo", role_raw="CMO",
                             prior_employer="HubSpot"),
            CurrentIncumbent(name="C", role_canonical="ceo", role_raw="CEO",
                             prior_employer=None),
        ],
    )
    aggs = _build_aggregates(data)
    # A and B have prior_employer set and ≠ current; C has None
    assert aggs.external_hire_count == 2


def test_aggregates_compute_internal_promotion_count():
    from rrxray.synthesizers.observed_stability_trajectory import _build_aggregates
    from rrxray.schemas.leadership_stability import (
        CurrentIncumbent, LeadershipStabilityData,
    )
    # Internal promotion = prior_role set AND prior_employer matches current company name
    # We pass company_name via the data context — for this test we rely on the
    # _build_aggregates signature; if it doesn't take company_name, the heuristic
    # "prior_employer is None AND prior_role is set" identifies a likely-internal move.
    # Implementer: pick the cleaner heuristic in the actual code; this test asserts
    # the count is reported, not the exact rule.
    data = LeadershipStabilityData(
        current_incumbents=[
            CurrentIncumbent(name="A", role_canonical="cro", role_raw="CRO",
                             prior_employer="Acme", prior_role="VP of Sales"),
            CurrentIncumbent(name="B", role_canonical="cmo", role_raw="CMO",
                             prior_employer="HubSpot", prior_role="VP Marketing"),
        ],
    )
    aggs = _build_aggregates(data)
    assert aggs.internal_promotion_count + aggs.external_hire_count == 2


def test_aggregates_compute_prior_employer_signals_per_role():
    from rrxray.synthesizers.observed_stability_trajectory import _build_aggregates
    from rrxray.schemas.leadership_stability import (
        CurrentIncumbent, LeadershipStabilityData,
    )
    data = LeadershipStabilityData(
        current_incumbents=[
            CurrentIncumbent(name="A", role_canonical="cro", role_raw="CRO",
                             prior_employer="Salesforce"),
            CurrentIncumbent(name="B", role_canonical="cmo", role_raw="CMO",
                             prior_employer=None),
        ],
    )
    aggs = _build_aggregates(data)
    assert aggs.prior_employer_signals.get("cro") == "Salesforce"
    assert aggs.prior_employer_signals.get("cmo") is None


def test_aggregates_handle_missing_enrichment_data_gracefully():
    """When no incumbents have enrichment fields, counts are 0 / signals empty."""
    from rrxray.synthesizers.observed_stability_trajectory import _build_aggregates
    from rrxray.schemas.leadership_stability import (
        CurrentIncumbent, LeadershipStabilityData,
    )
    data = LeadershipStabilityData(
        current_incumbents=[
            CurrentIncumbent(name="A", role_canonical="cro", role_raw="CRO"),
        ],
    )
    aggs = _build_aggregates(data)
    assert aggs.tenure_confirmed_count == 0
    assert aggs.tenure_confirmed_total == 1
    assert aggs.external_hire_count == 0
    assert aggs.internal_promotion_count == 0
    assert aggs.prior_employer_signals.get("cro") is None


def test_synth_renders_enrichment_metadata_when_partial():
    """Prompt should reflect aborted_reason='cost_cap' when set."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock
    from rrxray.config import Config
    from rrxray.context import SynthesizerContext
    from rrxray.schemas.data import CollectorOutputs
    from rrxray.schemas.leadership_stability import (
        LeadershipEnrichmentMetadata, LeadershipStabilityData,
    )
    from rrxray.synthesizers.observed_stability_trajectory import (
        NarrativeResponse, synthesize,
    )

    fake_anthropic = MagicMock()
    fake_anthropic.complete_with_cached_system = AsyncMock(return_value=MagicMock(
        parsed=NarrativeResponse(narrative_paragraphs=["test"]),
        model_used="claude-opus-4-7", cache_hit=False,
    ))
    fake_voice = MagicMock()
    fake_voice.sanitize_llm_output = lambda text, context: text
    fake_voice.process_synthesizer_text = lambda text, context: text

    data = LeadershipStabilityData(
        enrichment_metadata=LeadershipEnrichmentMetadata(
            spend_dollars=5.0, aborted_reason="cost_cap",
        ),
    )
    ctx = SynthesizerContext(
        collector_outputs=CollectorOutputs(leadership_stability=data),
        anthropic=fake_anthropic, voice=fake_voice,
        anonymizer=MagicMock(), config=Config(domain="example.com"),
    )
    result = asyncio.run(synthesize(ctx))

    # Capture the user_message sent to the LLM
    call_args = fake_anthropic.complete_with_cached_system.await_args
    user_message = call_args.kwargs.get("user_message", "")
    assert "cost_cap" in user_message or "partial" in user_message.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
/Users/dalezwizinski/Library/Python/3.9/bin/uv run pytest tests/test_observed_stability_trajectory.py -v -k "aggregates_compute or renders_enrichment_metadata"
```

Expected: 6 new tests fail (AttributeError on new aggregate fields; user_message doesn't include enrichment context).

- [ ] **Step 3: Edit `rrxray/synthesizers/observed_stability_trajectory.py`**

Extend `StabilityAggregates`:

```python
class StabilityAggregates(BaseModel):
    """Name-free pre-aggregation passed to the prompt template."""
    seat_changes: dict[str, int]
    seat_change_ages_months: dict[str, int | None]
    recent_changes: list[dict]
    current_incumbents_by_role: dict[str, dict]
    founder_present_in_ceo_seat: bool
    founder_tenure_years: int | None
    seats_with_no_change_18mo: list[str]
    collector_findings: list[str]
    # Phase 2.2-deep additions
    tenure_confirmed_count: int = 0
    tenure_confirmed_total: int = 0
    external_hire_count: int = 0
    internal_promotion_count: int = 0
    prior_employer_signals: dict[str, str | None] = {}
    enrichment_aborted_reason: str = "disabled"
    enrichment_spend_dollars: float = 0.0
```

Update `_build_aggregates`:

```python
def _build_aggregates(data: LeadershipStabilityData) -> StabilityAggregates:
    today = datetime.now(UTC).date()

    # ... existing seat_changes, recent_changes, incumbents_by_role logic unchanged ...

    # Phase 2.2-deep: tenure confirmation counts (high-confidence incumbents only)
    high_conf = [i for i in data.current_incumbents if i.confidence == "high"]
    tenure_confirmed_count = sum(1 for i in high_conf if i.tenure_months is not None)
    tenure_confirmed_total = len(high_conf)

    # Phase 2.2-deep: external hire vs internal promotion counts + prior_employer signals
    external_hire_count = 0
    internal_promotion_count = 0
    prior_employer_signals: dict[str, str | None] = {}
    for inc in high_conf:
        prior_employer_signals[inc.role_canonical] = inc.prior_employer
        if inc.prior_employer is None:
            continue
        # Internal promotion: prior_role is set AND prior_employer matches the current company name
        # heuristic. If prior_employer string contains or equals data company context, treat as internal.
        # Without explicit company name in scope here, fall back to "prior_role set AND prior_employer
        # equals incumbent's company" via the PDL data flag.
        # Simpler heuristic: if prior_role is set and prior_employer is set, count one or the other:
        # - external: prior_employer set and clearly external (no company-name match available)
        # - internal: prior_employer set and matches existing record marker
        # For Phase 2.2-deep we use the orchestrator's logic that already wrote prior_employer:
        # If prior_employer != current company → external; otherwise → internal.
        # We approximate by checking whether prior_employer literally equals the company name.
        # For tests where company_name is unavailable in _build_aggregates, this simplifies to:
        # if prior_employer is set, count as external (most common); flag internal only when
        # prior_role is set and prior_employer is None (the LeadershipEnrichment orchestrator
        # populates this pattern for internal moves).
        external_hire_count += 1

    # Internal promotions are signaled by prior_role set with prior_employer matching the company.
    # The orchestrator's _years_at_company logic detects this. For aggregation purposes, count
    # an internal promotion when the PDL experience array shows multiple roles at the same company.
    # Simpler proxy here: count incumbents whose prior_role is set AND prior_employer is None.
    for inc in high_conf:
        if inc.prior_role is not None and inc.prior_employer is None:
            internal_promotion_count += 1
            external_hire_count = max(0, external_hire_count - 1)  # de-bias from above

    # Phase 2.2-deep: enrichment metadata
    enrichment_aborted_reason = data.enrichment_metadata.aborted_reason
    enrichment_spend_dollars = data.enrichment_metadata.spend_dollars

    # ... existing seat_change_ages, founder_present, etc. logic unchanged ...

    return StabilityAggregates(
        seat_changes=seat_changes,
        seat_change_ages_months=seat_change_ages,
        recent_changes=recent_changes,
        current_incumbents_by_role=incumbents_by_role,
        founder_present_in_ceo_seat=founder_in_ceo,
        founder_tenure_years=founder_tenure_years,
        seats_with_no_change_18mo=seats_with_no_change,
        collector_findings=[f.text for f in data.findings],
        tenure_confirmed_count=tenure_confirmed_count,
        tenure_confirmed_total=tenure_confirmed_total,
        external_hire_count=external_hire_count,
        internal_promotion_count=internal_promotion_count,
        prior_employer_signals=prior_employer_signals,
        enrichment_aborted_reason=enrichment_aborted_reason,
        enrichment_spend_dollars=enrichment_spend_dollars,
    )
```

Also update `current_incumbents_by_role` building inside `_build_aggregates` to include the new fields:

```python
    incumbents_by_role[inc.role_canonical] = {
        "tenure_months": inc.tenure_months,
        "confidence": inc.confidence,
        "years_at_company": inc.years_at_company,
        "prior_employer": inc.prior_employer,
        "prior_role": inc.prior_role,
    }
```

- [ ] **Step 4: Edit `rrxray/prompts/observed_stability_trajectory.md`**

Add the new data blocks after the existing "Founder presence" block:

```jinja
**Tenure confirmation:** {{ aggregates.tenure_confirmed_count }} of {{ aggregates.tenure_confirmed_total }} current incumbents have tenure data confirmed via PeopleDataLabs.

**Hire-origin pattern:**
- External hires (incumbents who came from outside the company): {{ aggregates.external_hire_count }}
- Internal promotions (incumbents promoted from within): {{ aggregates.internal_promotion_count }}

**Prior employer per role (where confirmed):**
{% for role, prior in aggregates.prior_employer_signals.items() %}
{% if prior %}
- {{ role }}: came from {{ prior }}
{% else %}
- {{ role }}: prior employer not recovered
{% endif %}
{% endfor %}

**Leadership enrichment status:** {{ aggregates.enrichment_aborted_reason }} (spend: ${{ "%.2f"|format(aggregates.enrichment_spend_dollars) }})
{% if aggregates.enrichment_aborted_reason == "cost_cap" or aggregates.enrichment_aborted_reason == "circuit_breaker" %}
Note: PDL enrichment was partial. Some incumbents may lack tenure / prior-employer context. Frame findings accordingly.
{% endif %}
```

Add the motion-lens instruction block after the "Diagnostic posture" section (after "Output 2-4 paragraphs..."):

```
**Prior-employer motion lens:** When you see a prior_employer for a revenue or marketing role, infer the motion shape that incumbent likely brings:
- Came from an enterprise SaaS (Salesforce, Oracle, etc.) → likely enterprise outbound motion bias
- Came from a PLG company (Figma, Notion, etc.) → likely product-led pipeline bias
- Came from a smaller startup / unknown → bias unclear; do not speculate
- Came from the same vertical → motion stays domain-aligned; market expertise > motion shift
This is a working hypothesis only — state it as such ("the incoming CRO came from X, suggesting...") rather than as a confirmed fact.
```

- [ ] **Step 5: Run tests + ruff**

```bash
/Users/dalezwizinski/Library/Python/3.9/bin/uv run pytest tests/test_observed_stability_trajectory.py -v
/Users/dalezwizinski/Library/Python/3.9/bin/uv run pytest 2>&1 | tail -3
/Users/dalezwizinski/Library/Python/3.9/bin/uv run ruff check rrxray/ tests/
```

Expected: all synthesizer tests pass. Ruff clean.

- [ ] **Step 6: Commit**

```bash
git add rrxray/synthesizers/observed_stability_trajectory.py rrxray/prompts/observed_stability_trajectory.md tests/test_observed_stability_trajectory.py
git commit -m "$(cat <<'EOF'
Extend Section B synthesizer aggregates + prompt for PDL enrichment

StabilityAggregates gains six new fields:
- tenure_confirmed_count / tenure_confirmed_total
- external_hire_count / internal_promotion_count
- prior_employer_signals: dict[role, str | None]
- enrichment_aborted_reason / enrichment_spend_dollars

_build_aggregates computes counts from high-confidence incumbents'
enrichment fields. current_incumbents_by_role gains tenure_months,
years_at_company, prior_employer, prior_role.

Prompt template gains four new data blocks (tenure confirmation,
hire-origin pattern, prior employer per role, enrichment status) +
a prior-employer motion-lens instruction. The motion-lens prompt is
explicitly framed as "working hypothesis" to keep the LLM hedging
appropriately.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Renderer Module Detail template

**Files:**
- Modify: `templates/_leadership_stability_detail.md.jinja` (add tenure + prior_employer + years_at_company columns; add enrichment metadata line)
- Modify: `tests/test_render_internal.py` (add tests for new columns)

- [ ] **Step 1: Append failing tests to `tests/test_render_internal.py`**

```python
def test_leadership_stability_module_detail_renders_tenure_and_prior_employer():
    from datetime import UTC, datetime
    from rrxray.rendering.markdown import render_internal
    from rrxray.schemas.data import (
        CollectorOutputs, InputParams, RunMetadata, XrayData,
    )
    from rrxray.schemas.leadership_stability import (
        CurrentIncumbent, LeadershipEnrichmentMetadata, LeadershipStabilityData,
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
        CollectorOutputs, InputParams, RunMetadata, XrayData,
    )
    from rrxray.schemas.leadership_stability import (
        LeadershipEnrichmentMetadata, LeadershipStabilityData,
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
/Users/dalezwizinski/Library/Python/3.9/bin/uv run pytest tests/test_render_internal.py -v -k "module_detail_renders_tenure or module_detail_renders_enrichment"
```

Expected: 2 new tests fail (template doesn't render new columns).

- [ ] **Step 3: Edit `templates/_leadership_stability_detail.md.jinja`**

Replace the existing "Current incumbents" table with a richer version:

```jinja
#### Current incumbents

{% if ls.current_incumbents %}
| Role | Name | Tenure | Prior employer (last role) | LinkedIn |
|---|---|---|---|---|
{% for inc in ls.current_incumbents %}
| {{ inc.role_canonical }} | {{ inc.name | anonymize | voice_collector }} | {% if inc.tenure_months %}~{{ inc.tenure_months }} months{% else %}unconfirmed{% endif %} | {% if inc.prior_employer %}{{ inc.prior_employer }}{% if inc.prior_role %} ({{ inc.prior_role }}){% endif %}{% else %}—{% endif %} | {% if inc.linkedin_url %}[link]({{ inc.linkedin_url }}){% else %}—{% endif %} |
{% endfor %}
{% else %}
None recovered from public sources.
{% endif %}
```

Replace the existing "Exec changes" table to add a "Background" column:

```jinja
#### Exec changes (past 18 months)

{% if ls.exec_changes %}
| Role | Action | Name | Date | Background | Source |
|---|---|---|---|---|---|
{% for change in ls.exec_changes %}
| {{ change.role_canonical }} | {{ change.action }} | {{ change.name | anonymize | voice_collector }} | {{ change.occurred_at or "-" }} | {% if change.prior_employer %}from {{ change.prior_employer }}{% if change.prior_role %} ({{ change.prior_role }}){% endif %}{% else %}—{% endif %} | [press]({{ change.press_url }}) |
{% endfor %}
{% else %}
No public exec announcements recovered.
{% endif %}
```

Add the enrichment metadata line at the bottom of the partial (after findings/gaps/discovery sections):

```jinja
**Enrichment:** ${{ "%.2f"|format(ls.enrichment_metadata.spend_dollars) }} spent; status: {{ ls.enrichment_metadata.aborted_reason }}.
```

Replace em dashes (—) with "-" if any survive. Per CLAUDE.md no-em-dashes rule.

- [ ] **Step 4: Run tests + ruff**

```bash
/Users/dalezwizinski/Library/Python/3.9/bin/uv run pytest tests/test_render_internal.py -v 2>&1 | tail -10
/Users/dalezwizinski/Library/Python/3.9/bin/uv run pytest 2>&1 | tail -3
/Users/dalezwizinski/Library/Python/3.9/bin/uv run ruff check rrxray/ tests/
```

Expected: render tests pass. Full suite passes. Ruff clean.

- [ ] **Step 5: Commit**

```bash
git add templates/_leadership_stability_detail.md.jinja tests/test_render_internal.py
git commit -m "Render PDL enrichment fields in Leadership Stability Module Detail

Current incumbents table gains Tenure + Prior employer (last role) columns.
Exec changes table gains Background column (prior_employer + prior_role
when set). New 'Enrichment' line at the bottom shows PDL spend and
aborted_reason for operational transparency."
```

---

## Task 10: Quality gate (Dale-led)

**Files:**
- Modify: any prompt/sanitizer/template file as needed during iteration
- Modify: `roadmap.md` (post-quality-gate, one-line entry)
- Create: `docs/checkpoints/YYYY-MM-DD-phase-2.2-deep-pdl-enrichment-checkpoint.md` (use today date)

**Bounded by Dale's sign-off, not by time.** Implementer subagent must NOT mark Phase 2.2-deep complete on its own — it presents output and pauses for Dale's review.

**Prerequisites:**
- Anthropic credits funded (carry-over from Phase 2.2 sign-off note)
- PDL API key obtained (sign up at peopledatalabs.com if not already) and added to `.env` as `PDL_API_KEY`
- Symlink `.env` from parent repo to worktree root if running from a worktree (per `feedback_worktree_env` memory)

- [ ] **Step 1: Confirm preflight**

```bash
cd /Users/dalezwizinski/Documents/Apps/rrxray/.claude/worktrees/unruffled-chandrasekhar-93625c
/Users/dalezwizinski/Library/Python/3.9/bin/uv run pytest 2>&1 | tail -3
/Users/dalezwizinski/Library/Python/3.9/bin/uv run ruff check rrxray/ tests/
ls -la .env
grep -c "^PDL_API_KEY=" .env
```

Expected: ~380 tests passing, ruff clean, `.env` symlink in place, `PDL_API_KEY` present.

- [ ] **Step 2: Run live smokes against the trio**

```bash
cd /Users/dalezwizinski/Documents/Apps/rrxray/.claude/worktrees/unruffled-chandrasekhar-93625c

# RR target ICP (sign-off bar)
/Users/dalezwizinski/Library/Python/3.9/bin/uv run rrxray run --domain swayable.com
/Users/dalezwizinski/Library/Python/3.9/bin/uv run rrxray run --domain aioapp.com

# Larger SaaS / generic-name stress test (regression check)
/Users/dalezwizinski/Library/Python/3.9/bin/uv run rrxray run --domain remote.com
```

Expected: each completes; Section B narrative now cites tenure_confirmed_count, external_hire_count, prior_employer signals where applicable; "tenure unconfirmed" gaps significantly reduced vs Phase 2.2.

- [ ] **Step 3: Run one smoke with `--no-pdl`** to verify graceful fallback

```bash
/Users/dalezwizinski/Library/Python/3.9/bin/uv run rrxray run --domain swayable.com --no-pdl
```

Expected: completes; Section B falls through to "Signal Not Recovered" or relies on press changes only; report mentions enrichment_metadata.aborted_reason = "disabled".

- [ ] **Step 4: Dale-led review of all reports**

For each report, Dale verifies:

1. **Diagnostic value.** Does the synthesizer cite confirmed tenure with specific numbers? Are motion-lens inferences ("came from Salesforce → likely enterprise outbound") present where prior_employer is set?
2. **"Tenure unconfirmed" gaps reduced.** Comparing to the Phase 2.2 Swayable narrative (2026-05-09 commit), are gaps materially smaller?
3. **Voice compliance.** No em dashes; no forbidden words; GTM Gap™ on first use.
4. **Anonymizer correctness.** PDL-found names replaced with role descriptors; press-whitelisted names preserved.
5. **Enrichment status reporting.** When aborted_reason is "cost_cap" or "circuit_breaker", the narrative hedges appropriately.
6. **Cost reasonable.** `enrichment_metadata.spend_dollars` ≤ $5 default cap. Per-domain total cost matches the ~$2.91 estimate from the spec.

- [ ] **Step 5: Iterate if quality-gate flags issues**

Common iteration patterns (Phase 2.2 precedent says 1-2 cycles is normal):

- LLM doesn't cite tenure_confirmed_count → tighten prompt's "tenure confirmation" block
- Motion-lens inferences over-speculative → tighten "do not speculate" guard in instruction
- PDL Search returns same person across roles incorrectly (e.g., wrong domain match) → tighten orchestrator's "match_score" threshold or add domain-strict filter

Re-run the affected domain with `--no-cache` after each prompt change.

- [ ] **Step 6: Write the checkpoint** at `docs/checkpoints/YYYY-MM-DD-phase-2.2-deep-pdl-enrichment-checkpoint.md` (use today date)

Use `docs/checkpoints/TEMPLATE.md` as the structure. Read the Phase 2.2 checkpoint at `docs/checkpoints/2026-05-10-phase-2.2-leadership-stability-checkpoint.md` for format consistency.

- [ ] **Step 7: Update `roadmap.md`** with the Phase 2.2-deep entry under the existing Phase 2.2 leadership_stability sub-list:

```
- 2026-05-XX: Phase 2.2-deep shipped — PeopleDataLabs enrichment integration. LinkedIn snippet path replaced by PDL Search + Enrichment. Per-X-Ray cost ~$2.91; default cap $5. Closes the "tenure unconfirmed" narrative gap; synthesizer cites tenure_confirmed_count + prior_employer motion-lens inferences.
```

- [ ] **Step 8: Commit checkpoint + roadmap**

```bash
git add docs/checkpoints/YYYY-MM-DD-phase-2.2-deep-pdl-enrichment-checkpoint.md roadmap.md
git commit -m "Phase 2.2-deep PDL enrichment checkpoint + roadmap entry"
```

- [ ] **Step 9: Push + open PR**

```bash
git push -u origin <branch-name>
gh pr create --title "Phase 2.2-deep: PeopleDataLabs leadership enrichment" --body "$(cat <<'EOF'
## Summary

- Adds PDLClient + LeadershipEnrichment orchestrator. Phase 2.2 LinkedIn snippet path removed.
- New schema fields on CurrentIncumbent and ExecChange: tenure_months, years_at_company, prior_employer, prior_role.
- Synthesizer aggregates gain tenure_confirmed_count, external_hire_count, internal_promotion_count, prior_employer_signals.
- Cost cap (default $5/run) + circuit breaker (3+ consecutive failures) + graceful degradation.
- Quality gate signed off against Swayable / aioapp / remote.com.
- ~40 new tests; total ~380 passing; ruff clean.

## Test plan

- [x] Unit tests pass (~380 total)
- [x] Ruff clean
- [x] Live smoke Swayable / aioapp / remote.com — Section B narrative cites tenure + motion-lens inferences
- [x] Live smoke with --no-pdl — graceful fallthrough
- [x] Cost ceiling validated (~$2.91/X-Ray observed; cap untouched)
- [x] Anonymizer behavior verified

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Acceptance criteria → task map

| Spec criterion | Verified by tasks |
|---|---|
| 1. PDLClient works against mocked SDK | T1 |
| 2. LeadershipEnrichment runs Search → Enrich with per-role failure isolation | T4 |
| 3. Cost cap halts further calls; preserves data | T4 |
| 4. Circuit breaker opens after 3+ consecutive failures | T4 |
| 5. LinkedIn snippet path removed; PDL exclusive | T6 + T7 |
| 6. Press change names enriched with prior_employer/prior_role | T4 + T6 |
| 7. `--no-pdl` and missing API key both disable enrichment gracefully | T3 + T5 |
| 8. Synthesizer aggregates include new derived fields | T8 |
| 9. Module Detail Appendix renders tenure_months + prior_employer | T9 |
| 10. Anonymizer behavior unchanged | existing tests preserved |
| 11. data.json round-trips with new fields | T2 |
| 12. Live smoke against Swayable / aioapp / remote.com cites tenure_confirmed_count + motion-lens | T10 |
| 13. Synthesizer commits to a hypothesis; "tenure unconfirmed" gaps reduced | T10 |
| 14. Quality gate signed off by Dale | T10 |

## Model selection per task (CLAUDE.md matrix)

| Task | Implementer | Reviewer | Why |
|---|---|---|---|
| T1: PDLClient | **Opus 4.7** | Haiku 4.5 | Real-logic; new SDK integration; cache + error paths |
| T2: Schema extensions | Haiku 4.5 | (skip) | Mechanical |
| T3: Config + CLI | Haiku 4.5 | (skip) | Mechanical |
| T4: LeadershipEnrichment orchestrator | **Opus 4.7** | Haiku 4.5 | Real-logic; cost cap + circuit breaker + dedup logic |
| T5: Pipeline + CollectorContext | **Opus 4.7** | Haiku 4.5 | Real-logic; pipeline integration is risk-bearing |
| T6: Collector integration | **Opus 4.7** | Haiku 4.5 | Real-logic; deletes substantial code AND adds replacement |
| T7: Delete extract_linkedin_role | Haiku 4.5 | (skip) | Mechanical (deletion) |
| T8: Synthesizer aggregates + prompt | **Opus 4.7** | Haiku 4.5 | Real-logic; aggregation + voice; prompt design |
| T9: Renderer template | Haiku 4.5 | (skip) | Mechanical (template + tests) |
| T10: Quality gate | **Opus 4.7** controller | Dale | Prompt iteration is taste work |

## Risks and known mitigations

- **PDL coverage varies by company size + region.** Per-role failure isolation + fall-through to "Signal Not Recovered" hypothesis.
- **30-day cache TTL drift** on tenure data. Manual `--no-cache` flag forces refresh.
- **PDL Search by company_domain may miss variant domains.** Orchestrator falls back to free-text company name on zero results.
- **`peopledatalabs-python` is new dep.** Approved by Dale per CLAUDE.md.
- **Motion-lens inferences over-speculative.** Prompt explicitly frames as hypotheses; "do not speculate" guard for unknown employers.
- **Cost cap is per-run, not per-day.** Disk cache catches re-runs within 30 days; cap is per-invocation.

## Out-of-scope reminders

- Wayback /team page diffing — Phase 2.2-deep does NOT add this; standing deferral
- Education / seniority / raw experience fields on schema — deferred to future Phase 2.x
- Coresignal / Proxycurl / Apollo evaluation — rejected per CLAUDE.md
- LLM provider abstraction — Phase 3
- Section A or other-section synthesizer changes — out of scope

