# Phase 2.5a: `positioning_drift` Collector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `positioning_drift` collector that diffs Wayback Machine homepage snapshots at 6-month intervals over 18 months to detect messaging shift.

**Architecture:** The collector reuses `ctx.wayback.snapshots()` (already in the codebase and used by `pricing_packaging`). From each snapshot's markdown, three fields are extracted deterministically (hero headline, sub-headline, primary nav). The oldest and newest snapshots are diffed to produce `changed_fields` and `diff_summary`. No LLM used — all extraction is regex/text parsing.

**Tech Stack:** Python 3.12, Pydantic v2, pytest, asyncio. `WaybackClient.snapshots()` returns `list[Snapshot]` where each `Snapshot` has `.timestamp: datetime`, `.archive_url: str`, `.markdown: str`. Tests run with: `PYTHONPATH=. /Users/dalezwizinski/Documents/Apps/rrxray/.venv/bin/python -m pytest tests/ -v`

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `rrxray/schemas/positioning_drift.py` | Create | `HomepageSnapshot` + `PositioningDriftData` Pydantic models |
| `rrxray/collectors/_positioning_drift_catalog.py` | Create | Regex constants, extraction thresholds |
| `rrxray/collectors/positioning_drift.py` | Create | Collector: extraction helpers + `collect()` |
| `rrxray/schemas/data.py` | Modify | Add `positioning_drift` field to `CollectorOutputs` |
| `rrxray/pipeline.py` | Modify | Register `positioning_drift` in `COLLECTORS` |
| `templates/_positioning_drift_detail.md.jinja` | Create | Module Detail Appendix partial |
| `templates/report_internal.md.jinja` | Modify | Add include block in Module Detail Appendix |
| `tests/test_positioning_drift_schemas.py` | Create | Schema unit tests |
| `tests/test_positioning_drift_catalog.py` | Create | Catalog constant tests |
| `tests/test_positioning_drift.py` | Create | Collector function tests |
| `tests/test_schemas.py` | Modify | Add `CollectorOutputs.positioning_drift` field test |
| `tests/test_pipeline.py` | Modify | Add pipeline registration test |
| `tests/test_render_internal.py` | Modify | Add positioning_drift detail render test |
| `tests/fixtures/synthetic/positioning_drift/` | Create | Synthetic markdown fixtures |

---

### Task 1: Schema — `HomepageSnapshot` + `PositioningDriftData`

**Files:**
- Create: `rrxray/schemas/positioning_drift.py`
- Create: `tests/test_positioning_drift_schemas.py`

- [ ] **Step 1: Write failing schema tests**

Create `tests/test_positioning_drift_schemas.py`:

```python
"""Schema integrity tests for PositioningDriftData."""
from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

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
    import json
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=. /Users/dalezwizinski/Documents/Apps/rrxray/.venv/bin/python -m pytest tests/test_positioning_drift_schemas.py -v
```

Expected: `ModuleNotFoundError` or `ImportError` — `positioning_drift` schema doesn't exist yet.

- [ ] **Step 3: Create schema file**

Create `rrxray/schemas/positioning_drift.py`:

```python
"""Schemas for the positioning_drift collector."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from rrxray.schemas._shared import Finding, SourceCitation


class HomepageSnapshot(BaseModel):
    timestamp: date
    archive_url: str
    hero_headline: str | None = None
    sub_headline: str | None = None
    primary_nav: list[str] = []


class PositioningDriftData(BaseModel):
    snapshots: list[HomepageSnapshot] = []
    oldest_snapshot: HomepageSnapshot | None = None
    newest_snapshot: HomepageSnapshot | None = None
    changed_fields: list[str] = []
    diff_summary: str | None = None
    findings: list[Finding] = []
    gaps: list[str] = []
    discovery_questions: list[str] = []
    sources: list[SourceCitation] = []
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
PYTHONPATH=. /Users/dalezwizinski/Documents/Apps/rrxray/.venv/bin/python -m pytest tests/test_positioning_drift_schemas.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add rrxray/schemas/positioning_drift.py tests/test_positioning_drift_schemas.py
git commit -m "feat(2.5a): HomepageSnapshot + PositioningDriftData schemas"
```

---

### Task 2: Catalog Constants

**Files:**
- Create: `rrxray/collectors/_positioning_drift_catalog.py`
- Create: `tests/test_positioning_drift_catalog.py`

- [ ] **Step 1: Write failing catalog tests**

Create `tests/test_positioning_drift_catalog.py`:

