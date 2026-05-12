"""GeminiClient: thin async wrapper around google-genai for structured output."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import BaseModel

from rrxray.services.gemini_client import GeminiClient, GeminiError, ParsedResponse


class _DemoSchema(BaseModel):
    name: str
    age: int


@pytest.fixture
def fake_sdk():
    """A MagicMock standing in for the google-genai Client."""
    sdk = MagicMock()
    sdk.aio = MagicMock()
    sdk.aio.models = MagicMock()
    sdk.aio.models.generate_content = AsyncMock()
    return sdk


@pytest.fixture
def client(fake_sdk):
    return GeminiClient(api_key="test-key", _client_factory=lambda: fake_sdk)


def test_complete_structured_returns_parsed_response(client, fake_sdk):
    """Mocked SDK call yields a ParsedResponse with parsed pydantic model."""
    fake_sdk.aio.models.generate_content.return_value = MagicMock(
        parsed=_DemoSchema(name="Alice", age=30),
        text='{"name": "Alice", "age": 30}',
    )

    response = asyncio.run(client.complete_structured(
        system_prompt="You extract names and ages.",
        user_message="Alice is 30.",
        response_schema=_DemoSchema,
        model="gemini-2.0-flash",
    ))

    assert isinstance(response, ParsedResponse)
    assert isinstance(response.parsed, _DemoSchema)
    assert response.parsed.name == "Alice"
    assert response.parsed.age == 30
    assert response.model_used == "gemini-2.0-flash"
    assert response.cache_hit is False


def test_complete_structured_raises_on_sdk_error(client, fake_sdk):
    fake_sdk.aio.models.generate_content.side_effect = RuntimeError("simulated SDK failure")

    with pytest.raises(GeminiError):
        asyncio.run(client.complete_structured(
            system_prompt="x",
            user_message="y",
            response_schema=_DemoSchema,
        ))


def test_complete_structured_uses_injected_factory(fake_sdk):
    """Confirm the test seam works: the factory we pass is the SDK we get."""
    factory_calls = []

    def factory():
        factory_calls.append(True)
        return fake_sdk

    GeminiClient(api_key="test-key", _client_factory=factory)
    assert len(factory_calls) == 1


def test_complete_structured_returns_none_parsed_when_sdk_returns_text_only(client, fake_sdk):
    """If the SDK returns only text (no .parsed), we attempt JSON-parse fallback."""
    fake_sdk.aio.models.generate_content.return_value = MagicMock(
        parsed=None,
        text='{"name": "Bob", "age": 25}',
    )

    response = asyncio.run(client.complete_structured(
        system_prompt="x",
        user_message="y",
        response_schema=_DemoSchema,
    ))
    assert response.parsed.name == "Bob"
    assert response.parsed.age == 25
