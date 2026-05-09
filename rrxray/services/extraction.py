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


class ExtractedLinkedInIncumbent(BaseModel):
    name: str
    role_canonical: RoleCanonical
    role_raw: str
    is_relevant: bool


_EXEC_CHANGE_SYSTEM_PROMPT = """You extract structured exec-change records from press release titles and snippets.

Given a title and snippet, identify whether it announces an executive hire, departure, or promotion. If yes, extract the person's name, the role they're moving into (or out of), and the action.

Set is_relevant=True ONLY if both name and role are clearly stated. Set is_relevant=False if the title is not actually announcing an exec change (e.g., quarterly earnings, product launches, partnerships).

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
"""


_LINKEDIN_INCUMBENT_SYSTEM_PROMPT = """You extract a person's name and current role from a LinkedIn search result.

Given a search result title, snippet, and the role we were searching for, identify whether this result names a current incumbent in that role at the company.

Set is_relevant=True ONLY if both name and role are clearly stated AND the role appears to be current (not a past role or unrelated context).

Map role_canonical to: ceo, cro, vp_sales, vp_revenue, cmo, vp_marketing, founder. role_raw should preserve the wording from the result.
"""


class HaikuExtractor:
    def __init__(self, anthropic: AnthropicClient):
        self.anthropic = anthropic

    async def extract_exec_change(self, title: str, snippet: str) -> ExtractedExecChange | None:
        from rrxray.services.anthropic_client import AnthropicError
        try:
            response = await self.anthropic.complete_with_cached_system(
                system_prompt=_EXEC_CHANGE_SYSTEM_PROMPT,
                user_message=f"Title: {title}\n\nSnippet: {snippet}",
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
    ) -> ExtractedLinkedInIncumbent | None:
        from rrxray.services.anthropic_client import AnthropicError
        try:
            response = await self.anthropic.complete_with_cached_system(
                system_prompt=_LINKEDIN_INCUMBENT_SYSTEM_PROMPT,
                user_message=f"Role we were searching for: {role_query}\n\nTitle: {title}\n\nSnippet: {snippet}",
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

    async def extract_exec_change(self, title: str, snippet: str) -> ExtractedExecChange | None:
        from rrxray.services.gemini_client import GeminiError
        try:
            response = await self.gemini.complete_structured(
                system_prompt=_EXEC_CHANGE_SYSTEM_PROMPT,
                user_message=f"Title: {title}\n\nSnippet: {snippet}",
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
    ) -> ExtractedLinkedInIncumbent | None:
        from rrxray.services.gemini_client import GeminiError
        try:
            response = await self.gemini.complete_structured(
                system_prompt=_LINKEDIN_INCUMBENT_SYSTEM_PROMPT,
                user_message=f"Role we were searching for: {role_query}\n\nTitle: {title}\n\nSnippet: {snippet}",
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
