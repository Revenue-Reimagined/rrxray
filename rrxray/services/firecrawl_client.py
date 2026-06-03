"""Async wrapper around the firecrawl-py SDK with disk cache and concurrency cap."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from pydantic import BaseModel

from rrxray.services.cache import DiskCache, CacheMissError

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

    async def submit_batch(
        self,
        urls: list[str],
        formats: list[str] | None = None,
        only_main_content: bool = True,
    ) -> str:
        """Submit a batch scrape job and return the job ID."""
        if formats is None:
            formats = ["markdown", "html"]

        async def upstream() -> dict[str, Any]:
            async with self._semaphore:
                try:
                    response = await asyncio.to_thread(
                        self._sdk.start_batch_scrape,
                        urls,
                        formats=formats,  # type: ignore
                        only_main_content=only_main_content,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    log.warning("Firecrawl start_batch_scrape failed: %s", e)
                    raise FirecrawlError(f"submit_batch failed: {e}") from e

            from pydantic import BaseModel

            if isinstance(response, BaseModel):
                return response.model_dump()
            if isinstance(response, dict):
                return response
            return {
                "id": getattr(response, "id", "") or "",
                "url": getattr(response, "url", "") or "",
            }

        res = await upstream()
        job_id = res.get("id")
        if not job_id:
            raise FirecrawlError("Failed to obtain job ID from batch scrape submission.")
        return job_id

    async def get_batch_status(self, job_id: str) -> dict[str, Any]:
        """Retrieve the current status of a batch scrape job."""
        async def upstream() -> dict[str, Any]:
            async with self._semaphore:
                try:
                    response = await asyncio.to_thread(
                        self._sdk.get_batch_scrape_status,
                        job_id,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    log.warning("Firecrawl get_batch_scrape_status failed for %s: %s", job_id, e)
                    raise FirecrawlError(f"get_batch_status({job_id}) failed: {e}") from e

            from pydantic import BaseModel

            if isinstance(response, BaseModel):
                return response.model_dump()
            if isinstance(response, dict):
                return response
            
            # fallback conversion
            return {
                "status": getattr(response, "status", "") or "",
                "completed": getattr(response, "completed", 0) or 0,
                "total": getattr(response, "total", 0) or 0,
                "credits_used": getattr(response, "credits_used", 0) or 0,
                "expires_at": getattr(response, "expires_at", "") or "",
                "next": getattr(response, "next", None),
                "data": [
                    d.model_dump() if hasattr(d, "model_dump") else (  # type: ignore
                        d.dict() if hasattr(d, "dict") else d  # type: ignore
                    )
                    for d in (getattr(response, "data", []) or [])
                ],
            }
        
        return await upstream()

    def _document_to_scraped_page(self, doc: Any) -> ScrapedPage:
        if hasattr(doc, "model_dump"):
            raw = doc.model_dump()
        elif hasattr(doc, "dict"):
            raw = doc.dict()
        elif isinstance(doc, dict):
            raw = doc
        else:
            raw = {
                "markdown": getattr(doc, "markdown", "") or "",
                "html": getattr(doc, "html", "") or "",
                "metadata": getattr(doc, "metadata", {}) or {},
            }
        
        meta = raw.get("metadata") or {}
        if hasattr(meta, "model_dump"):
            meta_dict = meta.model_dump()  # type: ignore
        elif hasattr(meta, "dict"):
            meta_dict = meta.dict()  # type: ignore
        elif isinstance(meta, dict):
            meta_dict = meta
        else:
            meta_dict = {}

        url = (
            meta_dict.get("source_url")
            or meta_dict.get("sourceURL")
            or meta_dict.get("url")
            or raw.get("url")
            or ""
        )
        return ScrapedPage(
            url=url,
            markdown=raw.get("markdown") or "",
            html=raw.get("html") or "",
            metadata=meta_dict,
        )

    async def wait_for_batch(
        self,
        job_id: str,
        poll_interval: int = 5,
        timeout: int = 900,
        max_consecutive_errors: int = 5,
    ) -> list[ScrapedPage]:
        """Poll the batch status endpoint until completion, handling rate limits/retries with exponential backoff."""
        start_time = asyncio.get_event_loop().time()
        consecutive_errors = 0
        current_poll_interval = poll_interval

        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout:
                raise TimeoutError(f"Batch scrape job {job_id} did not complete within {timeout} seconds.")

            try:
                status_job = await self.get_batch_status(job_id)
                consecutive_errors = 0
                current_poll_interval = poll_interval
            except Exception as e:
                consecutive_errors += 1
                if consecutive_errors > max_consecutive_errors:
                    log.error("Exceeded maximum consecutive errors polling batch job %s", job_id)
                    raise FirecrawlError(f"Polling batch {job_id} failed: {e}") from e
                
                backoff_delay = min(current_poll_interval * (2 ** (consecutive_errors - 1)), 60)
                log.warning("Polling error (attempt %d/%d) for job %s, retrying in %.1f seconds: %s",
                            consecutive_errors, max_consecutive_errors, job_id, backoff_delay, e)
                await asyncio.sleep(backoff_delay)
                continue

            status = status_job.get("status")
            if status == "completed":
                pages = []
                for doc in status_job.get("data") or []:
                    pages.append(self._document_to_scraped_page(doc))
                return pages
            elif status == "failed":
                raise FirecrawlError(f"Batch scrape job {job_id} failed on the server.")
            elif status == "cancelled":
                raise FirecrawlError(f"Batch scrape job {job_id} was cancelled.")

            await asyncio.sleep(current_poll_interval)

    async def scrape_batch(
        self,
        urls: list[str],
        formats: list[str] | None = None,
        only_main_content: bool = True,
        poll_interval: int = 5,
        timeout: int = 900,
    ) -> list[ScrapedPage]:
        """Submit a batch of URLs, polling until complete, with transparent per-URL caching.
        
        Optimized to only submit URLs to Firecrawl that are not already present in DiskCache
        (unless mode is 'refresh'). Batch results are saved individually to the cache.
        """
        if formats is None:
            formats = ["markdown", "html"]

        results: list[ScrapedPage | None] = [None] * len(urls)
        urls_to_scrape_indices: list[int] = []
        urls_to_scrape: list[str] = []

        for idx, url in enumerate(urls):
            args = {"url": url, "only_main_content": only_main_content}
            key = self.cache._key("firecrawl.scrape", args)
            
            cached_raw = None
            if self.cache.mode != "refresh":
                cached_raw = self.cache._read(key)

            if cached_raw is not None:
                meta = cached_raw.get("metadata") or {}
                results[idx] = ScrapedPage(
                    url=meta.get("source_url") or meta.get("sourceURL") or meta.get("url") or url,
                    markdown=cached_raw.get("markdown") or "",
                    html=cached_raw.get("html") or "",
                    metadata=meta,
                )
            else:
                if self.cache.mode == "replay-only":
                    raise CacheMissError(
                        f"No cached entry for method='firecrawl.scrape' args={args} (key={key}). "
                        "Bootstrap by running with mode='live' or 'refresh'."
                    )
                urls_to_scrape_indices.append(idx)
                urls_to_scrape.append(url)

        if urls_to_scrape:
            job_id = await self.submit_batch(
                urls_to_scrape,
                formats=formats,
                only_main_content=only_main_content,
            )
            scraped_pages = await self.wait_for_batch(
                job_id,
                poll_interval=poll_interval,
                timeout=timeout,
            )

            # Map retrieved pages back to the correct indices and write to cache
            scraped_by_url: dict[str, ScrapedPage] = {}
            for page in scraped_pages:
                norm_url = page.url.strip().lower().rstrip("/")
                scraped_by_url[norm_url] = page

            unmapped_pages = list(scraped_pages)

            for idx, target_url in zip(urls_to_scrape_indices, urls_to_scrape):
                norm_target = target_url.strip().lower().rstrip("/")
                matched_page = scraped_by_url.get(norm_target)
                
                if matched_page:
                    results[idx] = matched_page
                    if matched_page in unmapped_pages:
                        unmapped_pages.remove(matched_page)
                else:
                    found = False
                    for up in unmapped_pages:
                        norm_up = up.url.strip().lower().rstrip("/")
                        if norm_up in norm_target or norm_target in norm_up:
                            results[idx] = up
                            unmapped_pages.remove(up)
                            found = True
                            break
                    if not found and unmapped_pages:
                        results[idx] = unmapped_pages.pop(0)

            # Write newly scraped pages to DiskCache
            for target_url, idx in zip(urls_to_scrape, urls_to_scrape_indices):
                page = results[idx]
                if page is not None:
                    args = {"url": target_url, "only_main_content": only_main_content}
                    key = self.cache._key("firecrawl.scrape", args)
                    raw_to_cache = {
                        "markdown": page.markdown,
                        "html": page.html,
                        "metadata": {
                            **page.metadata,
                            "source_url": page.url,
                        }
                    }
                    self.cache._write(key, raw_to_cache)

        final_results = [r for r in results if r is not None]
        return final_results
