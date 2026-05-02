"""Async Anthropic client with prompt caching baked in."""
from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel

from rrxray.services.cache import DiskCache

log = logging.getLogger("rrxray.anthropic")


class AnthropicError(Exception):
    pass


class AnthropicResponse[T](BaseModel):
    parsed: T
    cache_hit: bool
    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int
    cache_read_input_tokens: int
    model_used: str


def _schema_to_tool(schema: type[BaseModel]) -> dict[str, Any]:
    """Convert a Pydantic model to an Anthropic tool definition."""
    json_schema = schema.model_json_schema()
    return {
        "name": schema.__name__,
        "description": schema.__doc__ or f"Structured response matching {schema.__name__}",
        "input_schema": json_schema,
    }


class AnthropicClient:
    def __init__(
        self,
        api_key: str,
        cache: DiskCache,
        _sdk: Any | None = None,
    ):
        self.api_key = api_key
        self.cache = cache
        if _sdk is not None:
            self._sdk = _sdk
        else:
            from anthropic import AsyncAnthropic

            self._sdk = AsyncAnthropic(api_key=api_key)

    async def complete_with_cached_system(
        self,
        system_prompt: str,
        user_message: str,
        model: str,
        response_schema: type[BaseModel],
        max_tokens: int = 4096,
    ) -> AnthropicResponse:
        cache_args = {
            "model": model,
            "system_prompt_hash": system_prompt,
            "user_message": user_message,
            "schema": response_schema.__name__,
        }

        async def upstream() -> dict[str, Any]:
            tool = _schema_to_tool(response_schema)
            try:
                response = await self._sdk.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    system=[
                        {
                            "type": "text",
                            "text": system_prompt,
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                    messages=[{"role": "user", "content": user_message}],
                    tools=[tool],
                    tool_choice={"type": "tool", "name": response_schema.__name__},
                )
            except Exception as e:
                log.warning("Anthropic messages.create failed: %s", e)
                raise AnthropicError(f"messages.create failed: {e}") from e

            # Extract the tool_use block
            tool_use = next((b for b in response.content if b.type == "tool_use"), None)
            if tool_use is None:
                raise AnthropicError("No tool_use block in response")

            usage = response.usage
            cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
            cache_create = getattr(usage, "cache_creation_input_tokens", 0) or 0
            log.info(
                "anthropic call: model=%s input_tokens=%d output_tokens=%d "
                "cache_creation=%d cache_read=%d",
                model,
                usage.input_tokens,
                usage.output_tokens,
                cache_create,
                cache_read,
            )

            return {
                "tool_input": tool_use.input,
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "cache_creation_input_tokens": cache_create,
                "cache_read_input_tokens": cache_read,
            }

        raw = await self.cache.get_or_call("anthropic.complete", cache_args, upstream)
        parsed = response_schema.model_validate(raw["tool_input"])
        return AnthropicResponse(
            parsed=parsed,
            cache_hit=raw["cache_read_input_tokens"] > 0,
            input_tokens=raw["input_tokens"],
            output_tokens=raw["output_tokens"],
            cache_creation_input_tokens=raw["cache_creation_input_tokens"],
            cache_read_input_tokens=raw["cache_read_input_tokens"],
            model_used=model,
        )
