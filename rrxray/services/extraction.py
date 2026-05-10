"""LLM-based extraction for press release titles and LinkedIn snippets.

Used by leadership_stability collector to parse unstructured natural-language
content (press releases and LinkedIn search snippets) into structured records.

Phase 2.1c rule "no LLM in collector path" is amended to "no LLM in collector
path unless the data is genuinely unstructured natural language and a
deterministic alternative would degrade quality." Press release name + role +
action extraction is exactly that case; regex coverage is too patchy to be
useful.

Two concrete extractors share a duck-typed interface (no formal Protocol;
defer that to Phase 3's services/llm.py provider abstraction). HaikuExtractor
calls Anthropic Haiku 4.5; GeminiFlashExtractor calls Gemini 2.0 Flash. Both
return None on irrelevant or extraction failure so the collector can iterate
over results without per-call try/except.
"""
from __future__ import annotations

import logging
from enum import StrEnum
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ValidationError

if TYPE_CHECKING:
    from rrxray.config import Config
    from rrxray.services.anthropic_client import AnthropicClient
    from rrxray.services.gemini_client import GeminiClient

log = logging.getLogger("rrxray.extraction")


class ExtractorConfigError(Exception):
    pass


class ExecAction(StrEnum):
    HIRE = "hire"
    DEPARTURE = "departure"
    PROMOTION = "promotion"


RoleCanonical = Literal[
    "ceo", "cro", "vp_sales", "vp_revenue",
    "cmo", "vp_marketing", "founder",
]


class ExtractedExecChange(BaseModel):
    name: str
    role_canonical: RoleCanonical
    role_raw: str
    action: ExecAction
    is_relevant: bool
    occurred_at: str | None = None  # ISO date YYYY-MM-DD if extractable, else None


class ExtractedLinkedInIncumbent(BaseModel):
    name: str
    role_canonical: RoleCanonical
    role_raw: str
    is_relevant: bool


_EXEC_CHANGE_SYSTEM_PROMPT = """You extract structured exec-change records from press release titles and snippets.

The user message will begin with "Target company: <name>" and "Target domain: <domain>". The target company is identified by both name and domain. The DOMAIN is the authoritative identifier. Many companies share generic words in their names (e.g., "Linear" could be Linear the project management tool at linear.app, OR Linear Retail, OR Linear Health Sciences, OR Linear Clinical Research, OR Linear Air — these are all different companies). If the press release is about a different organization that shares part of the target's name, set is_relevant=False.

You must verify that the announcement is unambiguously about that target company. If the title and snippet are about ANY OTHER company (e.g., a competitor's CEO change, an Apple/Tim Cook announcement, an Adobe leadership transition, an industry roundup mentioning the target only tangentially, or a same-name-different-organization match), set is_relevant=False even if the announcement otherwise looks like a clean exec change. The press release must be announcing an exec change AT the company at the target domain, not merely mentioning the target in passing.

Given a title and snippet, identify whether it announces an executive hire, departure, or promotion AT the target company. If yes, extract the person's name, the role they're moving into (or out of), and the action.

Set is_relevant=True ONLY when ALL of the following are met:
1. The announcement is unambiguously about the company at the target domain (or you can confirm it from explicit context like the company's full name matching, the press release URL pointing to the target's domain, or text in the snippet identifying the target).
2. Both the person's name and role are clearly stated.
3. The action is genuinely a hire, departure, or promotion (not a routine product announcement, conference talk, partnership, quarterly earnings, etc.).

When in doubt, set is_relevant=False. False positives produce confidently-wrong synthesizer narratives; false negatives only mean the report has less data, which is recoverable in discovery.

Map the role to one of these canonical values:
- ceo
- cro
- vp_sales
- vp_revenue
- cmo
- vp_marketing
- founder

If the role doesn't map to one of these, pick the closest match and let role_raw preserve the original wording. If no match is reasonable, set is_relevant=False.

Action must be one of: hire, departure, promotion. Promotion = internal move (e.g., "promotes X to CRO"). Hire = external (e.g., "names", "appoints", "joins"). Departure = leaving (e.g., "departs", "resigns", "steps down").

If the body or snippet contains a clear date for when the change took effect (e.g., "effective March 1, 2026", "today announced", "January 15, 2024"), populate `occurred_at` as YYYY-MM-DD. If the date is ambiguous or not stated, set `occurred_at` to None. Do NOT guess or fabricate dates.
"""


_LINKEDIN_INCUMBENT_SYSTEM_PROMPT = """You extract a person's name and current role from a LinkedIn search result.

The user message will begin with "Target company: <name>" and "Target domain: <domain>". The target company is identified by both name and domain. The DOMAIN is the authoritative identifier. Many companies share generic words in their names (e.g., "Linear" could be Linear the project management tool at linear.app, OR Linear Retail, OR Linear Health Sciences, OR Linear Clinical Research, OR Linear Air — these are all different companies). Set is_relevant=True ONLY when the LinkedIn snippet clearly indicates the person currently holds this role at the company at the target domain — not at a different company that shares part of the target's name, and not at a previous company in the person's history.

You must verify that the LinkedIn profile/snippet clearly indicates the person currently holds the role AT that target company. If the snippet shows the person is at a DIFFERENT company (a competitor, a similarly-named-but-distinct company, a former employer, or an unrelated firm that happens to surface in the search), set is_relevant=False — even if the role title matches.

Given a search result title, snippet, and the role we were searching for, identify whether this result names a current incumbent in that role at the target company.

Set is_relevant=True ONLY if ALL of the following hold:
1. The profile/snippet clearly indicates the person is currently at the company at the target domain (not a former role, not a similar-sounding different company, not a competitor).
2. Both the person's name and role are clearly stated.
3. The role appears to be current (not a past role or unrelated context).

Otherwise, set is_relevant=False. When in doubt, set is_relevant=False. False positives produce confidently-wrong synthesizer narratives; false negatives only mean the report has less data, which is recoverable in discovery.

Map role_canonical to: ceo, cro, vp_sales, vp_revenue, cmo, vp_marketing, founder. role_raw should preserve the wording from the result.
"""


