"""WaybackClient: snapshots() returns archived versions via Firecrawl scrapes."""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from freezegun import freeze_time

from rrxray.services.cache import DiskCache
from rrxray.services.wayback_client import WaybackClient


@pytest.fixture
def fake_firecrawl():
    fc = MagicMock()
    fc.scrape_url = AsyncMock(side_effect=lambda url, only_main_content=True: MagicMock(
        url=url,
        markdown=f"snapshot of {url}",
        html=f"<p>{url}</p>",
        metadata={"sourceURL": url},
    ))
    return fc


@pytest.fixture
def fake_httpx():
    """Returns a fake httpx.AsyncClient that responds with available snapshots."""
    client = MagicMock()
    response = MagicMock()
    response.json.return_value = {
        "archived_snapshots": {
            "closest": {
                "available": True,
                "url": "https://web.archive.org/web/20251101000000/https://example.com/pricing",
                "timestamp": "20251101000000",
            },
        },
    }
    response.raise_for_status = MagicMock()
    client.get = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    return client


@pytest.fixture
def wayback(tmp_path: Path, fake_firecrawl, fake_httpx):
    return WaybackClient(
        firecrawl=fake_firecrawl,
        cache=DiskCache(dir=tmp_path, mode="live"),
        _httpx_client_factory=lambda: fake_httpx,
    )


@freeze_time("2026-05-01T12:00:00Z")
def test_snapshots_returns_four_at_six_month_intervals(wayback, fake_httpx):
    snapshots = asyncio.run(wayback.snapshots(
        "https://example.com/pricing", interval_months=6, span_months=18,
    ))
    assert len(snapshots) == 4
    # 2026-05-01 minus 0, 6, 12, 18 months
    expected_months = [(2026, 5), (2025, 11), (2025, 5), (2024, 11)]
    actual_months = [(s.timestamp.year, s.timestamp.month) for s in snapshots]
    assert sorted(actual_months) == sorted(expected_months)


@freeze_time("2026-05-01T12:00:00Z")
def test_snapshot_fetches_html_via_firecrawl(wayback, fake_firecrawl):
    snapshots = asyncio.run(wayback.snapshots(
        "https://example.com/pricing", interval_months=6, span_months=6,
    ))
    assert len(snapshots) == 2
    assert all(s.html for s in snapshots)
    assert fake_firecrawl.scrape_url.call_count == 2


@freeze_time("2026-05-01T12:00:00Z")
def test_unavailable_snapshot_skipped(tmp_path: Path, fake_firecrawl):
    httpx_client = MagicMock()
    response = MagicMock()
    response.json.return_value = {"archived_snapshots": {}}  # nothing available
    response.raise_for_status = MagicMock()
    httpx_client.get = AsyncMock(return_value=response)
    httpx_client.__aenter__ = AsyncMock(return_value=httpx_client)
    httpx_client.__aexit__ = AsyncMock(return_value=None)

    w = WaybackClient(
        firecrawl=fake_firecrawl,
        cache=DiskCache(dir=tmp_path, mode="live"),
        _httpx_client_factory=lambda: httpx_client,
    )
    snapshots = asyncio.run(w.snapshots(
        "https://example.com/pricing", interval_months=6, span_months=6,
    ))
    assert snapshots == []


@freeze_time("2026-05-01T12:00:00Z")
def test_snapshots_cached(wayback, fake_httpx):
    asyncio.run(wayback.snapshots(
        "https://example.com/pricing", interval_months=6, span_months=6,
    ))
    asyncio.run(wayback.snapshots(
        "https://example.com/pricing", interval_months=6, span_months=6,
    ))
    # Each target timestamp = 1 availability check; total 2 (current + 6mo back)
    # Second call hits the disk cache, so no additional httpx.get calls
    assert fake_httpx.get.call_count == 2


