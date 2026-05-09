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


class SearchResult(BaseModel):
    url: str
    title: str = ""
    description: str = ""
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
                try:
                    # firecrawl-py v2: Firecrawl.scrape(url, formats=..., only_main_content=...)
                    # Returns a Document object; we serialize to dict for caching.
                    response = await asyncio.to_thread(
                        self._sdk.scrape,
                        url,
                        formats=["markdown", "html"],
                        only_main_content=only_main_content,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    log.warning("Firecrawl scrape failed for %s: %s", url, e)
                    raise FirecrawlError(f"scrape({url}) failed: {e}") from e
            # Document objects from firecrawl-py v2 may need conversion
            if hasattr(response, "model_dump"):
                return response.model_dump()
            if hasattr(response, "dict"):
                return response.dict()
            if isinstance(response, dict):
                return response
            # Fallback: extract attributes
            return {
                "markdown": getattr(response, "markdown", "") or "",
                "html": getattr(response, "html", "") or "",
                "metadata": getattr(response, "metadata", {}) or {},
            }

        raw = await self.cache.get_or_call("firecrawl.scrape", args, upstream)
        meta = raw.get("metadata") or {}
        return ScrapedPage(
            url=meta.get("source_url") or meta.get("sourceURL") or meta.get("url") or url,
            markdown=raw.get("markdown") or "",
            html=raw.get("html") or "",
            metadata=meta,
        )

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        """Web search via Firecrawl SDK.

        Returns up to `limit` results. Same cache layer as scrape_url.
        """
        args = {"query": query, "limit": limit}

        async def upstream() -> list[dict[str, Any]]:
            async with self._semaphore:
                try:
                    response = await asyncio.to_thread(
                        self._sdk.search, query, limit=limit,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    log.warning("Firecrawl search failed for %r: %s", query, e)
                    raise FirecrawlError(f"search({query!r}) failed: {e}") from e

            if hasattr(response, "model_dump"):
                payload = response.model_dump()
                if isinstance(payload, dict):
                    # firecrawl-py v2 SearchData uses bucket-keyed shape:
                    # {"web": [...], "news": [...], "images": [...]}.
                    # Buckets that weren't requested are None (not empty list),
                    # so coerce defensively. Older SDK versions used
                    # {"results": [...]} or {"data": [...]}; preserve those
                    # for backwards compat.
                    merged: list[dict[str, Any]] = []
                    for key in ("web", "news", "results", "data"):
                        bucket = payload.get(key)
                        if isinstance(bucket, list):
                            merged.extend(bucket)
                    return merged
                return []
            if isinstance(response, list):
                return response
            return []

        raw = await self.cache.get_or_call("firecrawl.search", args, upstream)
        results: list[SearchResult] = []
        for r in raw or []:
            if not isinstance(r, dict):
                continue
            results.append(SearchResult(
                url=r.get("url", ""),
                title=r.get("title", ""),
                description=(
                    r.get("description")
                    or r.get("snippet")
                    or r.get("excerpt")
                    or ""
                ),
                metadata={
                    k: v for k, v in r.items()
                    if k not in {"url", "title", "description", "snippet", "excerpt"}
                },
            ))
        return results
