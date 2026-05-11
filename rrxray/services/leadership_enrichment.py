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
    CurrentIncumbent,
    ExecChange,
    LeadershipEnrichmentMetadata,
)
from rrxray.services.pdl_client import PDLClient, PDLEnrichment, PDLError

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
        # Soft cap: allow the op if spend has not yet reached the cap.
        # An op that pushes over the cap is allowed once; subsequent ops are blocked.
        if self._spend >= self.cost_cap_dollars:
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
        enrichment_cache: dict[str, PDLEnrichment | None] = {}

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
        # Use enumerate so we have the actual loop index for "remaining" slicing.
        # ExecChange is a pydantic BaseModel with field-equality `__eq__`, so
        # list.index() returns the FIRST match — wrong when duplicates exist.
        for idx, change in enumerate(exec_changes):
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
                    # Append remaining changes unmutated using the actual
                    # loop index (not list.index, which would return the
                    # first duplicate's position).
                    enriched.extend(exec_changes[idx + 1:])
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
