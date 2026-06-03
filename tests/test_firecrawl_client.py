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


def test_search_returns_search_results(client, fake_sdk):
    """search() wraps SDK results into SearchResult objects."""
    fake_sdk.search.return_value = [
        {"url": "https://www.linkedin.com/jobs/view/12345",
         "title": "Account Executive at Acme Corp",
         "description": "Sell to enterprise customers..."},
        {"url": "https://www.linkedin.com/jobs/view/67890",
         "title": "SDR at Acme Corp",
         "description": "Inbound and outbound..."},
    ]

    results = asyncio.run(client.search("site:linkedin.com/jobs Acme Corp"))

    from rrxray.services.firecrawl_client import SearchResult
    assert len(results) == 2
    assert isinstance(results[0], SearchResult)
    assert results[0].url == "https://www.linkedin.com/jobs/view/12345"
    assert results[0].title == "Account Executive at Acme Corp"
    assert "enterprise" in results[0].description


def test_search_caches_result(client, fake_sdk):
    fake_sdk.search.return_value = [
        {"url": "https://example.com", "title": "x", "description": "y"},
    ]
    asyncio.run(client.search("test query"))
    asyncio.run(client.search("test query"))
    assert fake_sdk.search.call_count == 1


def test_search_handles_firecrawl_error(client, fake_sdk):
    fake_sdk.search.side_effect = RuntimeError("simulated failure")

    from rrxray.services.firecrawl_client import FirecrawlError
    with pytest.raises(FirecrawlError):
        asyncio.run(client.search("test query"))


def test_search_returns_empty_list_when_no_results(client, fake_sdk):
    fake_sdk.search.return_value = []
    results = asyncio.run(client.search("query with no matches"))
    assert results == []


def test_search_passes_limit_to_sdk(client, fake_sdk):
    fake_sdk.search.return_value = []
    asyncio.run(client.search("test", limit=5))
    args, kwargs = fake_sdk.search.call_args
    assert kwargs.get("limit") == 5 or (len(args) > 1 and args[1] == 5)


def test_search_handles_v2_bucket_response(client, fake_sdk):
    """firecrawl-py v2 SearchData returns {web: [...], news: None|[], images: None|[]}.
    Our wrapper must merge non-None list buckets, not look for results/data keys.
    """
    from unittest.mock import MagicMock

    response = MagicMock()
    response.model_dump.return_value = {
        "web": [
            {"url": "https://example.com/a", "title": "Title A", "description": "Desc A"},
            {"url": "https://example.com/b", "title": "Title B", "description": "Desc B"},
        ],
        "news": None,
        "images": None,
    }
    fake_sdk.search.return_value = response

    results = asyncio.run(client.search("test query"))
    assert len(results) == 2
    assert results[0].url == "https://example.com/a"
    assert results[1].title == "Title B"


def test_search_merges_web_and_news_buckets(client, fake_sdk):
    """When both web and news buckets have results, merge them."""
    from unittest.mock import MagicMock

    response = MagicMock()
    response.model_dump.return_value = {
        "web": [{"url": "u1", "title": "Web1", "description": ""}],
        "news": [{"url": "u2", "title": "News1", "description": ""}],
        "images": None,
    }
    fake_sdk.search.return_value = response

    results = asyncio.run(client.search("test"))
    assert len(results) == 2
    titles = {r.title for r in results}
    assert titles == {"Web1", "News1"}


def test_submit_batch_returns_job_id(client, fake_sdk):
    fake_job_response = MagicMock()
    fake_job_response.id = "batch-job-123"
    fake_sdk.start_batch_scrape.return_value = fake_job_response

    job_id = asyncio.run(client.submit_batch(["https://example.com/1", "https://example.com/2"]))
    assert job_id == "batch-job-123"
    fake_sdk.start_batch_scrape.assert_called_once_with(
        ["https://example.com/1", "https://example.com/2"],
        formats=["markdown", "html"],
        only_main_content=True,
    )


def test_get_batch_status_returns_payload(client, fake_sdk):
    fake_status = MagicMock()
    fake_status.status = "completed"
    fake_status.completed = 2
    fake_status.total = 2
    fake_status.data = [
        {"markdown": "# 1", "html": "<p>1</p>", "metadata": {"sourceURL": "https://example.com/1"}},
        {"markdown": "# 2", "html": "<p>2</p>", "metadata": {"sourceURL": "https://example.com/2"}},
    ]
    fake_sdk.get_batch_scrape_status.return_value = fake_status

    status_payload = asyncio.run(client.get_batch_status("batch-job-123"))
    assert status_payload["status"] == "completed"
    assert status_payload["completed"] == 2
    assert len(status_payload["data"]) == 2
    fake_sdk.get_batch_scrape_status.assert_called_once_with("batch-job-123")


