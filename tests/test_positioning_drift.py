"""Tests for the positioning_drift collector."""
from __future__ import annotations

import asyncio
import json
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from rrxray.collectors.positioning_drift import (
    NAME,
    _diff_snapshots,
    _emit_findings,
    _extract_fields,
    _write_evidence,
    collect,
)
from rrxray.schemas.positioning_drift import HomepageSnapshot, PositioningDriftData

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


# --- collect + _write_evidence ---

@pytest.fixture
def fake_wayback():
    from rrxray.services.wayback_client import Snapshot

    wc = MagicMock()
    old_snap = Snapshot(
        timestamp=datetime(2024, 11, 1, tzinfo=UTC),
        archive_url="https://web.archive.org/web/20241101/https://acme.com",
        html="<html><h1>Old Hero Headline</h1></html>",
        markdown="# Old Hero Headline\n\nOld sub.\n\n[Product](/product) [Blog](/blog)\n",
    )
    new_snap = Snapshot(
        timestamp=datetime(2026, 5, 1, tzinfo=UTC),
        archive_url="https://web.archive.org/web/20260501/https://acme.com",
        html="<html><h1>New Hero Headline</h1></html>",
        markdown="# New Hero Headline\n\nNew sub.\n\n[Product](/product) [Pricing](/pricing) [Blog](/blog)\n",
    )
    wc.snapshots = AsyncMock(return_value=[old_snap, new_snap])
    return wc


@pytest.fixture
def collector_ctx(tmp_path, fake_wayback):
    ctx = MagicMock()
    ctx.domain = "acme.com"
    ctx.company_name = "Acme"
    ctx.wayback = fake_wayback
    ctx.evidence_dir = tmp_path / "evidence"
    return ctx


def test_collect_returns_positioning_drift_data(collector_ctx):
    result = asyncio.run(collect(collector_ctx))
    assert isinstance(result, PositioningDriftData)
    assert len(result.snapshots) == 2
    assert result.oldest_snapshot is not None
    assert result.newest_snapshot is not None
    assert result.oldest_snapshot.hero_headline == "Old Hero Headline"
    assert result.newest_snapshot.hero_headline == "New Hero Headline"
    assert "hero_headline" in result.changed_fields
    assert len(result.findings) >= 1
    assert result.gaps == []


def test_collect_writes_evidence_files(collector_ctx):
    asyncio.run(collect(collector_ctx))
    evidence = collector_ctx.evidence_dir / "positioning_drift"
    assert (evidence / "diff.json").exists()
    snapshot_files = list(evidence.glob("snapshot_*.md"))
    assert len(snapshot_files) == 2


def test_collect_graceful_degradation_on_wayback_error(collector_ctx):
    from rrxray.services.wayback_client import WaybackError
    collector_ctx.wayback.snapshots = AsyncMock(side_effect=WaybackError("503"))
    result = asyncio.run(collect(collector_ctx))
    assert isinstance(result, PositioningDriftData)
    assert result.snapshots == []
    assert len(result.gaps) == 1
    assert "Wayback" in result.gaps[0]


def test_write_evidence_creates_files(tmp_path):
    evidence_dir = tmp_path / "positioning_drift"
    snaps = [
        HomepageSnapshot(timestamp=date(2024, 11, 1), archive_url="https://x", hero_headline="Old"),
        HomepageSnapshot(timestamp=date(2026, 5, 1), archive_url="https://y", hero_headline="New"),
    ]
    _write_evidence(evidence_dir, snaps, ["hero_headline"], "hero shifted from 'Old' to 'New'")
    assert (evidence_dir / "diff.json").exists()
    assert (evidence_dir / "snapshot_20241101.md").exists()
    assert (evidence_dir / "snapshot_20260501.md").exists()
    diff = json.loads((evidence_dir / "diff.json").read_text())
    assert "hero_headline" in diff["changed_fields"]
