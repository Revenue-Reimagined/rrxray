"""Extractor tests: HaikuExtractor + GeminiFlashExtractor + make_extractor factory."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import BaseModel

from rrxray.services.extraction import (
    ExecAction,
    ExtractedExecChange,
    ExtractedLinkedInIncumbent,
    GeminiFlashExtractor,
    HaikuExtractor,
    make_extractor,
)


class _FakeAnthropicResponse(BaseModel):
    parsed: ExtractedExecChange | ExtractedLinkedInIncumbent
    model_used: str = "claude-haiku-4-5-20251001"
    cache_hit: bool = False


@pytest.fixture
def fake_anthropic():
    a = MagicMock()
    a.complete_with_cached_system = AsyncMock()
    return a


@pytest.fixture
def fake_gemini():
    g = MagicMock()
    g.complete_structured = AsyncMock()
    return g


def test_haiku_extractor_extracts_hire_announcement(fake_anthropic):
    fake_anthropic.complete_with_cached_system.return_value = _FakeAnthropicResponse(
        parsed=ExtractedExecChange(
            name="Jane Doe",
            role_canonical="cro",
            role_raw="Chief Revenue Officer",
            action=ExecAction.HIRE,
            is_relevant=True,
        ),
    )

    extractor = HaikuExtractor(fake_anthropic)
    result = asyncio.run(extractor.extract_exec_change(
        title="Acme Names Jane Doe as Chief Revenue Officer",
        snippet="Acme Corp today announced the appointment of Jane Doe as CRO.",
        target_company="Acme",
        target_domain="acme.com",
    ))

    assert result is not None
    assert result.name == "Jane Doe"
    assert result.role_canonical == "cro"
    assert result.action == ExecAction.HIRE
    assert result.is_relevant is True


def test_haiku_extractor_returns_none_on_irrelevant(fake_anthropic):
    fake_anthropic.complete_with_cached_system.return_value = _FakeAnthropicResponse(
        parsed=ExtractedExecChange(
            name="",
            role_canonical="cro",
            role_raw="",
            action=ExecAction.HIRE,
            is_relevant=False,
        ),
    )

    extractor = HaikuExtractor(fake_anthropic)
    result = asyncio.run(extractor.extract_exec_change(
        title="Acme Q3 Earnings Call",
        snippet="Quarterly results discussed.",
        target_company="Acme",
        target_domain="acme.com",
    ))
    assert result is None


def test_haiku_extractor_returns_none_on_anthropic_error(fake_anthropic):
    from rrxray.services.anthropic_client import AnthropicError
    fake_anthropic.complete_with_cached_system.side_effect = AnthropicError("simulated")

    extractor = HaikuExtractor(fake_anthropic)
    result = asyncio.run(extractor.extract_exec_change(
        "title", "snippet", target_company="Acme", target_domain="acme.com",
    ))
    assert result is None


def test_haiku_extractor_filters_other_company_announcements(fake_anthropic):
    """Extractor returns None when the announcement is about a different company.

    Mocks Haiku to return is_relevant=False for an Adobe-CEO announcement
    when the target was Acme; the wrapper should drop it.
    """
    fake_anthropic.complete_with_cached_system.return_value = _FakeAnthropicResponse(
        parsed=ExtractedExecChange(
            name="",
            role_canonical="ceo",
            role_raw="",
            action=ExecAction.HIRE,
            is_relevant=False,
        ),
    )

    extractor = HaikuExtractor(fake_anthropic)
    result = asyncio.run(extractor.extract_exec_change(
        title="Adobe Names Shantanu Narayen as Chairman",
        snippet="Adobe Inc. today announced... (mentions Acme as a partner).",
        target_company="Acme",
        target_domain="acme.com",
    ))
    assert result is None


def test_haiku_extractor_keeps_target_company_announcement(fake_anthropic):
    """Extractor returns the result when is_relevant=True for a target match."""
    fake_anthropic.complete_with_cached_system.return_value = _FakeAnthropicResponse(
        parsed=ExtractedExecChange(
            name="Jane Doe",
            role_canonical="cro",
            role_raw="Chief Revenue Officer",
            action=ExecAction.HIRE,
            is_relevant=True,
        ),
    )

    extractor = HaikuExtractor(fake_anthropic)
    result = asyncio.run(extractor.extract_exec_change(
        title="Acme Names Jane Doe as Chief Revenue Officer",
        snippet="Acme Corp announced the appointment of Jane Doe as CRO.",
        target_company="Acme",
        target_domain="acme.com",
    ))
    assert result is not None
    assert result.name == "Jane Doe"
    assert result.is_relevant is True


def test_haiku_extractor_extracts_occurred_at_date(fake_anthropic):
    """Iteration #3: extractor parses an ISO date when the body contains a clear effective date."""
    fake_anthropic.complete_with_cached_system.return_value = _FakeAnthropicResponse(
        parsed=ExtractedExecChange(
            name="Jane Doe", role_canonical="cro", role_raw="CRO",
            action=ExecAction.HIRE, is_relevant=True, occurred_at="2026-03-01",
        ),
    )
    extractor = HaikuExtractor(fake_anthropic)
    result = asyncio.run(extractor.extract_exec_change(
        title="Acme Names Jane Doe as CRO",
        snippet="...",
        target_company="Acme",
        target_domain="acme.com",
        body="Acme today announced the appointment of Jane Doe as Chief Revenue Officer, effective March 1, 2026.",
    ))
    assert result is not None
    assert result.occurred_at == "2026-03-01"


