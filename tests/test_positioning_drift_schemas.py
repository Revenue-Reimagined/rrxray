"""Schema integrity tests for PositioningDriftData."""
from __future__ import annotations

from datetime import UTC, date, datetime

from rrxray.schemas._shared import SourceCitation
from rrxray.schemas.positioning_drift import HomepageSnapshot, PositioningDriftData


def _source() -> SourceCitation:
    return SourceCitation(url="https://example.com", timestamp=datetime(2026, 5, 1, tzinfo=UTC))


def test_homepage_snapshot_minimal():
    s = HomepageSnapshot(timestamp=date(2026, 5, 1), archive_url="https://web.archive.org/web/20260501/https://ex.com")
    assert s.timestamp == date(2026, 5, 1)
    assert s.hero_headline is None
    assert s.sub_headline is None
    assert s.primary_nav == []


def test_homepage_snapshot_full():
    s = HomepageSnapshot(
        timestamp=date(2026, 5, 1),
        archive_url="https://web.archive.org/web/20260501/https://ex.com",
        hero_headline="The fastest way to close deals",
        sub_headline="Purpose-built for B2B sales teams",
        primary_nav=["Product", "Pricing", "Blog", "About"],
    )
    assert s.hero_headline == "The fastest way to close deals"
    assert len(s.primary_nav) == 4


def test_positioning_drift_data_defaults():
    d = PositioningDriftData()
    assert d.snapshots == []
    assert d.oldest_snapshot is None
    assert d.newest_snapshot is None
    assert d.changed_fields == []
    assert d.diff_summary is None
    assert d.findings == []
    assert d.gaps == []
    assert d.discovery_questions == []
    assert d.sources == []


def test_positioning_drift_data_with_snapshots():
    old = HomepageSnapshot(timestamp=date(2024, 11, 1), archive_url="https://web.archive.org/web/old", hero_headline="Old hero")
    new = HomepageSnapshot(timestamp=date(2026, 5, 1), archive_url="https://web.archive.org/web/new", hero_headline="New hero")
    d = PositioningDriftData(
        snapshots=[old, new],
        oldest_snapshot=old,
        newest_snapshot=new,
        changed_fields=["hero_headline"],
        diff_summary="hero shifted from 'Old hero' to 'New hero'",
    )
    assert len(d.snapshots) == 2
    assert d.changed_fields == ["hero_headline"]
    assert d.diff_summary is not None


def test_positioning_drift_data_round_trips_json():
    snap = HomepageSnapshot(
        timestamp=date(2026, 5, 1),
        archive_url="https://web.archive.org/web/20260501/https://ex.com",
        hero_headline="The fastest way to close deals",
        primary_nav=["Product", "Pricing"],
    )
    d = PositioningDriftData(snapshots=[snap], oldest_snapshot=snap)
    serialized = d.model_dump_json()
    restored = PositioningDriftData.model_validate_json(serialized)
    assert restored.snapshots[0].hero_headline == "The fastest way to close deals"
    assert restored.oldest_snapshot.primary_nav == ["Product", "Pricing"]