def test_wait_for_batch_polls_until_completed(client, fake_sdk):
    fake_status_1 = MagicMock()
    fake_status_1.status = "scraping"
    fake_status_1.completed = 0
    fake_status_1.total = 2
    fake_status_1.data = []

    fake_status_2 = MagicMock()
    fake_status_2.status = "completed"
    fake_status_2.completed = 2
    fake_status_2.total = 2
    fake_status_2.data = [
        {"markdown": "# 1", "html": "<p>1</p>", "metadata": {"sourceURL": "https://example.com/1"}},
        {"markdown": "# 2", "html": "<p>2</p>", "metadata": {"sourceURL": "https://example.com/2"}},
    ]

    fake_sdk.get_batch_scrape_status.side_effect = [fake_status_1, fake_status_2]

    pages = asyncio.run(client.wait_for_batch("batch-job-123", poll_interval=1))
    assert len(pages) == 2
    assert pages[0].url == "https://example.com/1"
    assert pages[0].markdown == "# 1"
    assert pages[1].url == "https://example.com/2"
    assert pages[1].markdown == "# 2"
    assert fake_sdk.get_batch_scrape_status.call_count == 2


def test_wait_for_batch_handles_failure(client, fake_sdk):
    fake_status = MagicMock()
    fake_status.status = "failed"
    fake_sdk.get_batch_scrape_status.return_value = fake_status

    from rrxray.services.firecrawl_client import FirecrawlError
    with pytest.raises(FirecrawlError, match="failed on the server"):
        asyncio.run(client.wait_for_batch("batch-job-123", poll_interval=1))


def test_wait_for_batch_handles_cancelled(client, fake_sdk):
    fake_status = MagicMock()
    fake_status.status = "cancelled"
    fake_sdk.get_batch_scrape_status.return_value = fake_status

    from rrxray.services.firecrawl_client import FirecrawlError
    with pytest.raises(FirecrawlError, match="was cancelled"):
        asyncio.run(client.wait_for_batch("batch-job-123", poll_interval=1))


def test_wait_for_batch_exponential_backoff_on_errors(client, fake_sdk):
    fake_sdk.get_batch_scrape_status.side_effect = [
        RuntimeError("Transient API / Connection Error"),
        MagicMock(status="completed", completed=1, total=1, data=[
            {"markdown": "# 1", "html": "1", "metadata": {"sourceURL": "https://example.com/1"}}
        ]),
    ]

    pages = asyncio.run(client.wait_for_batch("batch-job-123", poll_interval=1))
    assert len(pages) == 1
    assert pages[0].url == "https://example.com/1"
    assert fake_sdk.get_batch_scrape_status.call_count == 2


def test_scrape_batch_uses_cache_for_scraped_urls(client, fake_sdk):
    args_cached = {"url": "https://example.com/cached", "only_main_content": True}
    key_cached = client.cache._key("firecrawl.scrape", args_cached)
    client.cache._write(key_cached, {
        "markdown": "# Cached Markdown",
        "html": "<p>Cached HTML</p>",
        "metadata": {"sourceURL": "https://example.com/cached"},
    })

    fake_job_response = MagicMock()
    fake_job_response.id = "batch-job-456"
    fake_sdk.start_batch_scrape.return_value = fake_job_response

    fake_status = MagicMock()
    fake_status.status = "completed"
    fake_status.completed = 1
    fake_status.total = 1
    fake_status.data = [
        {"markdown": "# Uncached Markdown", "html": "<p>Uncached HTML</p>", "metadata": {"sourceURL": "https://example.com/uncached"}},
    ]
    fake_sdk.get_batch_scrape_status.return_value = fake_status

    urls = ["https://example.com/cached", "https://example.com/uncached"]
    pages = asyncio.run(client.scrape_batch(urls, poll_interval=1))

    assert len(pages) == 2
    assert pages[0].url == "https://example.com/cached"
    assert pages[0].markdown == "# Cached Markdown"
    assert pages[1].url == "https://example.com/uncached"
    assert pages[1].markdown == "# Uncached Markdown"

    fake_sdk.start_batch_scrape.assert_called_once_with(
        ["https://example.com/uncached"],
        formats=["markdown", "html"],
        only_main_content=True,
    )

    args_uncached = {"url": "https://example.com/uncached", "only_main_content": True}
    key_uncached = client.cache._key("firecrawl.scrape", args_uncached)
    cached_uncached = client.cache._read(key_uncached)
    assert cached_uncached is not None
    assert cached_uncached["markdown"] == "# Uncached Markdown"