class HaikuExtractor:
    def __init__(self, anthropic: AnthropicClient):
        self.anthropic = anthropic

    async def extract_exec_change(
        self, title: str, snippet: str, target_company: str, target_domain: str,
        body: str | None = None,
    ) -> ExtractedExecChange | None:
        from rrxray.services.anthropic_client import AnthropicError
        parts = [
            f"Target company: {target_company}",
            f"Target domain: {target_domain}",
            f"Title: {title}",
            f"Snippet: {snippet}",
        ]
        if body:
            parts.append(f"Full body (truncated to 4000 chars):\n{body[:4000]}")
        user_message = "\n\n".join(parts)
        try:
            response = await self.anthropic.complete_with_cached_system(
                system_prompt=_EXEC_CHANGE_SYSTEM_PROMPT,
                user_message=user_message,
                model="claude-haiku-4-5-20251001",
                response_schema=ExtractedExecChange,
            )
        except (AnthropicError, ValidationError) as e:
            log.debug("Haiku extract_exec_change failed: %s", e)
            return None
        result = response.parsed
        return result if result.is_relevant else None

    async def extract_linkedin_role(
        self, title: str, snippet: str, role_query: str,
        target_company: str, target_domain: str,
    ) -> ExtractedLinkedInIncumbent | None:
        from rrxray.services.anthropic_client import AnthropicError
        try:
            response = await self.anthropic.complete_with_cached_system(
                system_prompt=_LINKEDIN_INCUMBENT_SYSTEM_PROMPT,
                user_message=(
                    f"Target company: {target_company}\n"
                    f"Target domain: {target_domain}\n\n"
                    f"Role we were searching for: {role_query}\n\n"
                    f"Title: {title}\n\nSnippet: {snippet}"
                ),
                model="claude-haiku-4-5-20251001",
                response_schema=ExtractedLinkedInIncumbent,
            )
        except (AnthropicError, ValidationError) as e:
            log.debug("Haiku extract_linkedin_role failed: %s", e)
            return None
        result = response.parsed
        return result if result.is_relevant else None


class GeminiFlashExtractor:
    def __init__(self, gemini: GeminiClient):
        self.gemini = gemini

    async def extract_exec_change(
        self, title: str, snippet: str, target_company: str, target_domain: str,
        body: str | None = None,
    ) -> ExtractedExecChange | None:
        from rrxray.services.gemini_client import GeminiError
        parts = [
            f"Target company: {target_company}",
            f"Target domain: {target_domain}",
            f"Title: {title}",
            f"Snippet: {snippet}",
        ]
        if body:
            parts.append(f"Full body (truncated to 4000 chars):\n{body[:4000]}")
        user_message = "\n\n".join(parts)
        try:
            response = await self.gemini.complete_structured(
                system_prompt=_EXEC_CHANGE_SYSTEM_PROMPT,
                user_message=user_message,
                response_schema=ExtractedExecChange,
                model="gemini-2.0-flash",
            )
        except (GeminiError, ValidationError) as e:
            log.debug("Gemini extract_exec_change failed: %s", e)
            return None
        result = response.parsed
        return result if result.is_relevant else None

    async def extract_linkedin_role(
        self, title: str, snippet: str, role_query: str,
        target_company: str, target_domain: str,
    ) -> ExtractedLinkedInIncumbent | None:
        from rrxray.services.gemini_client import GeminiError
        try:
            response = await self.gemini.complete_structured(
                system_prompt=_LINKEDIN_INCUMBENT_SYSTEM_PROMPT,
                user_message=(
                    f"Target company: {target_company}\n"
                    f"Target domain: {target_domain}\n\n"
                    f"Role we were searching for: {role_query}\n\n"
                    f"Title: {title}\n\nSnippet: {snippet}"
                ),
                response_schema=ExtractedLinkedInIncumbent,
                model="gemini-2.0-flash",
            )
        except (GeminiError, ValidationError) as e:
            log.debug("Gemini extract_linkedin_role failed: %s", e)
            return None
        result = response.parsed
        return result if result.is_relevant else None


def make_extractor(
    config: Config,
    anthropic: AnthropicClient,
    gemini: GeminiClient | None,
) -> HaikuExtractor | GeminiFlashExtractor:
    """Factory: picks an extractor based on config.extractor_model.

    Raises ExtractorConfigError if extractor_model='gemini-flash' but gemini is None
    (i.e., GEMINI_API_KEY was not set).
    """
    if config.extractor_model == "gemini-flash":
        if gemini is None:
            raise ExtractorConfigError(
                "extractor_model='gemini-flash' but no GeminiClient available — "
                "set GEMINI_API_KEY in environment or .env."
            )
        return GeminiFlashExtractor(gemini)
    return HaikuExtractor(anthropic)
