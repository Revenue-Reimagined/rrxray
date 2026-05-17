"""Tests for the positioning_drift collector."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from rrxray.collectors.positioning_drift import (
    NAME,
    _diff_snapshots,
    _emit_findings,
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


# --- _emit_findings ---

def test_emit_findings_no_snapshots():
    findings, gaps, questions = _emit_findings("acme.com", [], [], None)
    assert len(findings) == 0
    assert len(gaps) == 1
    assert "Wayback" in gaps[0]
    assert len(questions) == 0


def test_emit_findings_one_snapshot():
    snap = HomepageSnapshot(timestamp=date(2026, 5, 1), archive_url="https://web.archive.org/x")
    findings, _gaps, _questions = _emit_findings("acme.com", [snap], [], None)
    assert len(findings) == 1
    assert "one" in findings[0].text.lower() or "1" in findings[0].text


def test_emit_findings_stable_two_snapshots():
    old = HomepageSnapshot(timestamp=date(2024, 11, 1), archive_url="https://web.archive.org/old", hero_headline="Same")
    new = HomepageSnapshot(timestamp=date(2026, 5, 1), archive_url="https://web.archive.org/new", hero_headline="Same")
    findings, _gaps, questions = _emit_findings("acme.com", [old, new], [], None)
    assert len(findings) == 1
    assert "stable" in findings[0].text.lower()
    assert len(questions) == 0


def test_emit_findings_hero_changed_produces_finding_and_question():
    old = HomepageSnapshot(timestamp=date(2024, 11, 1), archive_url="https://web.archive.org/old", hero_headline="Old Hero Message")
    new = HomepageSnapshot(timestamp=date(2026, 5, 1), archive_url="https://web.archive.org/new", hero_headline="New Hero Message")
    findings, _gaps, questions = _emit_findings("acme.com", [old, new], ["hero_headline"], "hero shifted from 'Old Hero Message' to 'New Hero Message'")
    assert len(findings) == 1
    assert "shift" in findings[0].text.lower() or "drift" in findings[0].text.lower() or "changed" in findings[0].text.lower() or "detect" in findings[0].text.lower()
    assert len(questions) == 1
    assert "Old Hero Message" in questions[0] or "repositioning" in questions[0].lower()


def test_emit_findings_nav_changed_no_question():
    old = HomepageSnapshot(timestamp=date(2024, 11, 1), archive_url="https://web.archive.org/old", primary_nav=["Product", "Blog"])
    new = HomepageSnapshot(timestamp=date(2026, 5, 1), archive_url="https://web.archive.org/new", primary_nav=["Product", "Blog", "Pricing"])
    findings, _gaps, questions = _emit_findings("acme.com", [old, new], ["primary_nav"], "1 nav item added (Pricing)")
    assert len(findings) == 1
    # Nav change alone does not produce a discovery question
    assert len(questions) == 0
