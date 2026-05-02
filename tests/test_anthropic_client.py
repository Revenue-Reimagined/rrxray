"""AnthropicClient: async wrapper with prompt caching baked in."""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import BaseModel

from rrxray.services.anthropic_client import AnthropicClient, AnthropicResponse
from rrxray.services.cache import DiskCache


class FakeNarrative(BaseModel):
    summary: str
    bullets: list[str]


@pytest.fixture
def fake_sdk():
    """Mock anthropic SDK that returns a structured tool-use response."""
    sdk = MagicMock()
    fake_message = MagicMock()
    fake_message.content = [
        MagicMock(
            type="tool_use",
            name="FakeNarrative",
            input={"summary": "hello", "bullets": ["a", "b"]},
        ),
    ]
    fake_message.usage = MagicMock(
        cache_creation_input_tokens=4000,
        cache_read_input_tokens=0,
        input_tokens=500,
        output_tokens=100,
    )
    sdk.messages.create = AsyncMock(return_value=fake_message)
    return sdk


@pytest.fixture
def client(tmp_path: Path, fake_sdk):
    return AnthropicClient(
        api_key="test-key",
        cache=DiskCache(dir=tmp_path, mode="live"),
        _sdk=fake_sdk,
    )


def test_complete_with_cached_system_returns_parsed_response(client, fake_sdk):
    resp = asyncio.run(client.complete_with_cached_system(
        system_prompt="You are a tester.",
        user_message="Run.",
        model="claude-sonnet-4-6",
        response_schema=FakeNarrative,
    ))
    assert isinstance(resp, AnthropicResponse)
    assert resp.parsed.summary == "hello"
    assert resp.parsed.bullets == ["a", "b"]


def test_cache_control_set_on_system_prompt(client, fake_sdk):
    asyncio.run(client.complete_with_cached_system(
        system_prompt="A static prompt.", user_message="x",
        model="claude-sonnet-4-6", response_schema=FakeNarrative,
    ))
    _args, kwargs = fake_sdk.messages.create.call_args
    system = kwargs["system"]
    # system should be a list of dicts with cache_control
    assert isinstance(system, list)
    assert system[0]["type"] == "text"
    assert system[0]["cache_control"] == {"type": "ephemeral"}


def test_cache_hit_telemetry_in_response(client, fake_sdk):
    fake_sdk.messages.create.return_value.usage.cache_read_input_tokens = 3000
    fake_sdk.messages.create.return_value.usage.cache_creation_input_tokens = 0
    resp = asyncio.run(client.complete_with_cached_system(
        system_prompt="x", user_message="y", model="claude-sonnet-4-6",
        response_schema=FakeNarrative,
    ))
    assert resp.cache_hit is True


def test_cache_miss_telemetry_in_response(client, fake_sdk):
    resp = asyncio.run(client.complete_with_cached_system(
        system_prompt="x", user_message="y", model="claude-sonnet-4-6",
        response_schema=FakeNarrative,
    ))
    assert resp.cache_hit is False  # cache_read_input_tokens == 0 in fixture


def test_disk_cache_keyed_by_model_and_prompts(client, fake_sdk):
    asyncio.run(client.complete_with_cached_system(
        system_prompt="A", user_message="B", model="claude-sonnet-4-6",
        response_schema=FakeNarrative,
    ))
    asyncio.run(client.complete_with_cached_system(
        system_prompt="A", user_message="B", model="claude-sonnet-4-6",
        response_schema=FakeNarrative,
    ))
    # Second call hits the disk cache, so SDK.messages.create called once
    assert fake_sdk.messages.create.call_count == 1


def test_different_user_message_different_cache_key(client, fake_sdk):
    asyncio.run(client.complete_with_cached_system(
        system_prompt="A", user_message="B1", model="claude-sonnet-4-6",
        response_schema=FakeNarrative,
    ))
    asyncio.run(client.complete_with_cached_system(
        system_prompt="A", user_message="B2", model="claude-sonnet-4-6",
        response_schema=FakeNarrative,
    ))
    assert fake_sdk.messages.create.call_count == 2
