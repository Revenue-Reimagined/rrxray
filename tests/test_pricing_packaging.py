"""pricing_packaging collector tests."""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from rrxray.collectors import pricing_packaging
from rrxray.context import CollectorContext


def make_ctx(tmp_path: Path, scrape_responses: dict[str, dict] | None = None) -> CollectorContext:
    """Build a CollectorContext with mocked Firecrawl + Wayback for tests."""
    fc = MagicMock()

    async def fake_scrape(url, only_main_content=True):
        scraped = scrape_responses.get(url) if scrape_responses else None
        if scraped is None:
            from rrxray.services.firecrawl_client import FirecrawlError
            raise FirecrawlError(f"no fixture for {url}")
        return MagicMock(
            url=url,
            markdown=scraped.get("markdown", ""),
            html=scraped.get("html", ""),
            metadata=scraped.get("metadata", {}),
        )

    fc.scrape_url = AsyncMock(side_effect=fake_scrape)

    wb = MagicMock()
    wb.snapshots = AsyncMock(return_value=[])

    config = MagicMock(domain="example.com")
    return CollectorContext(
        domain="example.com",
        company_name=None,
        firecrawl=fc,
        wayback=wb,
        evidence_dir=tmp_path / "evidence",
        config=config,
    )


def test_collector_name_constant():
    assert pricing_packaging.NAME == "pricing_packaging"


def test_no_pricing_url_found_returns_unavailable_data(tmp_path):
    ctx = make_ctx(tmp_path, scrape_responses={})
    result = asyncio.run(pricing_packaging.collect(ctx))
    assert result.has_public_pricing is False
    assert result.is_contact_us_gated is True
    assert result.current_pricing_url is None


def test_pricing_url_at_slash_pricing(tmp_path):
    ctx = make_ctx(tmp_path, scrape_responses={
        "https://example.com/pricing": {
            "markdown": "# Pricing\n\n## Pro $50/mo",
            "html": "<h1>Pricing</h1>",
            "metadata": {"sourceURL": "https://example.com/pricing"},
        },
    })
    result = asyncio.run(pricing_packaging.collect(ctx))
    assert result.has_public_pricing is True
    assert result.current_pricing_url == "https://example.com/pricing"


def test_pricing_url_falls_back_to_slash_plans(tmp_path):
    ctx = make_ctx(tmp_path, scrape_responses={
        "https://example.com/plans": {
            "markdown": "# Plans\n\n## Pro $50",
            "html": "",
            "metadata": {"sourceURL": "https://example.com/plans"},
        },
    })
    result = asyncio.run(pricing_packaging.collect(ctx))
    assert result.current_pricing_url == "https://example.com/plans"
