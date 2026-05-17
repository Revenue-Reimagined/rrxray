"""Tests for the positioning_drift collector."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from rrxray.collectors.positioning_drift import (
    NAME,
    _diff_snapshots,
    _extract_fields,
)
from rrxray.schemas.positioning_drift import HomepageSnapshot

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "synthetic" / "positioning_drift"


def _load_fixture(name: str) -> str:
    return (FIXTURE_DIR / name).read_text()


# --- Module identity ---

def test_name():
    assert NAME == "positioning_drift"


# --- _extract_fields ---

def test_extract_fields_from_full_markdown():
    md = """# The fastest way to close deals

Purpose-built for B2B sales teams.

[Product](/product) [Pricing](/pricing) [Blog](/blog) [About](/about)

More content here...
"""
    hero, sub, nav = _extract_fields(md)
    assert hero == "The fastest way to close deals"
    assert "B2B" in sub
    assert "Product" in nav
    assert "Pricing" in nav


def test_extract_fields_no_h1():
    md = """Welcome to Acme

[Product](/product) [Pricing](/pricing)
"""
    hero, _sub, nav = _extract_fields(md)
    assert hero is None  # no H1 found
    assert "Product" in nav


def test_extract_fields_empty_markdown():
    hero, sub, nav = _extract_fields("")
    assert hero is None
    assert sub is None
    assert nav == []


def test_extract_fields_skips_login_nav():
    md = """# Acme Corp

[Login](/login) [Sign In](/signin) [Product](/product) [Pricing](/pricing)
"""
    _hero, _sub, nav = _extract_fields(md)
    assert "Login" not in nav
    assert "Sign In" not in nav
    assert "Product" in nav


def test_extract_fields_caps_nav_items():
    # Build a markdown with 20 short nav links
    links = " ".join(f"[Item{i}](/item{i})" for i in range(20))
    md = f"# Hero\n\nSub.\n\n{links}\n"
    _, _, nav = _extract_fields(md)
    assert len(nav) <= 12  # MAX_NAV_ITEMS


def test_extract_fields_truncates_hero():
    long_hero = "A" * 300
    md = f"# {long_hero}\n\nSub."
    hero, _, _ = _extract_fields(md)
    assert len(hero) <= 200  # MAX_HEADLINE_LEN


def test_extract_fields_from_fixture():
    md = _load_fixture("snapshot_current.md")
    hero, _sub, nav = _extract_fields(md)
    assert hero is not None
    assert len(nav) > 0


# --- _diff_snapshots ---

def test_diff_snapshots_detects_hero_change():
    old = HomepageSnapshot(timestamp=date(2024, 11, 1), archive_url="https://old", hero_headline="Old Hero")
    new = HomepageSnapshot(timestamp=date(2026, 5, 1), archive_url="https://new", hero_headline="New Hero")
    changed, summary = _diff_snapshots(old, new)
    assert "hero_headline" in changed
    assert "Old Hero" in summary or "New Hero" in summary


def test_diff_snapshots_detects_nav_change():
    old = HomepageSnapshot(timestamp=date(2024, 11, 1), archive_url="https://old", primary_nav=["Product", "Blog"])
    new = HomepageSnapshot(timestamp=date(2026, 5, 1), archive_url="https://new", primary_nav=["Product", "Blog", "Pricing"])
    changed, summary = _diff_snapshots(old, new)
    assert "primary_nav" in changed
    assert summary is not None


def test_diff_snapshots_no_change():
    old = HomepageSnapshot(timestamp=date(2024, 11, 1), archive_url="https://x", hero_headline="Same", primary_nav=["A", "B"])
    new = HomepageSnapshot(timestamp=date(2026, 5, 1), archive_url="https://y", hero_headline="Same", primary_nav=["A", "B"])
    changed, summary = _diff_snapshots(old, new)
    assert changed == []
    assert summary is None


def test_diff_snapshots_detects_sub_headline_change():
    old = HomepageSnapshot(timestamp=date(2024, 11, 1), archive_url="https://old", sub_headline="Old sub")
    new = HomepageSnapshot(timestamp=date(2026, 5, 1), archive_url="https://new", sub_headline="New sub")
    changed, _summary = _diff_snapshots(old, new)
    assert "sub_headline" in changed
