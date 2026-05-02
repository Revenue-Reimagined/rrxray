"""Async wrapper around the firecrawl-py SDK with disk cache and concurrency cap."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from pydantic import BaseModel

from rrxray.services.cache import DiskCache

log = logging.getLogger("rrxray.firecrawl")


class FirecrawlError(Exception):
    pass


class ScrapedPage(BaseModel):
    url: str
    markdown: str
    html: str
    metadata: dict[str, Any] = {}


class FirecrawlClient:
    def __init__(
        self,
        api_key: str,
        cache: DiskCache,
        max_concurrent: int = 5,
        _sdk: Any | None = None,
    ):
        self.api_key = api_key
        self.cache = cache
        self._semaphore = asyncio.Semaphore(max_concurrent)
        if _sdk is not None:
            self._sdk = _sdk
        else:
            from firecrawl import FirecrawlApp

            self._sdk = FirecrawlApp(api_key=api_key)

    async def scrape_url(self, url: str, only_main_content: bool = True) -> ScrapedPage:
        args = {"url": url, "only_main_content": only_main_content}

        async def upstream() -> dict[str, Any]:
            async with self._semaphore:
                params = {"pageOptions": {"onlyMainContent": only_main_content}}
                try:
                    response = await asyncio.to_thread(
                        self._sdk.scrape_url, url, params=params,
                    )
                except Exception as e:
                    log.warning("Firecrawl scrape_url failed for %s: %s", url, e)
                    raise FirecrawlError(f"scrape_url({url}) failed: {e}") from e
            return response

        raw = await self.cache.get_or_call("firecrawl.scrape_url", args, upstream)
        return ScrapedPage(
            url=raw.get("metadata", {}).get("sourceURL", url),
            markdown=raw.get("markdown", ""),
            html=raw.get("html", ""),
            metadata=raw.get("metadata", {}),
        )