```python
"""Tests for positioning_drift catalog constants."""
from __future__ import annotations

import re

from rrxray.collectors._positioning_drift_catalog import (
    MAX_HEADLINE_LEN,
    MAX_NAV_ITEMS,
    MAX_SUBNAV_TEXT_LEN,
    MIN_HEADLINE_LEN,
    NAV_SKIP_PATTERNS,
    _H1_RE,
    _MD_LINK_RE,
)


def test_constants_positive():
    assert MIN_HEADLINE_LEN > 0
    assert MAX_HEADLINE_LEN > MIN_HEADLINE_LEN
    assert MAX_SUBNAV_TEXT_LEN > 0
    assert MAX_NAV_ITEMS > 0


def test_h1_re_matches_h1():
    m = _H1_RE.search("# The fastest way to close deals\n\nParagraph.")
    assert m is not None
    assert m.group(1) == "The fastest way to close deals"


def test_h1_re_ignores_h2():
    m = _H1_RE.search("## Section Header\n\nParagraph.")
    assert m is None


def test_md_link_re_matches_nav_link():
    m = _MD_LINK_RE.search("[Pricing](/pricing)")
    assert m is not None
    assert m.group(1) == "Pricing"


def test_md_link_re_ignores_long_text():
    # Link text is >40 chars — should not match because pattern caps at 40
    m = _MD_LINK_RE.search("[This is a very long link text that should not be a nav item](/url)")
    assert m is None


def test_nav_skip_patterns_match_login():
    lower = "login"
    assert any(p.search(lower) for p in NAV_SKIP_PATTERNS)


def test_nav_skip_patterns_match_skip_to_content():
    lower = "skip to content"
    assert any(p.search(lower) for p in NAV_SKIP_PATTERNS)


def test_nav_skip_patterns_do_not_match_product():
    lower = "product"
    assert not any(p.search(lower) for p in NAV_SKIP_PATTERNS)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=. /Users/dalezwizinski/Documents/Apps/rrxray/.venv/bin/python -m pytest tests/test_positioning_drift_catalog.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Create catalog file**

Create `rrxray/collectors/_positioning_drift_catalog.py`:

```python
"""Constants for the positioning_drift collector."""
from __future__ import annotations

import re

# Extraction thresholds
MIN_HEADLINE_LEN = 10
MAX_HEADLINE_LEN = 200
MAX_SUBNAV_TEXT_LEN = 40
MAX_NAV_ITEMS = 12

# Regex: first H1 line (not H2+)
_H1_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)

# Regex: markdown link with text up to MAX_SUBNAV_TEXT_LEN chars
_MD_LINK_RE = re.compile(r"\[([^\]]{1,40})\]\([^\)]+\)")

# Nav link texts to skip (login, utility, skip-link patterns)
_NAV_SKIP_RAW = [
    r"^skip\b",
    r"^login$",
    r"^log\s?in$",
    r"^sign\s?in$",
    r"^sign\s?up$",
    r"^get\s+started$",
    r"cookie",
    r"^accessibility",
    r"^privacy",
    r"^terms",
    r"^\d+$",          # pure numbers
]
NAV_SKIP_PATTERNS: list[re.Pattern] = [re.compile(p, re.IGNORECASE) for p in _NAV_SKIP_RAW]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
PYTHONPATH=. /Users/dalezwizinski/Documents/Apps/rrxray/.venv/bin/python -m pytest tests/test_positioning_drift_catalog.py -v
```

Expected: all 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add rrxray/collectors/_positioning_drift_catalog.py tests/test_positioning_drift_catalog.py
git commit -m "feat(2.5a): positioning_drift catalog constants"
```

---

### Task 3: Extraction Helpers — `_extract_fields` and `_diff_snapshots`

**Files:**
- Create: `rrxray/collectors/positioning_drift.py` (partial — just helpers)
- Create: `tests/test_positioning_drift.py` (partial)

- [ ] **Step 1: Write failing extraction tests**

Create `tests/test_positioning_drift.py`:

```python
"""Tests for the positioning_drift collector."""
from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, UTC
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from rrxray.collectors.positioning_drift import (
    NAME,
    _diff_snapshots,
    _extract_fields,
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
    hero, sub, nav = _extract_fields(md)
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
    hero, sub, nav = _extract_fields(md)
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
    hero, sub, nav = _extract_fields(md)
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
    snap = HomepageSnapshot(timestamp=date(2024, 11, 1), archive_url="https://x", hero_headline="Same", primary_nav=["A", "B"])
    old = snap.model_copy()
    new = HomepageSnapshot(timestamp=date(2026, 5, 1), archive_url="https://y", hero_headline="Same", primary_nav=["A", "B"])
    changed, summary = _diff_snapshots(old, new)
    assert changed == []
    assert summary is None


def test_diff_snapshots_detects_sub_headline_change():
    old = HomepageSnapshot(timestamp=date(2024, 11, 1), archive_url="https://old", sub_headline="Old sub")
    new = HomepageSnapshot(timestamp=date(2026, 5, 1), archive_url="https://new", sub_headline="New sub")
    changed, summary = _diff_snapshots(old, new)
    assert "sub_headline" in changed
```

- [ ] **Step 2: Create fixture directory and files**

```bash
mkdir -p tests/fixtures/synthetic/positioning_drift
```

Create `tests/fixtures/synthetic/positioning_drift/snapshot_current.md`:

```markdown
# The fastest way to close B2B deals

Purpose-built for enterprise sales teams who need real pipeline visibility.

[Product](/product) [Pricing](/pricing) [Customers](/customers) [Blog](/blog) [About](/about)

## Why Acme

Acme helps revenue teams close more deals with less friction.

## Features

- Pipeline management
- Forecasting
- Analytics
```

