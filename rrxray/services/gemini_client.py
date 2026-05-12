"""GeminiClient: thin async wrapper around google-genai for structured output.

Sibling to AnthropicClient. No provider abstraction layer (deferred to Phase 3
per roadmap.md line 87). Used by extraction.GeminiFlashExtractor for press
release / LinkedIn snippet parsing.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

log = logging.getLogger("rrxray.gemini")


class GeminiError(Exception):
    pass


class ParsedResponse(BaseModel):
    parsed: BaseModel
    model_used: str
    cache_hit: bool = False


class GeminiClient:
    def __init__(
        self,
        api_key: str,
        _client_factory: Callable[[], Any] | None = None,
    ):
        """`_client_factory` is a test seam — production defaults to google-genai SDK Client."""
        self.api_key = api_key
        if _client_factory is not None:
            self._sdk = _client_factory()
        else:
            from google import genai
            self._sdk = genai.Client(api_key=api_key)

    async def complete_structured(
        self,
        system_prompt: str,
        user_message: str,
        response_schema: type[BaseModel],
        model: str = "gemini-2.0-flash",
    ) -> ParsedResponse:
        """Structured-output completion. Wraps google-genai's generate_content.

        Returns a ParsedResponse with parsed pydantic model. Raises GeminiError
        on SDK failure (the SDK's own retry behavior runs first; we surface
        terminal errors).
        """
        # Concatenate system + user; google-genai uses role-based contents.
        contents = f"{system_prompt}\n\n{user_message}"
        config = {
            "response_mime_type": "application/json",
            "response_schema": response_schema,
        }

        try:
            response = await self._sdk.aio.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.warning("Gemini generate_content failed: %s", e)
            raise GeminiError(f"generate_content failed: {e}") from e

        # google-genai may return .parsed (preferred) or only .text (JSON string).
        parsed = getattr(response, "parsed", None)
        if parsed is None:
            text = getattr(response, "text", "")
            try:
                parsed = response_schema.model_validate(json.loads(text))
            except Exception as e:
                raise GeminiError(f"Failed to parse Gemini response as {response_schema.__name__}: {e}") from e

        return ParsedResponse(
            parsed=parsed,
            model_used=model,
            cache_hit=False,
        )
