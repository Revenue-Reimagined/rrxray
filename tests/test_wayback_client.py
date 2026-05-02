"""WaybackClient: snapshots() returns archived versions via Firecrawl scrapes."""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

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
