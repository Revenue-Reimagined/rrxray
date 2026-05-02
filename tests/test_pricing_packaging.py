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


def test_extract_tiers_from_typical_pricing_page():
    md = """
# Pricing

## Starter
$0 per month — for individuals

## Pro
$50 per seat per month

## Enterprise
Contact us for pricing
"""
    tiers = pricing_packaging._extract_tiers(md)
    assert len(tiers) == 3
    names = [t.name for t in tiers]
    assert "Starter" in names
    assert "Pro" in names
    assert "Enterprise" in names
    pro = next(t for t in tiers if t.name == "Pro")
    assert "$50" in pro.price
    assert "month" in pro.cadence.lower() or "seat" in pro.cadence.lower()


def test_extract_tiers_returns_empty_when_no_dollar_amounts():
    md = "Welcome to our pricing! Contact sales for details."
    tiers = pricing_packaging._extract_tiers(md)
    assert tiers == []


def test_detect_contact_us_returns_true_when_gated():
    md = "Contact sales for a custom quote. Request demo."
    assert pricing_packaging._detect_contact_us(md) is True


def test_detect_contact_us_returns_false_when_prices_visible():
    md = "## Pro\n\n$50/month\n\n## Enterprise\n\n$500/month"
    assert pricing_packaging._detect_contact_us(md) is False


def test_collect_extracts_tiers_from_real_markdown(tmp_path):
    md = """
# Pricing

## Starter — Free
$0/month

## Pro
$50 per user per month

## Enterprise
Contact us
"""
    ctx = make_ctx(tmp_path, scrape_responses={
        "https://example.com/pricing": {
            "markdown": md,
            "html": "",
            "metadata": {"sourceURL": "https://example.com/pricing"},
        },
    })
    result = asyncio.run(pricing_packaging.collect(ctx))
    assert len(result.current_tiers) >= 2
    tier_names = [t.name for t in result.current_tiers]
    assert "Pro" in tier_names


# ---------------------------------------------------------------------------
# Task 12: Snapshot diff logic
# ---------------------------------------------------------------------------
from datetime import date  # noqa: E402


def test_diff_detects_price_increase():
    from rrxray.schemas.pricing_packaging import PricingTier
    older = [PricingTier(name="Pro", price="$40", cadence="month", notes="")]
    current = [PricingTier(name="Pro", price="$50", cadence="month", notes="")]
    changes = pricing_packaging._diff_tier_lists(older, current, observed_at=date(2026, 5, 1))
    kinds = {c.kind for c in changes}
    assert "price_increased" in kinds


def test_diff_detects_tier_added():
    from rrxray.schemas.pricing_packaging import PricingTier
    older = [PricingTier(name="Pro", price="$50", cadence="month", notes="")]
    current = [
        PricingTier(name="Pro", price="$50", cadence="month", notes=""),
        PricingTier(name="Enterprise", price="$500", cadence="month", notes=""),
    ]
    changes = pricing_packaging._diff_tier_lists(older, current, observed_at=date(2026, 5, 1))
    assert any(c.kind == "tier_added" and c.after == "Enterprise" for c in changes)


def test_diff_detects_tier_removed():
    from rrxray.schemas.pricing_packaging import PricingTier
    older = [
        PricingTier(name="Pro", price="$50", cadence="month", notes=""),
        PricingTier(name="Old Plan", price="$10", cadence="month", notes=""),
    ]
    current = [PricingTier(name="Pro", price="$50", cadence="month", notes="")]
    changes = pricing_packaging._diff_tier_lists(older, current, observed_at=date(2026, 5, 1))
    assert any(c.kind == "tier_removed" and c.before == "Old Plan" for c in changes)


def test_diff_detects_price_decrease():
    from rrxray.schemas.pricing_packaging import PricingTier
    older = [PricingTier(name="Pro", price="$50", cadence="month", notes="")]
    current = [PricingTier(name="Pro", price="$40", cadence="month", notes="")]
    changes = pricing_packaging._diff_tier_lists(older, current, observed_at=date(2026, 5, 1))
    kinds = {c.kind for c in changes}
    assert "price_decreased" in kinds


def test_diff_no_changes_returns_empty():
    from rrxray.schemas.pricing_packaging import PricingTier
    tiers = [PricingTier(name="Pro", price="$50", cadence="month", notes="")]
    changes = pricing_packaging._diff_tier_lists(tiers, tiers, observed_at=date(2026, 5, 1))
    assert changes == []