def test_haiku_extractor_extract_linkedin_role(fake_anthropic):
    fake_anthropic.complete_with_cached_system.return_value = _FakeAnthropicResponse(
        parsed=ExtractedLinkedInIncumbent(
            name="Bob Smith",
            role_canonical="cmo",
            role_raw="Chief Marketing Officer",
            is_relevant=True,
        ),
    )

    extractor = HaikuExtractor(fake_anthropic)
    result = asyncio.run(extractor.extract_linkedin_role(
        title="Bob Smith - Chief Marketing Officer at Acme - LinkedIn",
        snippet="Bob Smith. Chief Marketing Officer at Acme Corp. New York, NY.",
        role_query="cmo",
        target_company="Acme",
        target_domain="acme.com",
    ))

    assert result is not None
    assert result.name == "Bob Smith"
    assert result.role_canonical == "cmo"


class _FakeGeminiResponse(BaseModel):
    parsed: ExtractedExecChange | ExtractedLinkedInIncumbent
    model_used: str = "gemini-2.0-flash"
    cache_hit: bool = False


def test_gemini_flash_extractor_extracts_hire_announcement(fake_gemini):
    fake_gemini.complete_structured.return_value = _FakeGeminiResponse(
        parsed=ExtractedExecChange(
            name="Jane Doe",
            role_canonical="cro",
            role_raw="Chief Revenue Officer",
            action=ExecAction.HIRE,
            is_relevant=True,
        ),
    )

    extractor = GeminiFlashExtractor(fake_gemini)
    result = asyncio.run(extractor.extract_exec_change(
        title="Acme Names Jane Doe as Chief Revenue Officer",
        snippet="...",
        target_company="Acme",
        target_domain="acme.com",
    ))
    assert result is not None
    assert result.name == "Jane Doe"


def test_gemini_flash_extractor_returns_none_on_irrelevant(fake_gemini):
    fake_gemini.complete_structured.return_value = _FakeGeminiResponse(
        parsed=ExtractedExecChange(
            name="",
            role_canonical="cro",
            role_raw="",
            action=ExecAction.HIRE,
            is_relevant=False,
        ),
    )

    extractor = GeminiFlashExtractor(fake_gemini)
    result = asyncio.run(extractor.extract_exec_change(
        "x", "y", target_company="Acme", target_domain="acme.com",
    ))
    assert result is None


def test_gemini_flash_extractor_returns_none_on_gemini_error(fake_gemini):
    from rrxray.services.gemini_client import GeminiError
    fake_gemini.complete_structured.side_effect = GeminiError("simulated")

    extractor = GeminiFlashExtractor(fake_gemini)
    result = asyncio.run(extractor.extract_exec_change(
        "x", "y", target_company="Acme", target_domain="acme.com",
    ))
    assert result is None


def test_make_extractor_picks_haiku_by_default(fake_anthropic, fake_gemini):
    from rrxray.config import Config
    config = Config(domain="example.com", extractor_model="haiku")
    extractor = make_extractor(config, fake_anthropic, fake_gemini)
    assert isinstance(extractor, HaikuExtractor)


def test_make_extractor_picks_gemini_with_flag(fake_anthropic, fake_gemini):
    from rrxray.config import Config
    config = Config(domain="example.com", extractor_model="gemini-flash")
    extractor = make_extractor(config, fake_anthropic, fake_gemini)
    assert isinstance(extractor, GeminiFlashExtractor)


def test_make_extractor_raises_when_gemini_key_missing(fake_anthropic):
    from rrxray.config import Config
    from rrxray.services.extraction import ExtractorConfigError
    config = Config(domain="example.com", extractor_model="gemini-flash")
    with pytest.raises(ExtractorConfigError):
        make_extractor(config, fake_anthropic, gemini=None)
