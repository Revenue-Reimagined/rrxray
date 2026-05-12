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

    def _redact_for_log(self, exc: Exception) -> str:
        """Generic, key-free description of an SDK exception for logging.

        Some HTTP libraries echo request URLs / Authorization headers into
        exception messages; logging `str(e)` would leak `self.api_key`. We
        log only the exception type and a fixed phrase.
        """
        return f"{type(exc).__name__}"

    def _sanitize_error_message(self, message: str) -> str:
        """Strip api_key from a message before raising it as PDLError."""
        if self.api_key and self.api_key in message:
            return message.replace(self.api_key, "[REDACTED]")
        return message

    async def search_people(
        self,
        company_domain: str,
        search_spec: dict[str, Any],
        size: int = 3,
    ) -> list[PDLSearchResult]:
        """Person Search by (company_domain, search_spec). Returns ranked matches.

        search_spec is a dict with up to three optional keys:
          - role: exact `job_title_role` (e.g. "sales", "marketing")
          - levels: list of `job_title_levels` (e.g. ["cxo"], ["vp"])
          - title_keywords: list of lowercase substrings — each wrapped as
            `*<keyword>*` and OR'd as wildcard clauses on `job_title`

        At least one of these keys must be present (empty spec rejected to
        avoid degenerate "all people at company" queries that burn budget).

        Caches by (company_domain, search_spec, size); 30-day TTL via DiskCache.
        Raises PDLError on terminal SDK failure (200-no-match is NOT an error).
        """
        # Reject empty spec — would otherwise return every person at the
        # company, defeating the role-targeted budget model.
        if not any(k in search_spec for k in ("role", "levels", "title_keywords")):
            raise PDLError(
                "search spec must have at least one of role/levels/title_keywords",
            )

        # PDL indexes job_company_website lowercased; normalize so callers
        # passing mixed-case domains still match.
        domain_lower = company_domain.lower()

        # Cache key includes the canonicalized spec so two calls with the
        # same logical query share the entry.
        args = {
            "domain": domain_lower,
            "spec": _canonicalize_spec(search_spec),
            "size": size,
        }

        async def upstream() -> dict[str, Any]:
            try:
                response = await asyncio.to_thread(
                    self._build_search_call, domain_lower, search_spec, size,
                )
            except asyncio.CancelledError:
                raise
            except Exception as e:
                # Some SDK exceptions echo request URLs/headers that include
                # the api_key. Log only the exception type; raise a sanitized
                # PDLError so the key cannot reach callers/UI either.
                log.warning("PDL search failed (%s)", self._redact_for_log(e))
                raise PDLError(
                    self._sanitize_error_message(f"search_people failed: {e}"),
                ) from e
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

    def _build_search_call(
        self, company_domain: str, search_spec: dict[str, Any], size: int,
    ) -> dict[str, Any]:
        """Synchronous SDK call wrapped by asyncio.to_thread.

        Builds a PDL Elasticsearch DSL query from `search_spec`:
          - company_domain → `term: job_company_website`
          - spec["role"] → `term: job_title_role`
          - spec["levels"] → `terms: job_title_levels`
          - spec["title_keywords"] → nested `bool/should` of wildcard clauses
            on `job_title`, each wrapped as `*<keyword>*`

        SQL was the previous path; PDL's SQL adapter does exact-match on
        the lowercased written title (e.g. "vice president of sales"), not
        on canonical role/level fields, which produced 0 hits for titles
        like "VP Sales". ES DSL hits the indexed classification fields
        directly.
        """
        must_clauses: list[dict[str, Any]] = [
            {"term": {"job_company_website": company_domain}},
        ]

        role = search_spec.get("role")
        if role:
            must_clauses.append({"term": {"job_title_role": role}})

        levels = search_spec.get("levels")
        if levels:
            must_clauses.append({"terms": {"job_title_levels": list(levels)}})

        title_keywords = search_spec.get("title_keywords")
        if title_keywords:
            should_clauses = [
                {"wildcard": {"job_title": f"*{kw.lower()}*"}}
                for kw in title_keywords
            ]
            must_clauses.append({"bool": {"should": should_clauses}})

        es_query = {"bool": {"must": must_clauses}}
        response = self._sdk.person.search(query=es_query, size=size, pretty=True)
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
                # See note in search_people: sanitize api_key out of the log
                # and the raised PDLError before they reach callers.
                log.warning("PDL enrichment failed (%s)", self._redact_for_log(e))
                raise PDLError(
                    self._sanitize_error_message(f"enrich_person failed: {e}"),
                ) from e
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
        # PDL does not guarantee ordering of experience across responses. We
        # explicitly sort by end_date descending so previous_companies[0] is the
        # most recent prior employer (the orchestrator depends on this). Missing
        # or None end_date sorts to the end of the prior-roles list. The current
        # role (end_date=None) is skipped below.
        def _end_date_key(exp: object) -> str:
            if not isinstance(exp, dict):
                return ""
            v = exp.get("end_date")
            return v if isinstance(v, str) else ""
        sorted_experience = sorted(experience, key=_end_date_key, reverse=True)
        for exp in sorted_experience:
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


def _canonicalize_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """Canonicalize a search_spec dict for stable cache-key hashing.

    list-typed values (levels, title_keywords) are sorted so two callers
    passing the same set in different orders share the cache entry.
    """
    canon: dict[str, Any] = {}
    if "role" in spec:
        canon["role"] = spec["role"]
    if "levels" in spec:
        canon["levels"] = sorted(list(spec["levels"]))
    if "title_keywords" in spec:
        canon["title_keywords"] = sorted(list(spec["title_keywords"]))
    return canon