Create `tests/fixtures/synthetic/positioning_drift/snapshot_old.md`:

```markdown
# Simple CRM for small sales teams

Easy to set up. No training required.

[Features](/features) [Pricing](/pricing) [Blog](/blog) [Contact](/contact)

## Built for Growing Teams

Acme gets out of your way so your team can sell.
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
PYTHONPATH=. /Users/dalezwizinski/Documents/Apps/rrxray/.venv/bin/python -m pytest tests/test_positioning_drift.py -v
```

Expected: `ModuleNotFoundError` or `ImportError` — collector doesn't exist yet.

- [ ] **Step 4: Create collector file with extraction helpers**

Create `rrxray/collectors/positioning_drift.py`:

```python
"""positioning_drift collector: Wayback homepage diffs detect messaging shift."""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from rrxray.collectors._positioning_drift_catalog import (
    MAX_HEADLINE_LEN,
    MAX_NAV_ITEMS,
    NAV_SKIP_PATTERNS,
    _H1_RE,
    _MD_LINK_RE,
)
from rrxray.schemas._shared import Finding, SourceCitation
from rrxray.schemas.positioning_drift import HomepageSnapshot, PositioningDriftData

if TYPE_CHECKING:
    from rrxray.context import CollectorContext

NAME = "positioning_drift"
log = logging.getLogger(f"rrxray.collectors.{NAME}")


def _extract_fields(markdown: str) -> tuple[str | None, str | None, list[str]]:
    """Extract (hero_headline, sub_headline, primary_nav) from homepage markdown.

    All extraction is deterministic — no LLM. Falls back gracefully on any missing
    element.
    """
    if not markdown:
        return None, None, []

    # Hero: first H1
    h1_match = _H1_RE.search(markdown)
    hero: str | None = None
    if h1_match:
        hero = h1_match.group(1).strip()[:MAX_HEADLINE_LEN]

    # Sub-headline: first non-empty, non-heading, non-link-only line after H1
    sub: str | None = None
    search_start = h1_match.end() if h1_match else 0
    for line in markdown[search_start:].splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            break  # hit next heading — stop looking
        if stripped.startswith("[") and stripped.endswith(")"):
            continue  # nav-link-only line
        sub = stripped[:300]
        break

    # Nav: markdown links in first third of document (or 1000 chars, whichever is larger)
    cutoff = max(len(markdown) // 3, 1000)
    nav_section = markdown[:cutoff]
    nav_items: list[str] = []
    seen: set[str] = set()
    for m in _MD_LINK_RE.finditer(nav_section):
        text = m.group(1).strip()
        if not text or len(text) < 2:
            continue
        lower = text.lower()
        if any(p.search(lower) for p in NAV_SKIP_PATTERNS):
            continue
        if lower in seen:
            continue
        seen.add(lower)
        nav_items.append(text)
        if len(nav_items) >= MAX_NAV_ITEMS:
            break

    return hero, sub, nav_items


def _diff_snapshots(
    oldest: HomepageSnapshot,
    newest: HomepageSnapshot,
) -> tuple[list[str], str | None]:
    """Compare oldest and newest snapshots. Return (changed_fields, diff_summary)."""
    changed: list[str] = []
    parts: list[str] = []

    # Hero headline
    if oldest.hero_headline != newest.hero_headline:
        changed.append("hero_headline")
        old_h = oldest.hero_headline or "(none)"
        new_h = newest.hero_headline or "(none)"
        parts.append(f"hero shifted from '{old_h[:60]}' to '{new_h[:60]}'")

    # Sub-headline
    if oldest.sub_headline != newest.sub_headline:
        changed.append("sub_headline")
        parts.append("sub-headline changed")

    # Primary nav (set comparison)
    old_nav = set(oldest.primary_nav)
    new_nav = set(newest.primary_nav)
    added = sorted(new_nav - old_nav)
    removed = sorted(old_nav - new_nav)
    if added or removed:
        changed.append("primary_nav")
        nav_parts: list[str] = []
        if added:
            nav_parts.append(f"{len(added)} nav item{'s' if len(added) > 1 else ''} added ({', '.join(added[:3])})")
        if removed:
            nav_parts.append(f"{len(removed)} nav item{'s' if len(removed) > 1 else ''} removed ({', '.join(removed[:3])})")
        parts.append("; ".join(nav_parts))

    summary = "; ".join(parts) if parts else None
    return changed, summary
```

- [ ] **Step 5: Run extraction tests**

```bash
PYTHONPATH=. /Users/dalezwizinski/Documents/Apps/rrxray/.venv/bin/python -m pytest tests/test_positioning_drift.py::test_name tests/test_positioning_drift.py::test_extract_fields_from_full_markdown tests/test_positioning_drift.py::test_extract_fields_no_h1 tests/test_positioning_drift.py::test_extract_fields_empty_markdown tests/test_positioning_drift.py::test_extract_fields_skips_login_nav tests/test_positioning_drift.py::test_extract_fields_caps_nav_items tests/test_positioning_drift.py::test_extract_fields_truncates_hero tests/test_positioning_drift.py::test_extract_fields_from_fixture tests/test_positioning_drift.py::test_diff_snapshots_detects_hero_change tests/test_positioning_drift.py::test_diff_snapshots_detects_nav_change tests/test_positioning_drift.py::test_diff_snapshots_no_change tests/test_positioning_drift.py::test_diff_snapshots_detects_sub_headline_change -v
```

