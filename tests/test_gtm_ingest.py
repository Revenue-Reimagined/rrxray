"""Tests for the gtm_ingest service."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import httpx
import pytest

from rrxray.config import Config
from rrxray.schemas._shared import Finding, SourceCitation
from rrxray.schemas.data import (
    CollectorOutputs,
    InputParams,
    ObservedGtmMotionNarrative,
    RunMetadata,
    SynthesizerOutputs,
    XrayData,
)
from rrxray.schemas.pricing_packaging import PricingPackagingData
from rrxray.services.gtm_ingest import build_ingestion_payload, post_ingestion_payload


def test_build_ingestion_payload_correctly(tmp_path):
    # Setup directories
    out_dir = tmp_path / "out"
    evidence_dir = out_dir / "evidence"
    evidence_dir.mkdir(parents=True)

    # Write a dummy evidence file
    evidence_subdir = evidence_dir / "pricing_packaging"
    evidence_subdir.mkdir()
    evidence_file = evidence_subdir / "current.md"
    evidence_file.write_text("Swayable pricing page content structure.", encoding="utf-8")

    config = Config(
        domain="swayable.com",
        output_dir=out_dir,
        gtm_submitter_first_name="Dale",
        gtm_submitter_last_name="Zwizinski",
        gtm_submitter_email="dale@revenue-reimagined.com",
    )

    source_citation = SourceCitation(
        url="https://swayable.com/pricing",
        timestamp=datetime(2026, 5, 31, 15, 0, tzinfo=UTC),
        evidence_path="pricing_packaging/current.md",
    )

    data = XrayData(
        domain="swayable.com",
        company_name="Swayable",
        run_metadata=RunMetadata(
            timestamp=datetime(2026, 5, 31, 15, 30, tzinfo=UTC),
            tool_version="0.1.0",
            modes_built=["internal"],
            model_used="claude-3-5-sonnet-20241022",
        ),
        inputs=InputParams(domain="swayable.com"),
        collectors=CollectorOutputs(
            pricing_packaging=PricingPackagingData(
                has_public_pricing=True, is_contact_us_gated=True, current_pricing_url="https://swayable.com/pricing"
            )
        ),
        synthesizers=SynthesizerOutputs(
            observed_gtm_motion=ObservedGtmMotionNarrative(
                narrative_paragraphs=["Swayable is PLG."],
                gap_bullets=["No transparent pricing."],
                findings=[Finding(text="RCT persuasion measurement", source=source_citation)],
                gaps=["No pricing"],
                discovery_questions=["How onboarding?"],
                model_used="claude-3-5-sonnet-20241022",
                cache_hit=False,
            )
        ),
        sources=[source_citation],
    )

    markdown_content = "# Rendered report"

    payload = build_ingestion_payload(config, data, markdown_content)

    assert payload["domain"] == "swayable.com"
    assert payload["company_name"] == "Swayable"
    assert payload["metadata"]["submitted_by"]["first_name"] == "Dale"
    assert payload["metadata"]["submitted_by"]["email"] == "dale@revenue-reimagined.com"
    assert payload["metadata"]["tool_version"] == "0.1.0"

    # Check reports
    assert payload["report"]["markdown_content"] == markdown_content
    assert payload["report"]["observed_gtm_motion"]["narrative_paragraphs"] == ["Swayable is PLG."]
    assert len(payload["report"]["observed_gtm_motion"]["findings"]) == 1
    assert payload["report"]["observed_gtm_motion"]["findings"][0]["source_index"] == 0

    # Check evidence file read
    assert "evidence" in payload
    assert len(payload["evidence"]) == 1
    assert payload["evidence"][0]["url"] == "https://swayable.com/pricing"
    assert payload["evidence"][0]["content"] == "Swayable pricing page content structure."
    assert payload["evidence"][0]["type"] == "WEB_CRAWL"


def test_build_ingestion_payload_preserves_finding_source_not_in_top_level_sources(tmp_path):
    config = Config(domain="swayable.com", output_dir=tmp_path / "out")
    finding_source = SourceCitation(
        url="https://swayable.com/use-cases",
        timestamp=datetime(2026, 5, 31, 16, 0, tzinfo=UTC),
    )
    data = XrayData(
        domain="swayable.com",
        company_name="Swayable",
        run_metadata=RunMetadata(
            timestamp=datetime(2026, 5, 31, 15, 30, tzinfo=UTC),
            tool_version="0.1.0",
            modes_built=["internal"],
            model_used="claude-3-5-sonnet-20241022",
        ),
        inputs=InputParams(domain="swayable.com"),
        collectors=CollectorOutputs(),
        synthesizers=SynthesizerOutputs(
            observed_gtm_motion=ObservedGtmMotionNarrative(
                narrative_paragraphs=["Swayable has research-backed messaging."],
                gap_bullets=[],
                findings=[Finding(text="Use-case proof exists", source=finding_source)],
                gaps=[],
                discovery_questions=[],
                model_used="claude-3-5-sonnet-20241022",
                cache_hit=False,
            )
        ),
        sources=[],
    )

    payload = build_ingestion_payload(config, data, "# Report")

    assert payload["sources"] == [
        {
            "index": 0,
            "url": "https://swayable.com/use-cases",
            "extracted_at": "2026-05-31T16:00:00+00:00",
            "content_summary": None,
        }
    ]
    assert payload["report"]["observed_gtm_motion"]["findings"][0]["source_index"] == 0


@pytest.mark.asyncio
async def test_post_ingestion_payload_disabled_does_nothing():
    config = Config(domain="swayable.com", gtm_ingest_enabled=False)
    success = await post_ingestion_payload(config, {})
    assert success is False


@pytest.mark.asyncio
async def test_post_ingestion_payload_unconfigured_url_logs_error():
    config = Config(domain="swayable.com", gtm_ingest_enabled=True, gtm_ingest_url=None)
    success = await post_ingestion_payload(config, {})
    assert success is False

    config_strict = Config(domain="swayable.com", gtm_ingest_enabled=True, gtm_ingest_url=None, gtm_ingest_strict=True)
    with pytest.raises(ValueError, match="GTM_INGEST_URL is not configured"):
        await post_ingestion_payload(config_strict, {})


@pytest.mark.asyncio
async def test_post_ingestion_payload_success(monkeypatch):
    config = Config(
        domain="swayable.com",
        gtm_ingest_enabled=True,
        gtm_ingest_url="https://gtmfoundations.com/api/v1/xray/ingest",
        gtm_ingest_token="secret-key",
    )

    class MockResponse:
        status_code = 201
        text = "Created"

        def json(self):
            return {"success": True}

    posted_info = {}

    async def mock_post(*args, **kwargs):
        posted_info["url"] = args[1] if len(args) > 1 else kwargs.get("url")
        posted_info["json"] = kwargs.get("json")
        posted_info["headers"] = kwargs.get("headers")
        return MockResponse()

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    success = await post_ingestion_payload(config, {"run_id": "test_run"})
    assert success is True
    assert posted_info["url"] == "https://gtmfoundations.com/api/v1/xray/ingest"
    assert posted_info["json"] == {"run_id": "test_run"}
    assert posted_info["headers"]["Authorization"] == "Bearer secret-key"
    assert posted_info["headers"]["Idempotency-Key"] == "test_run"


@pytest.mark.asyncio
async def test_post_ingestion_payload_retries_and_exponential_backoff(monkeypatch):
    config = Config(
        domain="swayable.com", gtm_ingest_enabled=True, gtm_ingest_url="https://gtmfoundations.com/api/v1/xray/ingest"
    )

    attempts = 0

    async def mock_post_fail(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        raise httpx.RequestError("Network timeout")

    # Fast forward sleep to keep tests fast
    sleep_durations = []

    async def mock_sleep(seconds):
        sleep_durations.append(seconds)

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post_fail)
    monkeypatch.setattr(asyncio, "sleep", mock_sleep)

    success = await post_ingestion_payload(config, {"run_id": "test_run"})
    assert success is False
    assert attempts == 3
    assert sleep_durations == [2, 4]


@pytest.mark.asyncio
async def test_post_ingestion_payload_strict_failure_raises(monkeypatch):
    config = Config(
        domain="swayable.com",
        gtm_ingest_enabled=True,
        gtm_ingest_url="https://gtmfoundations.com/api/v1/xray/ingest",
        gtm_ingest_strict=True,
    )

    async def mock_post_fail(*args, **kwargs):
        raise httpx.RequestError("Network timeout")

    async def mock_sleep(seconds):
        pass

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post_fail)
    monkeypatch.setattr(asyncio, "sleep", mock_sleep)

    with pytest.raises(RuntimeError, match="Failed to post X-Ray report to gtmfoundations"):
        await post_ingestion_payload(config, {"run_id": "test_run"})


@pytest.mark.asyncio
async def test_post_ingestion_payload_strict_http_failure_raises(monkeypatch):
    config = Config(
        domain="swayable.com",
        gtm_ingest_enabled=True,
        gtm_ingest_url="https://gtmfoundations.com/api/v1/xray/ingest",
        gtm_ingest_strict=True,
    )

    class MockResponse:
        status_code = 503
        text = "Database unavailable"

    async def mock_post_fail(*args, **kwargs):
        return MockResponse()

    async def mock_sleep(seconds):
        pass

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post_fail)
    monkeypatch.setattr(asyncio, "sleep", mock_sleep)

    with pytest.raises(RuntimeError, match="Status: 503"):
        await post_ingestion_payload(config, {"run_id": "test_run"})
