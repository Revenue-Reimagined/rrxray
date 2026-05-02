"""WaybackClient: archived snapshots at N-month intervals over M-month span."""
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from rrxray.services.cache import DiskCache

log = logging.getLogger("rrxray.wayback")


class WaybackError(Exception):
    pass


class Snapshot(BaseModel):
    timestamp: datetime
    archive_url: str
    html: str
    markdown: str


def _months_back(start: datetime, months: int) -> datetime:
    year = start.year
    month = start.month - months
    while month <= 0:
        month += 12
        year -= 1
    return start.replace(year=year, month=month, day=1, hour=0, minute=0, second=0, microsecond=0)


class WaybackClient:
    def __init__(
        self,
        firecrawl: Any,
        cache: DiskCache,
        _httpx_client_factory: Callable[[], Any] | None = None,
    ):
        self.firecrawl = firecrawl
        self.cache = cache
        if _httpx_client_factory is None:
            import httpx
            self._httpx_client_factory: Callable[[], Any] = lambda: httpx.AsyncClient(timeout=30.0)
        else:
            self._httpx_client_factory = _httpx_client_factory

    async def snapshots(
        self,
        url: str,
        interval_months: int = 6,
        span_months: int = 18,
    ) -> list[Snapshot]:
        now = datetime.now(UTC)
        targets = [_months_back(now, k) for k in range(0, span_months + 1, interval_months)]
        results: list[Snapshot] = []
        for target in targets:
            archive_url = await self._lookup_archive_url(url, target)
            if archive_url is None:
                continue
            page = await self.firecrawl.scrape_url(archive_url, only_main_content=True)
            results.append(Snapshot(
                timestamp=target,
                archive_url=archive_url,
                html=page.html,
                markdown=page.markdown,
            ))
        return results

    async def _lookup_archive_url(self, url: str, target: datetime) -> str | None:
        ts_str = target.strftime("%Y%m%d000000")
        cache_args = {"url": url, "timestamp": ts_str}

        async def upstream() -> dict[str, Any]:
            api_url = "https://archive.org/wayback/available"
            params = {"url": url, "timestamp": ts_str}
            async with self._httpx_client_factory() as client:
                try:
                    response = await client.get(api_url, params=params)
                    response.raise_for_status()
                except Exception as e:
                    log.warning("Wayback availability check failed: %s", e)
                    raise WaybackError(f"availability lookup failed: {e}") from e
                return response.json()

        payload = await self.cache.get_or_call("wayback.available", cache_args, upstream)
        closest = payload.get("archived_snapshots", {}).get("closest")
        if not closest or not closest.get("available"):
            return None
        return closest["url"]