Expected: all 12 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add rrxray/collectors/positioning_drift.py tests/test_positioning_drift.py tests/fixtures/synthetic/positioning_drift/
git commit -m "feat(2.5a): _extract_fields + _diff_snapshots helpers + fixtures"
```

---

### Task 4: Findings Logic — `_emit_findings`

**Files:**
- Modify: `rrxray/collectors/positioning_drift.py` (add `_emit_findings`)
- Modify: `tests/test_positioning_drift.py` (add findings tests)

- [ ] **Step 1: Write failing findings tests**

Append to `tests/test_positioning_drift.py`:

```python
from rrxray.collectors.positioning_drift import _emit_findings


# --- _emit_findings ---

def test_emit_findings_no_snapshots():
    findings, gaps, questions = _emit_findings("acme.com", [], [], None)
    assert len(findings) == 0
    assert len(gaps) == 1
    assert "Wayback" in gaps[0]
    assert len(questions) == 0


def test_emit_findings_one_snapshot():
    snap = HomepageSnapshot(timestamp=date(2026, 5, 1), archive_url="https://web.archive.org/x")
    findings, gaps, questions = _emit_findings("acme.com", [snap], [], None)
    assert len(findings) == 1
    assert "one" in findings[0].text.lower() or "1" in findings[0].text
    assert len(gaps) == 0


def test_emit_findings_stable_two_snapshots():
    old = HomepageSnapshot(timestamp=date(2024, 11, 1), archive_url="https://web.archive.org/old", hero_headline="Same")
    new = HomepageSnapshot(timestamp=date(2026, 5, 1), archive_url="https://web.archive.org/new", hero_headline="Same")
    findings, gaps, questions = _emit_findings("acme.com", [old, new], [], None)
    assert len(findings) == 1
    assert "stable" in findings[0].text.lower()
    assert len(questions) == 0


def test_emit_findings_hero_changed_produces_finding_and_question():
    old = HomepageSnapshot(timestamp=date(2024, 11, 1), archive_url="https://web.archive.org/old", hero_headline="Old Hero Message")
    new = HomepageSnapshot(timestamp=date(2026, 5, 1), archive_url="https://web.archive.org/new", hero_headline="New Hero Message")
    findings, gaps, questions = _emit_findings("acme.com", [old, new], ["hero_headline"], "hero shifted from 'Old Hero Message' to 'New Hero Message'")
    assert len(findings) == 1
    assert "shift" in findings[0].text.lower() or "drift" in findings[0].text.lower() or "changed" in findings[0].text.lower()
    assert len(questions) == 1
    assert "Old Hero Message" in questions[0] or "repositioning" in questions[0].lower()


def test_emit_findings_nav_changed_no_question():
    old = HomepageSnapshot(timestamp=date(2024, 11, 1), archive_url="https://web.archive.org/old", primary_nav=["Product", "Blog"])
    new = HomepageSnapshot(timestamp=date(2026, 5, 1), archive_url="https://web.archive.org/new", primary_nav=["Product", "Blog", "Pricing"])
    findings, gaps, questions = _emit_findings("acme.com", [old, new], ["primary_nav"], "1 nav item added (Pricing)")
    assert len(findings) == 1
    # Nav change alone does not produce a discovery question
    assert len(questions) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=. /Users/dalezwizinski/Documents/Apps/rrxray/.venv/bin/python -m pytest tests/test_positioning_drift.py::test_emit_findings_no_snapshots tests/test_positioning_drift.py::test_emit_findings_one_snapshot tests/test_positioning_drift.py::test_emit_findings_stable_two_snapshots tests/test_positioning_drift.py::test_emit_findings_hero_changed_produces_finding_and_question tests/test_positioning_drift.py::test_emit_findings_nav_changed_no_question -v
