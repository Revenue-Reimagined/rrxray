"""FirecrawlClient: async wrapper around firecrawl-py SDK with cache + concurrency cap."""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from rrxray.services.cache import DiskCache
from rrxray.services.firecrawl_client import FirecrawlClient, ScrapedPage


@pytest.fixture
def fake_sdk():
    sdk = MagicMock()
    fake_response = {
        "markdown": "# Pricing\n- Pro $50/mo",
        "html": "<h1>Pricing</h1>",
        "metadata": {"sourceURL": "https://example.com/pricing"},
    }
    sdk.scrape.return_value = fake_response  # v2
    sdk.scrape_url.return_value = fake_response  # keep for v1 fallback
    return sdk


@pytest.fixture
def client(tmp_path: Path, fake_sdk):
    return FirecrawlClient(
        api_key="test-key",
        cache=DiskCache(dir=tmp_path, mode="live"),
        _sdk=fake_sdk,
    )


def test_scrape_url_returns_scraped_page(client, fake_sdk):
    page = asyncio.run(client.scrape_url("https://example.com/pricing"))
    assert isinstance(page, ScrapedPage)
    assert page.url == "https://example.com/pricing"
    assert page.markdown.startswith("# Pricing")
    assert page.html == "<h1>Pricing</h1>"


def test_scrape_url_caches_result(client, fake_sdk):
    asyncio.run(client.scrape_url("https://example.com/pricing"))
    asyncio.run(client.scrape_url("https://example.com/pricing"))
    assert fake_sdk.scrape.call_count == 1


def test_scrape_url_only_main_content_default(client, fake_sdk):
    asyncio.run(client.scrape_url("https://example.com/pricing"))
    method = fake_sdk.scrape if fake_sdk.scrape.called else fake_sdk.scrape_url
    _args, kwargs = method.call_args
    assert kwargs.get("only_main_content") is True
    assert "markdown" in kwargs.get("formats", [])
    assert "html" in kwargs.get("formats", [])


def test_scrape_url_passes_only_main_content_false(client, fake_sdk):
    asyncio.run(client.scrape_url("https://example.com/pricing", only_main_content=False))
    method = fake_sdk.scrape if fake_sdk.scrape.called else fake_sdk.scrape_url
    _args, kwargs = method.call_args
    assert kwargs.get("only_main_content") is False


def test_concurrency_cap_via_semaphore(tmp_path: Path):
    # Verify the client has a semaphore bound; we cannot easily assert wait behavior
    # without flaky timing tests. Just confirm the attribute exists.
    sdk = MagicMock()
    sdk.scrape.return_value = {"markdown": "", "html": "", "metadata": {"sourceURL": "x"}}
    c = FirecrawlClient(
        api_key="k", cache=DiskCache(dir=tmp_path, mode="live"), _sdk=sdk, max_concurrent=3,
    )
    assert c._semaphore._value == 3
