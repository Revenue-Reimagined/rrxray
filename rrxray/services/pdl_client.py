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