```

Expected: `ImportError` — `_emit_findings` not defined yet.

- [ ] **Step 3: Add `_emit_findings` to the collector**

Add after `_diff_snapshots` in `rrxray/collectors/positioning_drift.py`:

```python
def _emit_findings(
    domain: str,
    snapshots: list[HomepageSnapshot],
    changed_fields: list[str],
    diff_summary: str | None,
) -> tuple[list[Finding], list[str], list[str]]:
    """Rule-based findings, gaps, and discovery questions. No LLM."""
    now = datetime.now(UTC)
    source_url = f"https://{domain}"
    findings: list[Finding] = []
    gaps: list[str] = []
    questions: list[str] = []

    if not snapshots:
        gaps.append(
            "No Wayback Machine homepage snapshots recovered; "
            "positioning drift assessment not available for this domain."
        )
        return findings, gaps, questions

    if len(snapshots) == 1:
        findings.append(Finding(
            text=(
                f"Only one historical homepage snapshot recovered ({snapshots[0].timestamp}); "
                "drift assessment requires at least two data points."
            ),
            source=SourceCitation(url=source_url, timestamp=now),
        ))
        return findings, gaps, questions

    # 2+ snapshots
    date_range = f"{snapshots[0].timestamp} to {snapshots[-1].timestamp}"
    n = len(snapshots)

    if not changed_fields:
        findings.append(Finding(
            text=(
                f"Homepage messaging has been stable across {n} snapshots "
                f"in the 18-month window ({date_range}); hero headline, "
                "sub-headline, and primary nav are consistent."
            ),
            source=SourceCitation(url=source_url, timestamp=now),
        ))
        return findings, gaps, questions

    if diff_summary:
        findings.append(Finding(
            text=(
                f"Positioning shift detected across {n} snapshots ({date_range}): {diff_summary}."
            ),
            source=SourceCitation(url=source_url, timestamp=now),
        ))

    if "hero_headline" in changed_fields:
        old_h = snapshots[0].hero_headline or "(none)"
        new_h = snapshots[-1].hero_headline or "(none)"
        questions.append(
            f"Your homepage hero shifted from '{old_h[:60]}' to '{new_h[:60]}' "
            "over the past 18 months. What drove that repositioning: new ICP, "
            "competitive pressure, or internal rebrand?"
        )

    return findings, gaps, questions
```

- [ ] **Step 4: Run all findings tests**

```bash
PYTHONPATH=. /Users/dalezwizinski/Documents/Apps/rrxray/.venv/bin/python -m pytest tests/test_positioning_drift.py -v
```

Expected: all tests PASS (including Task 3 tests).

- [ ] **Step 5: Commit**

```bash
git add rrxray/collectors/positioning_drift.py tests/test_positioning_drift.py
git commit -m "feat(2.5a): _emit_findings rule-based logic"
```

---

### Task 5: Evidence + `collect()` Orchestrator

**Files:**
- Modify: `rrxray/collectors/positioning_drift.py` (add `_write_evidence` + `collect`)
- Modify: `tests/test_positioning_drift.py` (add orchestrator tests)

- [ ] **Step 1: Write failing orchestrator tests**

Append to `tests/test_positioning_drift.py`:

```python
from rrxray.collectors.positioning_drift import _write_evidence, collect