@freeze_time("2026-05-01T12:00:00Z")
def test_snapshots_tolerates_transient_availability_error(tmp_path: Path, fake_firecrawl):
    """When availability API raises for one target, later targets still succeed."""
    httpx_client = MagicMock()
    httpx_client.__aenter__ = AsyncMock(return_value=httpx_client)
    httpx_client.__aexit__ = AsyncMock(return_value=None)

    call_count = [0]

    async def flaky_get(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 2:  # second target's availability lookup fails
            raise httpx.RequestError("simulated network error", request=MagicMock())
        response = MagicMock()
        response.json.return_value = {
            "archived_snapshots": {
                "closest": {
                    "available": True,
                    "url": f"https://web.archive.org/web/{call_count[0]}/https://example.com/pricing",
                    "timestamp": f"2026010{call_count[0]}000000",
                },
            },
        }
        response.raise_for_status = MagicMock()
        return response

    httpx_client.get = AsyncMock(side_effect=flaky_get)

    w = WaybackClient(
        firecrawl=fake_firecrawl,
        cache=DiskCache(dir=tmp_path, mode="live"),
        _httpx_client_factory=lambda: httpx_client,
    )
    snapshots = asyncio.run(w.snapshots(
        "https://example.com/pricing", interval_months=6, span_months=18,
    ))
    # Transient failure on 1 of 4 targets; we should still get 3 snapshots
    assert len(snapshots) == 3


@freeze_time("2026-05-01T12:00:00Z")
def test_503_retries_then_succeeds(tmp_path: Path, fake_firecrawl, monkeypatch):
    """Wayback 503 should be retried up to 2 additional times before failing."""
    # Patch asyncio.sleep to avoid real delays in tests
    monkeypatch.setattr("rrxray.services.wayback_client.asyncio.sleep", AsyncMock())

    httpx_client = MagicMock()
    call_count = 0

    async def get_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        response = MagicMock()
        if call_count < 3:
            # First two calls 503
            error_response = MagicMock(status_code=503)
            response.raise_for_status = MagicMock(
                side_effect=httpx.HTTPStatusError(
                    "503 Service Unavailable", request=MagicMock(), response=error_response,
                )
            )
        else:
            response.json.return_value = {
                "archived_snapshots": {
                    "closest": {
                        "available": True,
                        "url": "https://web.archive.org/web/20260501/https://example.com/pricing",
                        "timestamp": "20260501000000",
                    },
                },
            }
            response.raise_for_status = MagicMock()
        return response

    httpx_client.get = AsyncMock(side_effect=get_side_effect)
    httpx_client.__aenter__ = AsyncMock(return_value=httpx_client)
    httpx_client.__aexit__ = AsyncMock(return_value=None)

    w = WaybackClient(
        firecrawl=fake_firecrawl,
        cache=DiskCache(dir=tmp_path, mode="live"),
        _httpx_client_factory=lambda: httpx_client,
    )
    snapshots = asyncio.run(w.snapshots(
        "https://example.com/pricing", interval_months=18, span_months=18,
    ))
    # 2 targets (now + 18mo back); first target needs 3 attempts (call_count hits 3 on target 1),
    # second target succeeds on attempt 1
    assert call_count >= 3
    assert len(snapshots) >= 1


@freeze_time("2026-05-01T12:00:00Z")
def test_snapshots_tolerates_firecrawl_scrape_failure(tmp_path: Path, fake_httpx):
    """When Firecrawl raises for one snapshot, later targets still succeed."""
    from rrxray.services.firecrawl_client import FirecrawlError

    fc = MagicMock()
    call_count = [0]

    async def flaky_scrape(url, only_main_content=True):
        call_count[0] += 1
        if call_count[0] == 2:
            raise FirecrawlError(f"simulated scrape failure for {url}")
        return MagicMock(
            url=url, markdown=f"snapshot of {url}", html=f"<p>{url}</p>",
            metadata={"sourceURL": url},
        )

    fc.scrape_url = AsyncMock(side_effect=flaky_scrape)

    w = WaybackClient(
        firecrawl=fc,
        cache=DiskCache(dir=tmp_path, mode="live"),
        _httpx_client_factory=lambda: fake_httpx,
    )
    snapshots = asyncio.run(w.snapshots(
        "https://example.com/pricing", interval_months=6, span_months=18,
    ))
    # Transient failure on 1 of 4 scrapes; we should still get 3 snapshots
    assert len(snapshots) == 3