@pytest.fixture
def fake_wayback():
    from rrxray.services.wayback_client import Snapshot

    wc = MagicMock()
    # Two snapshots: older with old hero, newer with new hero
    old_snap = Snapshot(
        timestamp=datetime(2024, 11, 1, tzinfo=UTC),
        archive_url="https://web.archive.org/web/20241101/https://acme.com",
        html="<html><h1>Old Hero</h1></html>",
        markdown="# Old Hero\n\nOld sub.\n\n[Product](/product) [Blog](/blog)\n",
    )
    new_snap = Snapshot(
        timestamp=datetime(2026, 5, 1, tzinfo=UTC),
        archive_url="https://web.archive.org/web/20260501/https://acme.com",
        html="<html><h1>New Hero</h1></html>",
        markdown="# New Hero\n\nNew sub.\n\n[Product](/product) [Pricing](/pricing) [Blog](/blog)\n",
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
    assert result.oldest_snapshot.hero_headline == "Old Hero"
    assert result.newest_snapshot.hero_headline == "New Hero"
    assert "hero_headline" in result.changed_fields
    assert len(result.findings) >= 1
    assert result.gaps == []  # gaps only emitted when no snapshots recovered


def test_collect_writes_evidence_files(collector_ctx):
    asyncio.run(collect(collector_ctx))
    evidence = collector_ctx.evidence_dir / "positioning_drift"
    assert (evidence / "diff.json").exists()
    # At least one snapshot file
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=. /Users/dalezwizinski/Documents/Apps/rrxray/.venv/bin/python -m pytest tests/test_positioning_drift.py::test_collect_returns_positioning_drift_data tests/test_positioning_drift.py::test_collect_writes_evidence_files tests/test_positioning_drift.py::test_collect_graceful_degradation_on_wayback_error tests/test_positioning_drift.py::test_write_evidence_creates_files -v
```

Expected: `ImportError` — `collect` and `_write_evidence` not defined yet.

- [ ] **Step 3: Add `_write_evidence` and `collect` to the collector**

Append to `rrxray/collectors/positioning_drift.py`:

```python
def _write_evidence(
    evidence_dir: Path,
    snapshots: list[HomepageSnapshot],
    changed_fields: list[str],
    diff_summary: str | None,
) -> None:
    """Write snapshot summaries and diff JSON to evidence directory."""
    evidence_dir.mkdir(parents=True, exist_ok=True)
    # Remove stale snapshot files from prior runs
    for stale in evidence_dir.glob("snapshot_*.md"):
        stale.unlink()

    for s in snapshots:
        fname = f"snapshot_{s.timestamp.strftime('%Y%m%d')}.md"
        lines = [f"# Snapshot: {s.timestamp}\n", f"**Archive URL:** {s.archive_url}\n"]
        if s.hero_headline:
            lines.append(f"**Hero:** {s.hero_headline}\n")
        if s.sub_headline:
            lines.append(f"**Sub-headline:** {s.sub_headline}\n")
        if s.primary_nav:
            lines.append(f"**Nav:** {', '.join(s.primary_nav)}\n")
        (evidence_dir / fname).write_text("\n".join(lines), encoding="utf-8")

    diff_data = {"changed_fields": changed_fields, "diff_summary": diff_summary}
    (evidence_dir / "diff.json").write_text(
        json.dumps(diff_data, indent=2), encoding="utf-8"
    )


async def collect(ctx: "CollectorContext") -> PositioningDriftData:
    """Collect homepage positioning drift via Wayback Machine snapshot diffs."""
    from rrxray.services.wayback_client import WaybackError

    now = datetime.now(UTC)
    homepage_url = f"https://{ctx.domain}"

    # Fetch snapshots
    raw_snapshots = []
    try:
        raw_snapshots = await ctx.wayback.snapshots(
            homepage_url, interval_months=6, span_months=18
        )
    except WaybackError as e:
        log.warning("Wayback snapshots failed for %s: %s", ctx.domain, e)

    # Build HomepageSnapshot objects by extracting fields from markdown
    homepage_snapshots: list[HomepageSnapshot] = []
    for s in raw_snapshots:
        hero, sub, nav = _extract_fields(s.markdown or "")
        homepage_snapshots.append(HomepageSnapshot(
            timestamp=s.timestamp.date(),
            archive_url=s.archive_url,
            hero_headline=hero,
            sub_headline=sub,
            primary_nav=nav,
        ))

    # Sort ascending (oldest first) to ensure consistent oldest/newest assignment
    homepage_snapshots.sort(key=lambda s: s.timestamp)

    # Compute diff between oldest and newest
    oldest: HomepageSnapshot | None = None
    newest: HomepageSnapshot | None = None
    changed_fields: list[str] = []
    diff_summary: str | None = None

    if len(homepage_snapshots) >= 2:
        oldest = homepage_snapshots[0]
        newest = homepage_snapshots[-1]
        if oldest.timestamp != newest.timestamp:
            changed_fields, diff_summary = _diff_snapshots(oldest, newest)

    # Rule-based findings
    findings, gaps, questions = _emit_findings(
        ctx.domain, homepage_snapshots, changed_fields, diff_summary
    )

    # Write evidence
    _write_evidence(
        ctx.evidence_dir / NAME,
        homepage_snapshots,
        changed_fields,
        diff_summary,
    )

    # Source citations
    sources = [
        SourceCitation(url=s.archive_url, timestamp=now)
        for s in homepage_snapshots
    ]

    return PositioningDriftData(
        snapshots=homepage_snapshots,
        oldest_snapshot=oldest,
        newest_snapshot=newest,
        changed_fields=changed_fields,
        diff_summary=diff_summary,
        findings=findings,
        gaps=gaps,
        discovery_questions=questions,
        sources=sources,
    )
```

- [ ] **Step 4: Run all collector tests**

```bash
PYTHONPATH=. /Users/dalezwizinski/Documents/Apps/rrxray/.venv/bin/python -m pytest tests/test_positioning_drift.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add rrxray/collectors/positioning_drift.py tests/test_positioning_drift.py
git commit -m "feat(2.5a): _write_evidence + collect() orchestrator"
```

---

### Task 6: `CollectorOutputs` Field + Pipeline Registration

**Files:**
- Modify: `rrxray/schemas/data.py`
- Modify: `rrxray/pipeline.py`
- Modify: `tests/test_schemas.py`
- Modify: `tests/test_pipeline.py`

- [ ] **Step 1: Write failing schema + pipeline tests**

Append to `tests/test_schemas.py`:

```python
def test_collector_outputs_has_positioning_drift_field():
    from rrxray.schemas.data import CollectorOutputs
    outputs = CollectorOutputs()
    assert hasattr(outputs, "positioning_drift")
    assert outputs.positioning_drift is None
```

Append to `tests/test_pipeline.py`:

```python
def test_collectors_includes_positioning_drift():
    from rrxray import pipeline
    names = [c.NAME for c in pipeline.COLLECTORS]
    assert "positioning_drift" in names
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=. /Users/dalezwizinski/Documents/Apps/rrxray/.venv/bin/python -m pytest tests/test_schemas.py::test_collector_outputs_has_positioning_drift_field tests/test_pipeline.py::test_collectors_includes_positioning_drift -v
```

Expected: both FAIL — field not yet added.

- [ ] **Step 3: Add `positioning_drift` field to `CollectorOutputs` in `data.py`**

In `rrxray/schemas/data.py`, add the field to `CollectorOutputs` (after `funding_trajectory`):

```python
class CollectorOutputs(BaseModel):
    """One field per collector. None = not run or failed gracefully."""
    model_config = ConfigDict(validate_assignment=True)
    pricing_packaging: "PricingPackagingData | None" = None
    tech_stack: "TechStackData | None" = None
    revenue_motion: "RevenueMotionData | None" = None
    content_demand: "ContentDemandData | None" = None
    leadership_stability: "LeadershipStabilityData | None" = None
    funding_trajectory: "FundingTrajectoryData | None" = None
    positioning_drift: "PositioningDriftData | None" = None  # Phase 2.5a
```

At the bottom of `rrxray/schemas/data.py`, add the import and rebuild:

```python
from rrxray.schemas.positioning_drift import PositioningDriftData  # noqa: E402

CollectorOutputs.model_rebuild()
```

The full bottom section of `data.py` should be:

```python
# Resolve forward references
from rrxray.schemas.content_demand import ContentDemandData  # noqa: E402
from rrxray.schemas.funding_trajectory import FundingTrajectoryData  # noqa: E402
from rrxray.schemas.leadership_stability import LeadershipStabilityData  # noqa: E402
from rrxray.schemas.positioning_drift import PositioningDriftData  # noqa: E402
from rrxray.schemas.pricing_packaging import PricingPackagingData  # noqa: E402
from rrxray.schemas.revenue_motion import RevenueMotionData  # noqa: E402
from rrxray.schemas.tech_stack import TechStackData  # noqa: E402

CollectorOutputs.model_rebuild()
```

- [ ] **Step 4: Register `positioning_drift` in pipeline**

In `rrxray/pipeline.py`, add to the imports block (with other collectors):

```python
from rrxray.collectors import (
    content_demand,
    funding_trajectory,
    leadership_stability,
    positioning_drift,
    pricing_packaging,
    revenue_motion,
    tech_stack,
)
```

And add to `COLLECTORS` list after `funding_trajectory`:

```python
COLLECTORS = [
    pricing_packaging,
    tech_stack,
    revenue_motion,
    content_demand,
    leadership_stability,
    funding_trajectory,
    positioning_drift,
]
```

- [ ] **Step 5: Run tests**

```bash
PYTHONPATH=. /Users/dalezwizinski/Documents/Apps/rrxray/.venv/bin/python -m pytest tests/test_schemas.py::test_collector_outputs_has_positioning_drift_field tests/test_pipeline.py::test_collectors_includes_positioning_drift -v
```

Expected: both PASS.

- [ ] **Step 6: Run full test suite to check for regressions**

```bash
PYTHONPATH=. /Users/dalezwizinski/Documents/Apps/rrxray/.venv/bin/python -m pytest tests/ -v --tb=short
```

Expected: all previously passing tests still pass; 2 new tests pass.

- [ ] **Step 7: Commit**

```bash
git add rrxray/schemas/data.py rrxray/pipeline.py tests/test_schemas.py tests/test_pipeline.py
git commit -m "feat(2.5a): register positioning_drift in CollectorOutputs + pipeline"
```

---

### Task 7: Module Detail Partial + Report Template Include

**Files:**
- Create: `templates/_positioning_drift_detail.md.jinja`
- Modify: `templates/report_internal.md.jinja`
- Modify: `tests/test_render_internal.py`

- [ ] **Step 1: Write failing render test**

Read `tests/test_render_internal.py` first to understand the existing pattern, then append:

```python
def test_render_includes_positioning_drift_detail(tmp_path):
    """When positioning_drift collector data is present, the detail block renders."""
    from datetime import UTC, date, datetime

    from rrxray.rendering.markdown import render_internal
    from rrxray.schemas.data import (
        CollectorOutputs, InputParams, RunMetadata, SynthesizerOutputs, XrayData,
    )
    from rrxray.schemas.positioning_drift import HomepageSnapshot, PositioningDriftData

    snap = HomepageSnapshot(
        timestamp=date(2026, 5, 1),
        archive_url="https://web.archive.org/web/20260501/https://example.com",
        hero_headline="Fastest CRM for B2B teams",
        primary_nav=["Product", "Pricing", "Blog"],
    )
    data = XrayData(
        domain="example.com",
        run_metadata=RunMetadata(
            timestamp=datetime(2026, 5, 17, tzinfo=UTC),
            tool_version="0.1.0",
            modes_built=["internal"],
            model_used="claude-sonnet-4-6",
        ),
        inputs=InputParams(domain="example.com", mode="internal", model="claude-sonnet-4-6"),
        collectors=CollectorOutputs(
            positioning_drift=PositioningDriftData(
                snapshots=[snap],
                oldest_snapshot=snap,
                changed_fields=[],
                diff_summary=None,
            )
        ),
        synthesizers=SynthesizerOutputs(),
    )
    report = render_internal(data, output_dir=tmp_path)
    assert "Positioning Drift" in report
    assert "Fastest CRM for B2B teams" in report
```

- [ ] **Step 2: Run test to verify it fails**

```bash
PYTHONPATH=. /Users/dalezwizinski/Documents/Apps/rrxray/.venv/bin/python -m pytest tests/test_render_internal.py::test_render_includes_positioning_drift_detail -v
```

Expected: FAIL — no "Positioning Drift" in rendered output yet.

- [ ] **Step 3: Create partial template**

Create `templates/_positioning_drift_detail.md.jinja`:

```jinja
{# templates/_positioning_drift_detail.md.jinja #}
{% set pd = data.collectors.positioning_drift %}
**Snapshots recovered:** {{ pd.snapshots | length }}
{% if pd.snapshots %}
**Date range:** {{ pd.snapshots[0].timestamp }} to {{ pd.snapshots[-1].timestamp }}
{% endif %}
**Changed fields:** {% if pd.changed_fields %}{{ pd.changed_fields | join(", ") }}{% else %}none{% endif %}

{% if pd.diff_summary %}
**Drift summary:** {{ pd.diff_summary }}
{% endif %}

{% if pd.snapshots %}
| Date | Hero Headline | Nav Items |
|---|---|---|
{% for s in pd.snapshots %}
| {{ s.timestamp }} | {{ s.hero_headline or "(not recovered)" }} | {{ s.primary_nav | join(", ") or "(none)" }} |
{% endfor %}
{% endif %}

{% if pd.findings %}
**Findings:**

{% for f in pd.findings %}
- {{ f.text | voice_collector }} *(source: [{{ f.source.url }}]({{ f.source.url }}))*
{% endfor %}
{% endif %}

{% if pd.gaps %}
**Gaps:**

{% for g in pd.gaps %}
→ {{ g | voice_collector }}
{% endfor %}
{% endif %}

{% if pd.discovery_questions %}
**Discovery questions:**

{% for q in pd.discovery_questions %}
- {{ q | voice_collector }}
{% endfor %}
{% endif %}
```

- [ ] **Step 4: Add include block to `report_internal.md.jinja`**

In `templates/report_internal.md.jinja`, after the `{% if data.collectors.funding_trajectory %}` block and before the `---` separator, add:

```jinja
{% if data.collectors.positioning_drift %}
### Positioning Drift

{% include "_positioning_drift_detail.md.jinja" %}
{% endif %}
```

The Module Detail Appendix section should now look like:

```jinja
{% if data.collectors.pricing_packaging %}
### Pricing & Packaging

{% include "_pricing_detail.md.jinja" %}
{% else %}
[Pricing module not available for this domain]
{% endif %}

{% if data.collectors.tech_stack %}
### Tech Stack

{% include "_tech_stack_detail.md.jinja" %}
{% endif %}

{% if data.collectors.revenue_motion %}
### Revenue Motion

{% include "_revenue_motion_detail.md.jinja" %}
{% endif %}

{% if data.collectors.content_demand %}
### Content Demand

{% include "_content_demand_detail.md.jinja" %}
{% endif %}

{% if data.collectors.leadership_stability %}
### Leadership Stability

{% include "_leadership_stability_detail.md.jinja" %}
{% endif %}

{% if data.collectors.funding_trajectory %}
### Funding Trajectory

{% include "_funding_trajectory_detail.md.jinja" %}
{% endif %}

{% if data.collectors.positioning_drift %}
### Positioning Drift

{% include "_positioning_drift_detail.md.jinja" %}
{% endif %}
```

- [ ] **Step 5: Run render test**

```bash
PYTHONPATH=. /Users/dalezwizinski/Documents/Apps/rrxray/.venv/bin/python -m pytest tests/test_render_internal.py::test_render_includes_positioning_drift_detail -v
```

Expected: PASS.

- [ ] **Step 6: Run full test suite**

```bash
PYTHONPATH=. /Users/dalezwizinski/Documents/Apps/rrxray/.venv/bin/python -m pytest tests/ -v --tb=short
```

Expected: all tests pass; new test passes; no regressions.

- [ ] **Step 7: Lint**

```bash
PYTHONPATH=. /Users/dalezwizinski/Documents/Apps/rrxray/.venv/bin/python -m ruff check rrxray/ tests/
```

Expected: no lint errors.

- [ ] **Step 8: Commit**

```bash
git add templates/_positioning_drift_detail.md.jinja templates/report_internal.md.jinja tests/test_render_internal.py
git commit -m "feat(2.5a): positioning_drift Module Detail partial + report template include"
```

---

## Self-Review Checklist

After all tasks are committed, the implementer should verify:

- [ ] `rrxray/schemas/positioning_drift.py` has `HomepageSnapshot` and `PositioningDriftData`
- [ ] `rrxray/collectors/_positioning_drift_catalog.py` has all required constants
- [ ] `rrxray/collectors/positioning_drift.py` has `NAME`, `_extract_fields`, `_diff_snapshots`, `_emit_findings`, `_write_evidence`, `collect`
- [ ] `rrxray/schemas/data.py` has `positioning_drift: "PositioningDriftData | None" = None` in `CollectorOutputs` and the forward-ref import + `model_rebuild()`
- [ ] `rrxray/pipeline.py` imports `positioning_drift` and includes it in `COLLECTORS`
- [ ] `templates/_positioning_drift_detail.md.jinja` exists and shows the snapshot table
- [ ] `templates/report_internal.md.jinja` has the `{% if data.collectors.positioning_drift %}` block
- [ ] Full test suite passes with no regressions
- [ ] `ruff check` clean
