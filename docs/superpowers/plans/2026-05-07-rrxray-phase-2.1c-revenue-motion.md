# rrxray Phase 2.1c revenue_motion Collector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the `revenue_motion` collector as the third Section A signal. Scrapes the company's careers page (with ATS-link follow for Lever/Greenhouse/Ashby/Workable), runs LinkedIn search via Firecrawl for job postings + employee count snippet, classifies roles into 8 GTM categories (AE / SDR / RevOps / CSM / sales_leadership / marketing_leadership / marketing_ops / other) via a hardcoded keyword catalog, and emits findings + discovery questions from observable patterns.

**Architecture:** Same module-pattern collector as Phase 2.1a tech_stack. Adds `FirecrawlClient.search()` (deferred from Phase 1) which Phase 2.2 + 2.3 will also use. Section A synthesizer prompt template gets a third conditional block (Revenue Motion signal); the synthesizer body adds one line to read `revenue_motion` from `collector_outputs`. No schema changes outside the new `revenue_motion.py` schema and the one-line addition to `CollectorOutputs`.

**Tech Stack:** Python 3.12+, pydantic v2, jinja2, firecrawl-py (existing — extending the wrapper), pytest + pytest-asyncio, ruff. No new dependencies.

**Spec reference:** [docs/superpowers/specs/2026-05-07-rrxray-phase-2.1c-revenue-motion-design.md](../specs/2026-05-07-rrxray-phase-2.1c-revenue-motion-design.md)

---

## File Structure

`[T#]` indicates the task that creates or modifies each file.

```
NEW:
  rrxray/collectors/revenue_motion.py             [T5-T9: collector body]
  rrxray/collectors/_revenue_motion_catalog.py    [T4: role taxonomy + ATS patterns]
  rrxray/schemas/revenue_motion.py                [T2: RevenueMotionData, JobPosting]
  templates/_revenue_motion_detail.md.jinja       [T10: Module Detail partial]
  tests/test_revenue_motion.py                    [T5-T9: collector tests]
  tests/test_revenue_motion_catalog.py            [T4: catalog tests]
  tests/fixtures/synthetic/revenue_motion/        [T5-T7: HTML + JSON fixtures]

MODIFIED:
  rrxray/services/firecrawl_client.py             [T1: add search() method]
  tests/test_firecrawl_client.py                  [T1: search() tests]
  rrxray/schemas/data.py                          [T3: add revenue_motion field on CollectorOutputs]
  rrxray/pipeline.py                              [T12: append revenue_motion to COLLECTORS]
  rrxray/prompts/observed_gtm_motion.md           [T11: add Revenue Motion conditional block + framework guidance]
  rrxray/synthesizers/observed_gtm_motion.py      [T11: read revenue_motion from collector_outputs]
  tests/test_synthesizer_observed_gtm_motion.py   [T11: test_synth_runs_with_three_collectors]
  templates/report_internal.md.jinja              [T10: include _revenue_motion_detail partial]
```

---

## Task overview

12 tasks total. T1 is foundational (FirecrawlClient extension). T2-T9 build the collector. T10-T11 wire it into the renderer + synthesizer. T12 is pipeline registration + Dale-led quality gate (bounded by sign-off, not time).

- **T1: FirecrawlClient.search() extension**
- **T2: RevenueMotionData + JobPosting schemas**
- **T3: Add revenue_motion field to CollectorOutputs**
- **T4: Role catalog + ATS pattern catalog**
- **T5: Careers page URL discovery + ATS link follow (collector skeleton)**
- **T6: HTML role extraction**
- **T7: LinkedIn search integration (jobs + employee count)**
- **T8: Rule-based findings emission**
- **T9: Evidence writing + full collect() orchestration**
- **T10: Renderer template + integration**
- **T11: Synthesizer prompt + body update**
- **T12: Pipeline registration + quality gate (Dale-led)**

---

## Task 1: FirecrawlClient.search() extension

**Files:**
- Modify: `rrxray/services/firecrawl_client.py` (add `SearchResult` model + `search()` method)
- Modify: `tests/test_firecrawl_client.py` (append search tests)

- [ ] **Step 1: Inspect the firecrawl-py SDK to confirm the search method shape**

```bash
uv run python -c "
import firecrawl
import inspect
print('search methods on FirecrawlApp:')
methods = [m for m in dir(firecrawl.FirecrawlApp) if 'search' in m.lower()]
print(methods)
for m in methods:
    try:
        sig = inspect.signature(getattr(firecrawl.FirecrawlApp, m))
        print(f'  {m}{sig}')
    except (TypeError, ValueError):
        pass
"
```

Expected: shows the SDK's search method name and signature. firecrawl-py v2 typically exposes `.search(query, limit=...)`. If the method is named differently (e.g., `search_url`), adjust the wrapper accordingly.

- [ ] **Step 2: Append failing tests to `tests/test_firecrawl_client.py`**

```python
def test_search_returns_search_results(client, fake_sdk):
    """search() wraps SDK results into SearchResult objects."""
    fake_sdk.search.return_value = [
        {"url": "https://www.linkedin.com/jobs/view/12345",
         "title": "Account Executive at Acme Corp",
         "description": "Sell to enterprise customers..."},
        {"url": "https://www.linkedin.com/jobs/view/67890",
         "title": "SDR at Acme Corp",
         "description": "Inbound and outbound..."},
    ]

    results = asyncio.run(client.search("site:linkedin.com/jobs Acme Corp"))

    from rrxray.services.firecrawl_client import SearchResult
    assert len(results) == 2
    assert isinstance(results[0], SearchResult)
    assert results[0].url == "https://www.linkedin.com/jobs/view/12345"
    assert results[0].title == "Account Executive at Acme Corp"
    assert "enterprise" in results[0].description


def test_search_caches_result(client, fake_sdk):
    fake_sdk.search.return_value = [
        {"url": "https://example.com", "title": "x", "description": "y"},
    ]
    asyncio.run(client.search("test query"))
    asyncio.run(client.search("test query"))
    assert fake_sdk.search.call_count == 1


def test_search_handles_firecrawl_error(client, fake_sdk):
    fake_sdk.search.side_effect = RuntimeError("simulated failure")

    from rrxray.services.firecrawl_client import FirecrawlError
    with pytest.raises(FirecrawlError):
        asyncio.run(client.search("test query"))


def test_search_returns_empty_list_when_no_results(client, fake_sdk):
    fake_sdk.search.return_value = []
    results = asyncio.run(client.search("query with no matches"))
    assert results == []


def test_search_passes_limit_to_sdk(client, fake_sdk):
    fake_sdk.search.return_value = []
    asyncio.run(client.search("test", limit=5))
    args, kwargs = fake_sdk.search.call_args
    assert kwargs.get("limit") == 5 or args[1] == 5 if len(args) > 1 else False
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
uv run pytest tests/test_firecrawl_client.py -v -k search
```

Expected: 5 new tests fail with `AttributeError` (no `search` method) or import errors.

- [ ] **Step 4: Add `SearchResult` model + `search()` method to `rrxray/services/firecrawl_client.py`**

Append after the existing `ScrapedPage` model:

```python
class SearchResult(BaseModel):
    url: str
    title: str = ""
    description: str = ""
    metadata: dict[str, Any] = {}
```

Append `search()` method to the `FirecrawlClient` class (after `scrape_url`):

```python
    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        """Web search via Firecrawl SDK.

        Returns up to `limit` results. Useful for queries against LinkedIn,
        press release indexes, review sites, etc. Goes through the same
        cache layer as scrape_url.
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

            # firecrawl-py v2 may return a list of dicts directly OR a SearchResults
            # wrapper object; handle both.
            if hasattr(response, "model_dump"):
                payload = response.model_dump()
                if isinstance(payload, dict):
                    return payload.get("results", payload.get("data", []))
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
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/test_firecrawl_client.py -v -k search
```

Expected: 5 new tests pass.

- [ ] **Step 6: Run full suite + ruff**

```bash
uv run pytest -v 2>&1 | tail -3
uv run ruff check rrxray/ tests/
```

Expected: 188 passed, 1 skipped (183 prior + 5 new). Ruff clean.

- [ ] **Step 7: Commit**

```bash
git add rrxray/services/firecrawl_client.py tests/test_firecrawl_client.py
git commit -m "Add FirecrawlClient.search() method (Phase 1 deferred capability)

Async wrapper around the firecrawl-py SDK's search; same disk-cache +
concurrency-cap pattern as scrape_url. Returns list[SearchResult] with
url, title, description, plus a metadata dict for any extra fields the
SDK includes.

Used by Phase 2.1c revenue_motion (LinkedIn job search + employee
count snippet); Phase 2.2 leadership_stability (press release search);
Phase 2.3 buyer_sentiment (G2/Reddit/Glassdoor search) will reuse."
```

---

## Task 2: RevenueMotionData + JobPosting schemas

**Files:**
- Create: `rrxray/schemas/revenue_motion.py`
- Create: `tests/test_revenue_motion_schemas.py`

- [ ] **Step 1: Write failing tests in `tests/test_revenue_motion_schemas.py`**

```python
"""RevenueMotionData / JobPosting schema round-trip + validation."""
import json

import pytest
from pydantic import ValidationError

from rrxray.schemas.revenue_motion import JobPosting, RevenueMotionData, RoleCategory


def test_job_posting_minimal():
    j = JobPosting(
        title="Senior Account Executive",
        category="ae",
        source="company_careers",
    )
    assert j.title == "Senior Account Executive"
    assert j.category == "ae"
    assert j.source == "company_careers"
    assert j.url is None
    assert j.location is None


def test_job_posting_rejects_invalid_category():
    with pytest.raises(ValidationError):
        JobPosting(
            title="x", category="not_a_category",  # type: ignore[arg-type]
            source="company_careers",
        )


def test_job_posting_rejects_invalid_source():
    with pytest.raises(ValidationError):
        JobPosting(
            title="x", category="ae", source="not_a_source",  # type: ignore[arg-type]
        )


def test_revenue_motion_data_defaults_empty():
    d = RevenueMotionData()
    assert d.careers_page_url is None
    assert d.ats_platform is None
    assert d.open_roles == []
    assert d.role_counts == {}
    assert d.ae_to_sdr_ratio is None
    assert d.linkedin_employee_count is None
    assert d.linkedin_job_count is None
    assert d.findings == []
    assert d.gaps == []
    assert d.discovery_questions == []
    assert d.sources == []


def test_revenue_motion_data_round_trips():
    d = RevenueMotionData(
        careers_page_url="https://example.com/careers",
        ats_platform="lever",
        open_roles=[
            JobPosting(title="AE", category="ae", source="company_careers"),
            JobPosting(title="SDR", category="sdr", source="company_careers"),
        ],
        role_counts={"ae": 1, "sdr": 1},
        ae_to_sdr_ratio=1.0,
        linkedin_employee_count=247,
    )
    serialized = d.model_dump_json()
    restored = RevenueMotionData.model_validate(json.loads(serialized))
    assert restored.careers_page_url == "https://example.com/careers"
    assert restored.ats_platform == "lever"
    assert len(restored.open_roles) == 2
    assert restored.linkedin_employee_count == 247


def test_role_category_literal_includes_all_eight():
    """RoleCategory Literal must include all 8 categories named in the spec."""
    from typing import get_args
    expected = {
        "ae", "sdr", "revops", "csm",
        "sales_leadership", "marketing_leadership",
        "marketing_ops", "other",
    }
    actual = set(get_args(RoleCategory))
    assert actual == expected, f"missing={expected - actual}, extra={actual - expected}"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_revenue_motion_schemas.py -v
```

Expected: ERRORS with `ModuleNotFoundError: No module named 'rrxray.schemas.revenue_motion'`.

- [ ] **Step 3: Create `rrxray/schemas/revenue_motion.py`**

```python
"""Schemas specific to the revenue_motion collector."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from rrxray.schemas._shared import Finding, SourceCitation

RoleCategory = Literal[
    "ae",
    "sdr",
    "revops",
    "csm",
    "sales_leadership",
    "marketing_leadership",
    "marketing_ops",
    "other",
]


class JobPosting(BaseModel):
    title: str
    category: RoleCategory
    url: str | None = None
    source: Literal["company_careers", "ats", "linkedin"]
    location: str | None = None
    matched_keyword: str | None = None


class RevenueMotionData(BaseModel):
    careers_page_url: str | None = None
    ats_platform: str | None = None
    open_roles: list[JobPosting] = []
    role_counts: dict[str, int] = {}
    ae_to_sdr_ratio: float | None = None
    linkedin_employee_count: int | None = None
    linkedin_job_count: int | None = None
    findings: list[Finding] = []
    gaps: list[str] = []
    discovery_questions: list[str] = []
    sources: list[SourceCitation] = []
```

- [ ] **Step 4: Run tests to verify they pass + ruff**

```bash
uv run pytest tests/test_revenue_motion_schemas.py -v
uv run ruff check rrxray/ tests/
```

Expected: 6 tests pass. Ruff clean.

- [ ] **Step 5: Commit**

```bash
git add rrxray/schemas/revenue_motion.py tests/test_revenue_motion_schemas.py
git commit -m "Add RevenueMotionData and JobPosting schemas"
```

---

## Task 3: Add revenue_motion field to CollectorOutputs

**Files:**
- Modify: `rrxray/schemas/data.py`
- Modify: `tests/test_schemas.py`

- [ ] **Step 1: Append failing tests to `tests/test_schemas.py`**

```python
def test_collector_outputs_has_revenue_motion_field():
    """CollectorOutputs must accept a revenue_motion field."""
    from rrxray.schemas.data import CollectorOutputs
    from rrxray.schemas.revenue_motion import RevenueMotionData

    co = CollectorOutputs(revenue_motion=RevenueMotionData())
    assert co.revenue_motion is not None


def test_collector_outputs_revenue_motion_defaults_none():
    from rrxray.schemas.data import CollectorOutputs
    co = CollectorOutputs()
    assert co.revenue_motion is None


def test_collector_outputs_all_three_collectors_round_trip():
    import json
    from rrxray.schemas.data import CollectorOutputs
    from rrxray.schemas.pricing_packaging import PricingPackagingData
    from rrxray.schemas.tech_stack import DetectedTool, TechStackData
    from rrxray.schemas.revenue_motion import JobPosting, RevenueMotionData

    co = CollectorOutputs(
        pricing_packaging=PricingPackagingData(
            has_public_pricing=True, is_contact_us_gated=False,
            current_pricing_url="https://example.com/pricing",
        ),
        tech_stack=TechStackData(
            detected_tools=[DetectedTool(
                name="HubSpot", category="marketing_automation", confidence="high",
                signature_id="hubspot:strict_js", matched_text="x",
            )],
        ),
        revenue_motion=RevenueMotionData(
            careers_page_url="https://example.com/careers",
            open_roles=[JobPosting(title="AE", category="ae", source="company_careers")],
        ),
    )
    serialized = co.model_dump_json()
    restored = CollectorOutputs.model_validate(json.loads(serialized))
    assert restored.pricing_packaging is not None
    assert restored.tech_stack is not None
    assert restored.revenue_motion is not None
    assert restored.revenue_motion.open_roles[0].title == "AE"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_schemas.py -v -k revenue_motion
```

Expected: 3 new tests fail.

- [ ] **Step 3: Modify `rrxray/schemas/data.py`**

Add the `revenue_motion` field on `CollectorOutputs`:

```python
class CollectorOutputs(BaseModel):
    """One field per collector. None = not run or failed gracefully."""
    model_config = ConfigDict(validate_assignment=True)
    pricing_packaging: "PricingPackagingData | None" = None
    tech_stack: "TechStackData | None" = None
    revenue_motion: "RevenueMotionData | None" = None    # new
```

At the bottom of the file, alongside the existing forward-ref imports, add the new one and re-run rebuild:

```python
# Resolve forward references
from rrxray.schemas.pricing_packaging import PricingPackagingData  # noqa: E402
from rrxray.schemas.tech_stack import TechStackData  # noqa: E402
from rrxray.schemas.revenue_motion import RevenueMotionData  # noqa: E402

CollectorOutputs.model_rebuild()
```

- [ ] **Step 4: Run tests + ruff**

```bash
uv run pytest tests/test_schemas.py -v
uv run pytest -v 2>&1 | tail -3
uv run ruff check rrxray/ tests/
```

Expected: All 3 new tests pass; full suite at 197 passed (188 + 6 from T2 + 3 from T3 = 197), 1 skipped.

- [ ] **Step 5: Commit**

```bash
git add rrxray/schemas/data.py tests/test_schemas.py
git commit -m "Add revenue_motion field to CollectorOutputs"
```

---

## Task 4: Role catalog + ATS pattern catalog

**Files:**
- Create: `rrxray/collectors/_revenue_motion_catalog.py`
- Create: `tests/test_revenue_motion_catalog.py`
- Create: `tests/fixtures/synthetic/revenue_motion/.gitkeep`

- [ ] **Step 1: Write failing tests in `tests/test_revenue_motion_catalog.py`**

```python
"""Catalog integrity tests."""
import re

from rrxray.collectors._revenue_motion_catalog import (
    ATS_PATTERNS,
    ROLE_CATEGORIES,
    ROLE_KEYWORDS,
)


def test_role_categories_has_eight_entries():
    assert len(ROLE_CATEGORIES) == 8
    expected = {
        "ae", "sdr", "revops", "csm",
        "sales_leadership", "marketing_leadership",
        "marketing_ops", "other",
    }
    assert set(ROLE_CATEGORIES) == expected


def test_role_keywords_all_have_required_keys():
    for entry in ROLE_KEYWORDS:
        assert "category" in entry
        assert "keywords" in entry
        assert isinstance(entry["keywords"], list)
        assert len(entry["keywords"]) > 0


def test_role_keywords_categories_are_valid():
    valid = set(ROLE_CATEGORIES)
    for entry in ROLE_KEYWORDS:
        assert entry["category"] in valid, (
            f"unknown category {entry['category']}"
        )


def test_role_keywords_cover_major_categories():
    """Spec mandate: every major revenue role category should have keywords."""
    covered = {entry["category"] for entry in ROLE_KEYWORDS}
    required = {"ae", "sdr", "revops", "csm", "sales_leadership"}
    missing = required - covered
    assert not missing, f"required categories missing: {missing}"


def test_ats_patterns_has_four_platforms():
    """Lever, Greenhouse, Ashby, Workable — the four most common B2B SaaS ATS platforms."""
    assert len(ATS_PATTERNS) >= 4
    names = {p["name"] for p in ATS_PATTERNS}
    expected = {"lever", "greenhouse", "ashby", "workable"}
    assert expected.issubset(names)


def test_ats_patterns_are_valid_regex():
    for entry in ATS_PATTERNS:
        re.compile(entry["url_pattern"])


def test_ats_patterns_match_real_urls():
    """Each ATS pattern should match a typical URL for that platform."""
    test_cases = [
        ("lever", "https://jobs.lever.co/swayable", True),
        ("greenhouse", "https://boards.greenhouse.io/linear", True),
        ("ashby", "https://example.ashbyhq.com", True),
        ("workable", "https://apply.workable.com/example", True),
        ("lever", "https://example.com/careers", False),
    ]
    for platform, url, should_match in test_cases:
        pattern = next(p for p in ATS_PATTERNS if p["name"] == platform)
        m = re.search(pattern["url_pattern"], url)
        if should_match:
            assert m is not None, f"{platform} pattern should match {url}"
        else:
            assert m is None, f"{platform} pattern should NOT match {url}"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_revenue_motion_catalog.py -v
```

Expected: ImportError on the catalog module.

- [ ] **Step 3: Create `rrxray/collectors/_revenue_motion_catalog.py`**

```python
"""Role-taxonomy and ATS-pattern catalogs for the revenue_motion collector.

Hardcoded keyword catalog matches the Phase 2.1a tech_stack pattern: deterministic,
no LLM in collector path, easy to extend by appending entries. When new role title
patterns surface that don't match, append them here.

Adding a role keyword: append a dict to ROLE_KEYWORDS (entries are processed in order;
more specific patterns first beat generic ones).

Adding an ATS platform: append a dict to ATS_PATTERNS with name + url_pattern (regex).
"""
from __future__ import annotations

ROLE_CATEGORIES: list[str] = [
    "ae",
    "sdr",
    "revops",
    "csm",
    "sales_leadership",
    "marketing_leadership",
    "marketing_ops",
    "other",
]


# Order matters: more specific titles checked first
ROLE_KEYWORDS: list[dict] = [
    # AE titles (specific multi-word first)
    {"category": "ae", "keywords": [
        "enterprise account executive",
        "strategic account executive",
        "mid-market account executive",
        "senior account executive",
        "account executive",
        "sales representative",
    ]},
    {"category": "ae", "keywords": [
        "AE", "enterprise AE", "strategic AE", "founding AE",
    ]},

    # SDR titles
    {"category": "sdr", "keywords": [
        "sales development representative",
        "business development representative",
        "outbound SDR",
        "inbound SDR",
    ]},
    {"category": "sdr", "keywords": ["SDR", "BDR"]},

    # RevOps
    {"category": "revops", "keywords": [
        "revenue operations",
        "sales operations",
        "go-to-market operations",
        "GTM operations",
    ]},
    {"category": "revops", "keywords": ["RevOps", "SalesOps"]},

    # CSM
    {"category": "csm", "keywords": [
        "customer success manager",
        "customer success",
        "account manager",
        "post-sales",
        "renewals manager",
    ]},
    {"category": "csm", "keywords": ["CSM"]},

    # Sales leadership (specific titles)
    {"category": "sales_leadership", "keywords": [
        "chief revenue officer",
        "VP of sales",
        "VP sales",
        "head of sales",
        "director of sales",
        "VP revenue",
        "VP of revenue",
        "head of revenue",
    ]},
    {"category": "sales_leadership", "keywords": ["CRO"]},

    # Marketing leadership
    {"category": "marketing_leadership", "keywords": [
        "chief marketing officer",
        "VP marketing",
        "VP of marketing",
        "head of marketing",
        "director of marketing",
    ]},
    {"category": "marketing_leadership", "keywords": ["CMO"]},

    # Marketing ops
    {"category": "marketing_ops", "keywords": [
        "marketing operations",
        "marketing ops",
        "demand generation",
        "demand gen",
    ]},
]


# ATS platform detection patterns. Each entry's url_pattern is a regex applied
# (case-insensitive) against any link href found in scraped careers-page HTML.
ATS_PATTERNS: list[dict[str, str]] = [
    {"name": "lever", "url_pattern": r"jobs\.lever\.co/([a-z0-9-]+)"},
    {"name": "greenhouse", "url_pattern": r"boards\.greenhouse\.io/([a-z0-9-]+)"},
    {"name": "ashby", "url_pattern": r"([a-z0-9-]+)\.ashbyhq\.com"},
    {"name": "workable", "url_pattern": r"apply\.workable\.com/([a-z0-9-]+)"},
]
```

- [ ] **Step 4: Create the fixture directory marker**

```bash
mkdir -p tests/fixtures/synthetic/revenue_motion
touch tests/fixtures/synthetic/revenue_motion/.gitkeep
```

- [ ] **Step 5: Run tests + ruff**

```bash
uv run pytest tests/test_revenue_motion_catalog.py -v
uv run ruff check rrxray/ tests/
```

Expected: 7 catalog tests pass. Ruff clean.

- [ ] **Step 6: Commit**

```bash
git add rrxray/collectors/_revenue_motion_catalog.py tests/test_revenue_motion_catalog.py tests/fixtures/synthetic/revenue_motion/.gitkeep
git commit -m "Add revenue_motion role catalog (8 categories) + ATS patterns (4 platforms)"
```

---

## Task 5: Careers page URL discovery + ATS link follow

**Files:**
- Create: `rrxray/collectors/revenue_motion.py` (skeleton with `NAME`, `_discover_careers_url`, `_detect_ats`)
- Create: `tests/test_revenue_motion.py` (skeleton with helpers + tests for these two functions)
- Create: `tests/fixtures/synthetic/revenue_motion/careers_simple.html`
- Create: `tests/fixtures/synthetic/revenue_motion/careers_with_ats_link.html`

- [ ] **Step 1: Create the synthetic HTML fixtures**

`tests/fixtures/synthetic/revenue_motion/careers_simple.html`:

```html
<!doctype html>
<html><head><title>Careers — Acme</title></head>
<body>
<h1>Open Roles</h1>
<ul>
  <li><a href="/careers/account-executive">Senior Account Executive</a></li>
  <li><a href="/careers/sdr">Sales Development Representative</a></li>
  <li><a href="/careers/cto">Chief Technology Officer</a></li>
</ul>
</body></html>
```

`tests/fixtures/synthetic/revenue_motion/careers_with_ats_link.html`:

```html
<!doctype html>
<html><head><title>Join Acme</title></head>
<body>
<p>We post all our open roles on Lever:</p>
<a href="https://jobs.lever.co/acme">View open positions on Lever</a>
</body></html>
```

- [ ] **Step 2: Write failing tests in `tests/test_revenue_motion.py`**

```python
"""revenue_motion collector tests."""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from rrxray.collectors import revenue_motion
from rrxray.context import CollectorContext


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "synthetic" / "revenue_motion"


def _load(name: str) -> str:
    return (FIXTURE_DIR / name).read_text()


def _make_ctx(
    tmp_path: Path,
    scrape_responses: dict[str, dict] | None = None,
    search_responses: dict[str, list[dict]] | None = None,
) -> CollectorContext:
    """Build a CollectorContext with mocked Firecrawl scrape + search."""
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

    async def fake_search(query, limit=10):
        if search_responses is None:
            return []
        # Match by substring (any registered query that's a substring of the actual query matches)
        from rrxray.services.firecrawl_client import SearchResult
        for key, items in search_responses.items():
            if key in query:
                return [SearchResult(**item) for item in items[:limit]]
        return []

    fc.scrape_url = AsyncMock(side_effect=fake_scrape)
    fc.search = AsyncMock(side_effect=fake_search)

    wb = MagicMock()
    wb.snapshots = AsyncMock(return_value=[])
    config = MagicMock(domain="acme.com")
    return CollectorContext(
        domain="acme.com",
        company_name=None,
        firecrawl=fc,
        wayback=wb,
        evidence_dir=tmp_path / "evidence",
        config=config,
    )


def test_collector_name_constant():
    assert revenue_motion.NAME == "revenue_motion"


def test_discover_careers_url_at_slash_careers(tmp_path):
    ctx = _make_ctx(tmp_path, scrape_responses={
        "https://acme.com/careers": {
            "html": _load("careers_simple.html"),
            "markdown": "# Careers",
            "metadata": {"sourceURL": "https://acme.com/careers"},
        },
    })
    url, page = asyncio.run(revenue_motion._discover_careers_url(ctx))
    assert url == "https://acme.com/careers"
    assert page is not None


def test_discover_careers_url_falls_back_to_slash_jobs(tmp_path):
    ctx = _make_ctx(tmp_path, scrape_responses={
        "https://acme.com/jobs": {
            "html": _load("careers_simple.html"),
            "markdown": "# Jobs",
            "metadata": {"sourceURL": "https://acme.com/jobs"},
        },
    })
    url, _ = asyncio.run(revenue_motion._discover_careers_url(ctx))
    assert url == "https://acme.com/jobs"


def test_discover_careers_url_returns_none_when_nothing_found(tmp_path):
    ctx = _make_ctx(tmp_path, scrape_responses={})
    url, page = asyncio.run(revenue_motion._discover_careers_url(ctx))
    assert url is None
    assert page is None


def test_detect_ats_lever():
    html = _load("careers_with_ats_link.html")
    name, url = revenue_motion._detect_ats(html)
    assert name == "lever"
    assert "jobs.lever.co/acme" in url


def test_detect_ats_greenhouse():
    html = '<a href="https://boards.greenhouse.io/linear">Apply</a>'
    name, url = revenue_motion._detect_ats(html)
    assert name == "greenhouse"


def test_detect_ats_ashby():
    html = '<iframe src="https://example.ashbyhq.com/embed"></iframe>'
    name, url = revenue_motion._detect_ats(html)
    assert name == "ashby"


def test_detect_ats_workable():
    html = '<a href="https://apply.workable.com/exampleco">View jobs</a>'
    name, url = revenue_motion._detect_ats(html)
    assert name == "workable"


def test_detect_ats_returns_none_when_no_ats_link():
    html = _load("careers_simple.html")
    name, url = revenue_motion._detect_ats(html)
    assert name is None
    assert url is None
```

- [ ] **Step 3: Create `rrxray/collectors/revenue_motion.py` skeleton**

```python
"""revenue_motion collector: careers page + LinkedIn job + employee count signals."""
from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from rrxray.collectors._revenue_motion_catalog import ATS_PATTERNS

if TYPE_CHECKING:
    from rrxray.context import CollectorContext

NAME = "revenue_motion"
log = logging.getLogger(f"rrxray.collectors.{NAME}")

CANDIDATE_PATHS = ["/careers", "/jobs", "/work-with-us", "/join-us"]


async def _discover_careers_url(ctx: "CollectorContext"):
    """Try standard careers paths. Return (url, ScrapedPage) or (None, None)."""
    from rrxray.services.firecrawl_client import FirecrawlError
    base = f"https://{ctx.domain}"
    for path in CANDIDATE_PATHS:
        url = base + path
        try:
            page = await ctx.firecrawl.scrape_url(url, only_main_content=False)
            html = page.html or ""
            if html.strip() and len(html) > 200:
                return url, page
        except FirecrawlError as e:
            log.debug("careers discover: %s not reachable: %s", url, e)
            continue
    return None, None


def _detect_ats(html: str) -> tuple[str | None, str | None]:
    """Scan HTML for known ATS subdomain links. Return (platform_name, full_url) or (None, None)."""
    if not html:
        return None, None
    for pattern_entry in ATS_PATTERNS:
        m = re.search(pattern_entry["url_pattern"], html, re.IGNORECASE)
        if m:
            return pattern_entry["name"], m.group(0)
    return None, None
```

- [ ] **Step 4: Run tests + ruff**

```bash
uv run pytest tests/test_revenue_motion.py -v
uv run ruff check rrxray/ tests/
```

Expected: 9 tests pass.

- [ ] **Step 5: Commit**

```bash
git add rrxray/collectors/revenue_motion.py tests/test_revenue_motion.py tests/fixtures/synthetic/revenue_motion/*.html
git commit -m "Add revenue_motion collector skeleton: careers URL discovery + ATS detection"
```

---

## Task 6: HTML role extraction

**Files:**
- Modify: `rrxray/collectors/revenue_motion.py` (append `_categorize_title`, `_extract_roles`)
- Modify: `tests/test_revenue_motion.py` (append role extraction tests)

- [ ] **Step 1: Append failing tests**

```python
def test_categorize_title_ae():
    cat, kw = revenue_motion._categorize_title("Senior Account Executive")
    assert cat == "ae"
    assert "account executive" in kw.lower()


def test_categorize_title_sdr():
    cat, _ = revenue_motion._categorize_title("Sales Development Representative")
    assert cat == "sdr"


def test_categorize_title_bdr():
    cat, _ = revenue_motion._categorize_title("BDR — Outbound")
    assert cat == "sdr"


def test_categorize_title_sales_leadership():
    for title in ["VP of Sales", "Chief Revenue Officer", "Head of Revenue"]:
        cat, _ = revenue_motion._categorize_title(title)
        assert cat == "sales_leadership", f"{title} should be sales_leadership; got {cat}"


def test_categorize_title_csm():
    cat, _ = revenue_motion._categorize_title("Senior Customer Success Manager")
    assert cat == "csm"


def test_categorize_title_unknown_returns_other():
    cat, kw = revenue_motion._categorize_title("Senior Software Engineer")
    assert cat == "other"
    assert kw is None


def test_categorize_title_case_insensitive():
    cat, _ = revenue_motion._categorize_title("ACCOUNT EXECUTIVE")
    assert cat == "ae"


def test_extract_roles_from_simple_careers_page():
    html = _load("careers_simple.html")
    roles = revenue_motion._extract_roles(html, source="company_careers", base_url="https://acme.com")
    titles = [r.title for r in roles]
    assert "Senior Account Executive" in titles
    assert "Sales Development Representative" in titles
    # Non-revenue roles should be assigned category="other" but still surfaced
    assert "Chief Technology Officer" in titles


def test_extract_roles_categorizes_correctly():
    html = _load("careers_simple.html")
    roles = revenue_motion._extract_roles(html, source="company_careers", base_url="https://acme.com")
    cat_map = {r.title: r.category for r in roles}
    assert cat_map["Senior Account Executive"] == "ae"
    assert cat_map["Sales Development Representative"] == "sdr"
    assert cat_map["Chief Technology Officer"] == "other"


def test_extract_roles_resolves_relative_urls():
    html = _load("careers_simple.html")
    roles = revenue_motion._extract_roles(html, source="company_careers", base_url="https://acme.com")
    ae_role = next(r for r in roles if r.category == "ae")
    assert ae_role.url is not None
    # Relative URL /careers/account-executive should resolve to absolute
    assert ae_role.url.startswith("https://acme.com")


def test_extract_roles_returns_empty_for_html_with_no_links():
    roles = revenue_motion._extract_roles(
        "<html><body><p>No jobs</p></body></html>",
        source="company_careers",
        base_url="https://acme.com",
    )
    assert roles == []
```

- [ ] **Step 2: Append implementation to `rrxray/collectors/revenue_motion.py`**

```python
from urllib.parse import urljoin  # noqa: E402

from rrxray.collectors._revenue_motion_catalog import ROLE_KEYWORDS  # noqa: E402
from rrxray.schemas.revenue_motion import JobPosting  # noqa: E402


# Compile keyword patterns once at module load. Each entry maps a category to
# a list of (keyword, compiled_pattern) tuples, ordered by specificity.
def _compile_role_patterns() -> list[tuple[str, str, "re.Pattern"]]:
    compiled = []
    for entry in ROLE_KEYWORDS:
        for kw in entry["keywords"]:
            # Word-boundary match for short tokens; substring otherwise.
            if len(kw) <= 4 and kw.isupper():
                # Acronyms like "AE", "SDR", "CRO" need word boundaries to avoid false matches.
                pattern = re.compile(rf"\b{re.escape(kw)}\b", re.IGNORECASE)
            else:
                pattern = re.compile(re.escape(kw), re.IGNORECASE)
            compiled.append((entry["category"], kw, pattern))
    return compiled


_ROLE_PATTERNS = _compile_role_patterns()


def _categorize_title(title: str) -> tuple[str, str | None]:
    """Categorize a job title via the keyword catalog.

    Returns (category, matched_keyword) — first match wins. Falls back to
    ('other', None) if no keyword matches.
    """
    for category, keyword, pattern in _ROLE_PATTERNS:
        if pattern.search(title):
            return category, keyword
    return "other", None


_LINK_RE = re.compile(
    r'<a[^>]*\bhref=["\']([^"\']+)["\'][^>]*>([^<]+)</a>',
    re.IGNORECASE,
)


def _extract_roles(html: str, source: str, base_url: str) -> list[JobPosting]:
    """Extract job postings from HTML.

    Parses anchor tags and treats their text as role titles. Categorizes via
    the role catalog. Resolves relative URLs against base_url.
    """
    if not html:
        return []
    roles: list[JobPosting] = []
    seen_titles: set[str] = set()
    for m in _LINK_RE.finditer(html):
        href = m.group(1).strip()
        title = m.group(2).strip()
        if not title or len(title) > 200:
            continue
        if title in seen_titles:
            continue
        seen_titles.add(title)
        category, matched = _categorize_title(title)
        full_url = urljoin(base_url, href) if href and not href.startswith("#") else None
        roles.append(JobPosting(
            title=title,
            category=category,  # type: ignore[arg-type]
            url=full_url,
            source=source,  # type: ignore[arg-type]
            matched_keyword=matched,
        ))
    return roles
```

- [ ] **Step 3: Run tests + ruff**

```bash
uv run pytest tests/test_revenue_motion.py -v
uv run ruff check rrxray/ tests/
```

Expected: 19 tests total in this file (9 from T5 + 10 from T6) all pass.

- [ ] **Step 4: Commit**

```bash
git add rrxray/collectors/revenue_motion.py tests/test_revenue_motion.py
git commit -m "Add HTML role extraction with title categorization"
```

---

## Task 7: LinkedIn search integration

**Files:**
- Modify: `rrxray/collectors/revenue_motion.py` (append `_linkedin_search_jobs`, `_linkedin_employee_count`)
- Modify: `tests/test_revenue_motion.py` (append LinkedIn search tests)

- [ ] **Step 1: Append failing tests**

```python
def test_linkedin_search_jobs_parses_results(tmp_path):
    ctx = _make_ctx(tmp_path, search_responses={
        "site:linkedin.com/jobs": [
            {"url": "https://www.linkedin.com/jobs/view/123",
             "title": "Account Executive at Acme Corp",
             "description": "Sell to enterprise..."},
            {"url": "https://www.linkedin.com/jobs/view/456",
             "title": "SDR at Acme Corp",
             "description": "Outbound prospecting..."},
            {"url": "https://www.linkedin.com/jobs/view/789",
             "title": "Senior Engineer at Acme Corp",
             "description": "Build the platform..."},
        ],
    })
    roles = asyncio.run(revenue_motion._linkedin_search_jobs(ctx.firecrawl, "acme.com"))
    assert len(roles) == 3
    titles = [r.title for r in roles]
    assert "Account Executive at Acme Corp" in titles
    cat_map = {r.title: r.category for r in roles}
    # The categorizer pulls 'account executive' substring out of full LinkedIn title
    assert cat_map["Account Executive at Acme Corp"] == "ae"
    assert all(r.source == "linkedin" for r in roles)


def test_linkedin_search_jobs_empty_when_no_results(tmp_path):
    ctx = _make_ctx(tmp_path, search_responses={})
    roles = asyncio.run(revenue_motion._linkedin_search_jobs(ctx.firecrawl, "acme.com"))
    assert roles == []


def test_linkedin_search_jobs_swallows_firecrawl_error(tmp_path):
    """Search failure must NOT raise — collector continues with careers data."""
    ctx = _make_ctx(tmp_path)

    async def fail(query, limit=10):
        from rrxray.services.firecrawl_client import FirecrawlError
        raise FirecrawlError("simulated failure")

    ctx.firecrawl.search = AsyncMock(side_effect=fail)
    roles = asyncio.run(revenue_motion._linkedin_search_jobs(ctx.firecrawl, "acme.com"))
    assert roles == []


def test_linkedin_employee_count_parses_snippet(tmp_path):
    ctx = _make_ctx(tmp_path, search_responses={
        "site:linkedin.com/company": [
            {"url": "https://www.linkedin.com/company/acme",
             "title": "Acme Corp | LinkedIn",
             "description": "Acme Corp · Software · 247 employees on LinkedIn ..."},
        ],
    })
    count = asyncio.run(revenue_motion._linkedin_employee_count(ctx.firecrawl, "acme.com"))
    assert count == 247


def test_linkedin_employee_count_returns_none_when_snippet_unparseable(tmp_path):
    ctx = _make_ctx(tmp_path, search_responses={
        "site:linkedin.com/company": [
            {"url": "https://www.linkedin.com/company/acme",
             "title": "Acme | LinkedIn",
             "description": "no number in this description"},
        ],
    })
    count = asyncio.run(revenue_motion._linkedin_employee_count(ctx.firecrawl, "acme.com"))
    assert count is None


def test_linkedin_employee_count_handles_search_failure(tmp_path):
    ctx = _make_ctx(tmp_path)

    async def fail(query, limit=10):
        from rrxray.services.firecrawl_client import FirecrawlError
        raise FirecrawlError("boom")

    ctx.firecrawl.search = AsyncMock(side_effect=fail)
    count = asyncio.run(revenue_motion._linkedin_employee_count(ctx.firecrawl, "acme.com"))
    assert count is None
```

- [ ] **Step 2: Append implementation to `rrxray/collectors/revenue_motion.py`**

```python
async def _linkedin_search_jobs(firecrawl, domain: str) -> list[JobPosting]:
    """Search Google for LinkedIn job postings mentioning the domain.

    Best-effort. Returns empty list on search failure or no results.
    """
    from rrxray.services.firecrawl_client import FirecrawlError

    query = f'site:linkedin.com/jobs "{domain}"'
    try:
        results = await firecrawl.search(query, limit=10)
    except FirecrawlError as e:
        log.warning("LinkedIn jobs search failed for %s: %s", domain, e)
        return []

    roles: list[JobPosting] = []
    for r in results:
        title = r.title.strip()
        if not title:
            continue
        category, matched = _categorize_title(title)
        roles.append(JobPosting(
            title=title,
            category=category,  # type: ignore[arg-type]
            url=r.url or None,
            source="linkedin",
            matched_keyword=matched,
        ))
    return roles


_EMPLOYEE_COUNT_RE = re.compile(r"([\d,]+)\s+employees", re.IGNORECASE)


async def _linkedin_employee_count(firecrawl, domain: str) -> int | None:
    """Search Google for the LinkedIn company snippet and parse '<N> employees'.

    Returns int or None. Best-effort.
    """
    from rrxray.services.firecrawl_client import FirecrawlError

    query = f'"{domain}" employees site:linkedin.com/company'
    try:
        results = await firecrawl.search(query, limit=3)
    except FirecrawlError as e:
        log.warning("LinkedIn employee count search failed for %s: %s", domain, e)
        return None

    for r in results:
        haystack = " ".join([r.title, r.description])
        m = _EMPLOYEE_COUNT_RE.search(haystack)
        if m:
            try:
                return int(m.group(1).replace(",", ""))
            except ValueError:
                continue
    return None
```

- [ ] **Step 3: Run tests + ruff**

```bash
uv run pytest tests/test_revenue_motion.py -v
uv run ruff check rrxray/ tests/
```

Expected: 25 tests in this file (19 from T5-T6 + 6 from T7) all pass.

- [ ] **Step 4: Commit**

```bash
git add rrxray/collectors/revenue_motion.py tests/test_revenue_motion.py
git commit -m "Add LinkedIn search integration: job postings + employee count snippet"
```

---

## Task 8: Rule-based findings emission

**Files:**
- Modify: `rrxray/collectors/revenue_motion.py` (append `_compute_role_metrics`, `_emit_findings`)
- Modify: `tests/test_revenue_motion.py` (append findings tests)

- [ ] **Step 1: Append failing tests**

```python
def test_compute_role_metrics_basic():
    roles = [
        JobPosting(title="AE 1", category="ae", source="company_careers"),
        JobPosting(title="AE 2", category="ae", source="company_careers"),
        JobPosting(title="SDR 1", category="sdr", source="company_careers"),
    ]
    counts, ratio = revenue_motion._compute_role_metrics(roles)
    assert counts["ae"] == 2
    assert counts["sdr"] == 1
    assert ratio == 2.0


def test_compute_role_metrics_zero_sdr_returns_none_ratio():
    roles = [
        JobPosting(title="AE 1", category="ae", source="company_careers"),
        JobPosting(title="AE 2", category="ae", source="company_careers"),
    ]
    counts, ratio = revenue_motion._compute_role_metrics(roles)
    assert counts["ae"] == 2
    assert ratio is None


def test_compute_role_metrics_zero_ae_returns_none_ratio():
    roles = [
        JobPosting(title="SDR 1", category="sdr", source="company_careers"),
    ]
    counts, ratio = revenue_motion._compute_role_metrics(roles)
    assert ratio is None


def test_emit_findings_high_ae_to_sdr_ratio():
    roles = [
        JobPosting(title=f"AE {i}", category="ae", source="company_careers")
        for i in range(8)
    ] + [JobPosting(title="SDR 1", category="sdr", source="company_careers")]
    counts = {"ae": 8, "sdr": 1}
    findings, gaps, questions = revenue_motion._emit_findings(
        domain="acme.com", careers_url="https://acme.com/careers",
        roles=roles, counts=counts, ratio=8.0,
        employee_count=None, ats_platform=None,
    )
    finding_text = " ".join(f.text.lower() for f in findings) + " " + " ".join(gaps).lower()
    assert "ae" in finding_text or "sdr" in finding_text


def test_emit_findings_ae_without_sdr():
    roles = [
        JobPosting(title="AE 1", category="ae", source="company_careers"),
    ]
    counts = {"ae": 1, "sdr": 0}
    _findings, gaps, _questions = revenue_motion._emit_findings(
        domain="acme.com", careers_url="https://acme.com/careers",
        roles=roles, counts=counts, ratio=None,
        employee_count=None, ats_platform=None,
    )
    gap_text = " ".join(gaps).lower()
    assert "ae" in gap_text or "sdr" in gap_text or "founder" in gap_text


def test_emit_findings_sales_leadership_posted():
    roles = [
        JobPosting(title="VP of Sales", category="sales_leadership", source="company_careers"),
    ]
    counts = {"sales_leadership": 1}
    findings, _gaps, _q = revenue_motion._emit_findings(
        domain="acme.com", careers_url="https://acme.com/careers",
        roles=roles, counts=counts, ratio=None,
        employee_count=None, ats_platform=None,
    )
    finding_text = " ".join(f.text.lower() for f in findings)
    assert "leadership" in finding_text or "transition" in finding_text or "vp" in finding_text


def test_emit_findings_no_roles_emits_finding():
    findings, _gaps, _q = revenue_motion._emit_findings(
        domain="acme.com", careers_url=None,
        roles=[], counts={}, ratio=None,
        employee_count=None, ats_platform=None,
    )
    finding_text = " ".join(f.text.lower() for f in findings)
    assert "no" in finding_text and ("careers" in finding_text or "roles" in finding_text or "open" in finding_text)
```

- [ ] **Step 2: Append implementation to `rrxray/collectors/revenue_motion.py`**

```python
from datetime import UTC, datetime  # noqa: E402

from rrxray.schemas._shared import Finding, SourceCitation  # noqa: E402


def _compute_role_metrics(
    roles: list[JobPosting],
) -> tuple[dict[str, int], float | None]:
    """Aggregate role counts per category and compute AE/SDR ratio (None if either is 0)."""
    counts: dict[str, int] = {}
    for r in roles:
        counts[r.category] = counts.get(r.category, 0) + 1
    ae = counts.get("ae", 0)
    sdr = counts.get("sdr", 0)
    ratio: float | None = ae / sdr if (ae > 0 and sdr > 0) else None
    return counts, ratio


def _emit_findings(
    domain: str,
    careers_url: str | None,
    roles: list[JobPosting],
    counts: dict[str, int],
    ratio: float | None,
    employee_count: int | None,
    ats_platform: str | None,
) -> tuple[list[Finding], list[str], list[str]]:
    """Rule-based findings/gaps/questions. No LLM."""
    now = datetime.now(UTC)
    source_url = careers_url or f"https://{domain}"
    findings: list[Finding] = []
    gaps: list[str] = []
    questions: list[str] = []

    if not roles:
        findings.append(Finding(
            text=(
                f"No careers/jobs page or open roles discovered at standard paths "
                f"on {domain}. Either no current hiring activity or careers content "
                f"lives on a non-standard path or external surface."
            ),
            source=SourceCitation(url=source_url, timestamp=now),
        ))
        questions.append(
            "We did not find a public careers page or open roles. "
            "Are you actively hiring, and if so, where do you currently post roles? "
            "(Internal referral, executive recruiter, ATS-only, etc.)"
        )
        return findings, gaps, questions

    ae = counts.get("ae", 0)
    sdr = counts.get("sdr", 0)
    sales_leadership = counts.get("sales_leadership", 0)
    csm = counts.get("csm", 0)
    revops = counts.get("revops", 0)

    if ratio is not None and ratio >= 4.0:
        findings.append(Finding(
            text=(
                f"AE-to-SDR ratio is {ratio:.1f} ({ae} AEs hiring, {sdr} SDRs). "
                f"Outbound coverage looks under-resourced relative to AE capacity; "
                f"either pipeline is AE-self-sourced, founder-sourced, or pulled from "
                f"inbound demand alone."
            ),
            source=SourceCitation(url=source_url, timestamp=now),
        ))

    if ae > 0 and sdr == 0:
        gaps.append(
            f"Hiring {ae} AE{'s' if ae > 1 else ''} with zero SDRs in the open-role list. "
            "Top-of-funnel is either founder-led, AE-self-sourced, or assumed to come "
            "from inbound demand-gen — confirm which."
        )
        questions.append(
            "You're hiring AEs with no SDRs visible in the open requisitions. "
            "How are AEs sourcing pipeline today: outbound themselves, marketing-fed, "
            "or founder hand-offs?"
        )

    if sales_leadership > 0:
        findings.append(Finding(
            text=(
                f"Sales leadership role posted ({sales_leadership} open). The motion "
                "may be in transition — either the previous leader exited recently, "
                "or the company is scaling past founder-led sales."
            ),
            source=SourceCitation(url=source_url, timestamp=now),
        ))
        questions.append(
            "You're hiring sales leadership. What does the next 12 months look like "
            "for this role: rebuilding a function, scaling an existing one, or "
            "transitioning from founder-led sales?"
        )

    # Founding AE / first sales hire pattern
    founding_titles = [
        r for r in roles
        if any(token in r.title.lower() for token in ["founding", "first sales", "first ae"])
    ]
    if founding_titles:
        findings.append(Finding(
            text=(
                f"'{founding_titles[0].title}' role posted — motion is transitioning "
                "from founder-led sales to a first dedicated GTM hire."
            ),
            source=SourceCitation(url=source_url, timestamp=now),
        ))

    # Marketing leadership without marketing ops
    if counts.get("marketing_leadership", 0) > 0 and counts.get("marketing_ops", 0) == 0:
        gaps.append(
            "Marketing leadership posted but no marketing-ops role visible. "
            "Building a demand-gen function from scratch — pipeline visibility "
            "and attribution will be a question."
        )

    if revops == 0 and (ae > 0 or sdr > 0):
        gaps.append(
            "Hiring revenue-facing roles with no Revenue Operations role visible. "
            "Pipeline data, comp plans, and forecasting may be ad hoc or owned by sales leadership."
        )

    if csm == 0 and ae > 0:
        gaps.append(
            "AEs hiring with no Customer Success role posted. Post-sale ownership "
            "may be unclear — either AEs hold accounts, or CS is centralized and not currently expanding."
        )

    if ats_platform:
        findings.append(Finding(
            text=(
                f"Recruiting via {ats_platform}. The careers page redirects there "
                f"and that's the source of truth for open roles."
            ),
            source=SourceCitation(url=source_url, timestamp=now),
        ))

    if employee_count is not None:
        findings.append(Finding(
            text=(
                f"LinkedIn shows ~{employee_count} employees. "
                f"Open-role count: {len(roles)}. Hiring rate "
                f"({len(roles) / employee_count * 100:.1f}% of headcount) "
                f"signals {'aggressive growth' if len(roles) / employee_count > 0.05 else 'measured pace'}."
            ),
            source=SourceCitation(url="https://www.linkedin.com/company/" + domain.split('.')[0], timestamp=now),
        ))

    return findings, gaps, questions
```

- [ ] **Step 3: Run tests + ruff**

```bash
uv run pytest tests/test_revenue_motion.py -v
uv run ruff check rrxray/ tests/
```

Expected: 32 tests in this file (25 prior + 7 new) all pass.

- [ ] **Step 4: Commit**

```bash
git add rrxray/collectors/revenue_motion.py tests/test_revenue_motion.py
git commit -m "Add revenue_motion rule-based findings emission"
```

---

## Task 9: Evidence writing + collect() orchestration

**Files:**
- Modify: `rrxray/collectors/revenue_motion.py` (append `_write_evidence`, `collect`)
- Modify: `tests/test_revenue_motion.py` (append integration tests)

- [ ] **Step 1: Append failing tests**

```python
def test_collect_writes_evidence(tmp_path):
    ctx = _make_ctx(tmp_path, scrape_responses={
        "https://acme.com/careers": {
            "html": _load("careers_simple.html"),
            "markdown": "",
            "metadata": {"sourceURL": "https://acme.com/careers"},
        },
    })
    asyncio.run(revenue_motion.collect(ctx))
    evidence = tmp_path / "evidence" / "revenue_motion"
    assert (evidence / "careers.html").exists()


def test_collect_returns_revenue_motion_data(tmp_path):
    from rrxray.schemas.revenue_motion import RevenueMotionData

    ctx = _make_ctx(tmp_path, scrape_responses={
        "https://acme.com/careers": {
            "html": _load("careers_simple.html"),
            "markdown": "",
            "metadata": {"sourceURL": "https://acme.com/careers"},
        },
    }, search_responses={
        "site:linkedin.com/jobs": [
            {"url": "https://www.linkedin.com/jobs/view/123",
             "title": "Account Executive at Acme",
             "description": ""},
        ],
        "site:linkedin.com/company": [
            {"url": "https://www.linkedin.com/company/acme",
             "title": "Acme | LinkedIn",
             "description": "Acme · Software · 200 employees on LinkedIn"},
        ],
    })
    result = asyncio.run(revenue_motion.collect(ctx))
    assert isinstance(result, RevenueMotionData)
    assert result.careers_page_url == "https://acme.com/careers"
    assert len(result.open_roles) >= 3
    assert result.linkedin_employee_count == 200
    assert result.linkedin_job_count == 1


def test_collect_handles_no_careers_page(tmp_path):
    ctx = _make_ctx(tmp_path, scrape_responses={})
    result = asyncio.run(revenue_motion.collect(ctx))
    assert result.careers_page_url is None
    assert result.open_roles == []
    assert len(result.findings) >= 1


def test_collect_follows_ats_link(tmp_path):
    ctx = _make_ctx(tmp_path, scrape_responses={
        "https://acme.com/careers": {
            "html": _load("careers_with_ats_link.html"),
            "markdown": "",
            "metadata": {"sourceURL": "https://acme.com/careers"},
        },
        "https://jobs.lever.co/acme": {
            "html": _load("careers_simple.html"),  # reuse fixture for ATS content
            "markdown": "",
            "metadata": {"sourceURL": "https://jobs.lever.co/acme"},
        },
    })
    result = asyncio.run(revenue_motion.collect(ctx))
    assert result.ats_platform == "lever"
    assert any(r.source == "ats" for r in result.open_roles)


def test_source_citation_path_relative_to_evidence_dir(tmp_path):
    """SourceCitation.evidence_path must NOT start with 'evidence/' to avoid template double-prefix."""
    ctx = _make_ctx(tmp_path, scrape_responses={
        "https://acme.com/careers": {
            "html": _load("careers_simple.html"),
            "markdown": "",
            "metadata": {"sourceURL": "https://acme.com/careers"},
        },
    })
    result = asyncio.run(revenue_motion.collect(ctx))
    for source in result.sources:
        if source.evidence_path:
            assert not source.evidence_path.startswith("evidence/")
            assert source.evidence_path.startswith("revenue_motion/")
```

- [ ] **Step 2: Append implementation to `rrxray/collectors/revenue_motion.py`**

```python
import json  # noqa: E402
from pathlib import Path  # noqa: E402

from rrxray.schemas.revenue_motion import RevenueMotionData  # noqa: E402


def _write_evidence(
    evidence_dir: Path,
    careers_html: str,
    ats_html: str | None,
    linkedin_jobs: list,
    linkedin_employee_count: int | None,
) -> None:
    """Write raw HTML + LinkedIn search results to evidence dir."""
    evidence_dir.mkdir(parents=True, exist_ok=True)
    # Clean stale evidence from prior runs
    for stale in evidence_dir.glob("*.html"):
        stale.unlink()
    for stale in evidence_dir.glob("*.json"):
        stale.unlink()

    if careers_html:
        (evidence_dir / "careers.html").write_text(careers_html, encoding="utf-8")
    if ats_html:
        (evidence_dir / "ats.html").write_text(ats_html, encoding="utf-8")
    (evidence_dir / "linkedin_jobs.json").write_text(
        json.dumps([j.model_dump() for j in linkedin_jobs], indent=2),
        encoding="utf-8",
    )
    (evidence_dir / "linkedin_employee_count.json").write_text(
        json.dumps({"count": linkedin_employee_count}, indent=2),
        encoding="utf-8",
    )


async def collect(ctx) -> RevenueMotionData:
    """Discover careers page, scrape it (and ATS if linked), search LinkedIn, emit findings."""
    from rrxray.services.firecrawl_client import FirecrawlError

    now = datetime.now(UTC)

    # Discover careers page
    careers_url, careers_page = await _discover_careers_url(ctx)
    careers_html = (careers_page.html if careers_page else "") or ""

    # Detect ATS link in careers page HTML
    ats_platform: str | None = None
    ats_url: str | None = None
    ats_html: str | None = None
    if careers_html:
        ats_platform, ats_url = _detect_ats(careers_html)
        if ats_url:
            try:
                ats_page = await ctx.firecrawl.scrape_url(ats_url, only_main_content=False)
                ats_html = ats_page.html or ""
            except FirecrawlError as e:
                log.warning("ATS scrape failed for %s: %s", ats_url, e)
                ats_html = None

    # Extract roles from careers page + ATS page
    base_url = f"https://{ctx.domain}"
    careers_roles = _extract_roles(careers_html, source="company_careers", base_url=base_url)
    ats_roles = _extract_roles(ats_html or "", source="ats", base_url=ats_url or base_url)
    company_roles = careers_roles + ats_roles

    # Search LinkedIn
    linkedin_roles = await _linkedin_search_jobs(ctx.firecrawl, ctx.domain)
    linkedin_employee_count = await _linkedin_employee_count(ctx.firecrawl, ctx.domain)

    # Combine all roles for metrics; per-source counts surface in findings
    all_roles = company_roles + linkedin_roles
    role_counts, ratio = _compute_role_metrics(all_roles)

    # Findings
    findings, gaps, questions = _emit_findings(
        domain=ctx.domain,
        careers_url=careers_url,
        roles=all_roles,
        counts=role_counts,
        ratio=ratio,
        employee_count=linkedin_employee_count,
        ats_platform=ats_platform,
    )

    # Evidence
    _write_evidence(
        ctx.evidence_dir / NAME,
        careers_html,
        ats_html,
        linkedin_roles,
        linkedin_employee_count,
    )

    # Source citations
    sources = []
    if careers_url:
        sources.append(SourceCitation(
            url=careers_url, timestamp=now,
            evidence_path=str(
                (ctx.evidence_dir / NAME / "careers.html").relative_to(ctx.evidence_dir)
            ),
        ))
    if ats_url:
        sources.append(SourceCitation(
            url=ats_url, timestamp=now,
            evidence_path=str(
                (ctx.evidence_dir / NAME / "ats.html").relative_to(ctx.evidence_dir)
            ) if ats_html else None,
        ))

    return RevenueMotionData(
        careers_page_url=careers_url,
        ats_platform=ats_platform,
        open_roles=all_roles,
        role_counts=role_counts,
        ae_to_sdr_ratio=ratio,
        linkedin_employee_count=linkedin_employee_count,
        linkedin_job_count=len(linkedin_roles) if linkedin_roles else (None if not linkedin_roles else 0),
        findings=findings,
        gaps=gaps,
        discovery_questions=questions,
        sources=sources,
    )
```

- [ ] **Step 3: Run tests + full suite + ruff**

```bash
uv run pytest tests/test_revenue_motion.py -v
uv run pytest -v 2>&1 | tail -3
uv run ruff check rrxray/ tests/
```

Expected: 37 tests in `test_revenue_motion.py` all pass; full suite around 230 passed, 1 skipped.

- [ ] **Step 4: Commit**

```bash
git add rrxray/collectors/revenue_motion.py tests/test_revenue_motion.py
git commit -m "Wire revenue_motion collect() with evidence + graceful error handling"
```

---

## Task 10: Renderer template + integration

**Files:**
- Create: `templates/_revenue_motion_detail.md.jinja`
- Modify: `templates/report_internal.md.jinja` (include the new partial)
- Modify: `tests/test_render_internal.py` (append render tests)

- [ ] **Step 1: Append failing tests to `tests/test_render_internal.py`**

```python
def test_revenue_motion_module_detail_renders():
    from rrxray.schemas.revenue_motion import JobPosting, RevenueMotionData

    rm = RevenueMotionData(
        careers_page_url="https://example.com/careers",
        ats_platform="lever",
        open_roles=[
            JobPosting(title="Senior AE", category="ae", source="company_careers"),
            JobPosting(title="SDR", category="sdr", source="company_careers"),
        ],
        role_counts={"ae": 1, "sdr": 1},
        ae_to_sdr_ratio=1.0,
        linkedin_employee_count=247,
    )
    data = make_data()
    data.collectors.revenue_motion = rm
    out = render_internal(data, Anonymizer(), VoicePostProcessor())
    assert "### Revenue Motion" in out
    assert "Senior AE" in out
    assert "lever" in out.lower()
    assert "247" in out


def test_revenue_motion_module_detail_omits_when_no_collector():
    data = make_data()
    out = render_internal(data, Anonymizer(), VoicePostProcessor())
    assert "### Revenue Motion" not in out
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_render_internal.py -v -k revenue_motion
```

Expected: 2 new tests fail.

- [ ] **Step 3: Create `templates/_revenue_motion_detail.md.jinja`**

```jinja
{% set rm = data.collectors.revenue_motion %}
**Careers page:** {{ rm.careers_page_url or "not found" }}
**ATS platform:** {{ rm.ats_platform or "not detected" }}
**Open roles:** {{ rm.open_roles | length }}

{% if rm.role_counts %}
| Category | Count |
|---|---|
{% for category, count in rm.role_counts.items() %}
| {{ category }} | {{ count }} |
{% endfor %}
{% endif %}

**AE-to-SDR ratio:** {{ "%.1f" | format(rm.ae_to_sdr_ratio) if rm.ae_to_sdr_ratio is not none else "n/a (zero in one or both)" }}
**LinkedIn employee count:** {{ rm.linkedin_employee_count if rm.linkedin_employee_count is not none else "not detected" }}
**LinkedIn job postings:** {{ rm.linkedin_job_count if rm.linkedin_job_count is not none else "not detected" }}

{% if rm.open_roles %}
**Open roles:**

{% for role in rm.open_roles[:20] %}
- [{{ role.category }}] {{ role.title | voice_collector }}{% if role.location %} ({{ role.location }}){% endif %}{% if role.source != "company_careers" %} (source: {{ role.source }}){% endif %}
{% endfor %}
{% endif %}

{% if rm.findings %}
**Findings:**

{% for f in rm.findings %}
- {{ f.text | voice_collector }} *(source: [{{ f.source.url }}]({{ f.source.url }}))*
{% endfor %}
{% endif %}

{% if rm.gaps %}
**Gaps:**
{% for g in rm.gaps %}
→ {{ g | voice_collector }}
{% endfor %}
{% endif %}

{% if rm.discovery_questions %}
**Discovery questions:**
{% for q in rm.discovery_questions %}
- {{ q }}
{% endfor %}
{% endif %}
```

- [ ] **Step 4: Modify `templates/report_internal.md.jinja`**

Find the Module Detail Appendix section, after the Tech Stack conditional block. Add:

```jinja
{% if data.collectors.revenue_motion %}
### Revenue Motion

{% include "_revenue_motion_detail.md.jinja" %}
{% endif %}
```

- [ ] **Step 5: Run tests + ruff**

```bash
uv run pytest tests/test_render_internal.py -v
uv run ruff check rrxray/ tests/
```

Expected: 2 new render tests pass; all existing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add templates/_revenue_motion_detail.md.jinja templates/report_internal.md.jinja tests/test_render_internal.py
git commit -m "Add Revenue Motion subsection to Module Detail Appendix"
```

---

## Task 11: Synthesizer prompt + body update

**Files:**
- Modify: `rrxray/synthesizers/observed_gtm_motion.py` (read revenue_motion + pass to prompt)
- Modify: `rrxray/prompts/observed_gtm_motion.md` (add framework guidance + third conditional block)
- Modify: `tests/test_synthesizer_observed_gtm_motion.py` (append three-collector test)

- [ ] **Step 1: Append failing test to `tests/test_synthesizer_observed_gtm_motion.py`**

```python
def test_synth_runs_with_three_collectors():
    """When all three Section A collectors are present, all three blocks render in the user message."""
    from rrxray.schemas.revenue_motion import JobPosting, RevenueMotionData
    pricing = PricingPackagingData(
        has_public_pricing=True, is_contact_us_gated=False,
        current_pricing_url="https://example.com/pricing",
        current_tiers=[PricingTier(name="Pro", price="$50", cadence="month")],
    )
    tech = TechStackData(
        detected_tools=[DetectedTool(
            name="HubSpot", category="marketing_automation", confidence="high",
            signature_id="hubspot:strict_js", matched_text="x",
        )],
        categories_observed=["marketing_automation"],
        categories_absent=["analytics", "tag_manager", "chat", "product_analytics",
                           "crm", "cdp", "ab_testing", "attribution"],
    )
    rm = RevenueMotionData(
        careers_page_url="https://example.com/careers",
        ats_platform="lever",
        open_roles=[
            JobPosting(title="Senior AE", category="ae", source="company_careers"),
            JobPosting(title="SDR", category="sdr", source="company_careers"),
        ],
        role_counts={"ae": 1, "sdr": 1},
        ae_to_sdr_ratio=1.0,
        linkedin_employee_count=247,
        linkedin_job_count=3,
    )

    fake_anthropic = MagicMock()
    fake_anthropic.complete_with_cached_system = AsyncMock(
        return_value=make_anthropic_response(
            ["Three-signal narrative."],
            ["Multi-signal observation"],
        ),
    )
    config = MagicMock(domain="example.com", model="claude-sonnet-4-6")
    config.evidence_dir = MagicMock()
    ctx = SynthesizerContext(
        collector_outputs=CollectorOutputs(
            pricing_packaging=pricing,
            tech_stack=tech,
            revenue_motion=rm,
        ),
        anthropic=fake_anthropic,
        voice=VoicePostProcessor(),
        anonymizer=Anonymizer(),
        config=config,
    )

    result = asyncio.run(observed_gtm_motion.synthesize(ctx))
    assert result is not None
    user_msg = ctx.anthropic.complete_with_cached_system.call_args.kwargs["user_message"]
    assert "Pricing & Packaging signal" in user_msg
    assert "Tech Stack signal" in user_msg
    assert "Revenue Motion signal" in user_msg
    assert "Senior AE" in user_msg
    assert "lever" in user_msg.lower()
    assert "247" in user_msg
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_synthesizer_observed_gtm_motion.py -v -k three_collectors
```

Expected: fails because the prompt template has no "Revenue Motion signal" block yet.

- [ ] **Step 3: Modify `rrxray/synthesizers/observed_gtm_motion.py`**

Update the `synthesize()` function to read `revenue_motion` from collector outputs and pass it to the user-message renderer:

```python
async def synthesize(ctx: SynthesizerContext) -> ObservedGtmMotionNarrative | None:
    pricing = ctx.collector_outputs.pricing_packaging
    tech_stack = ctx.collector_outputs.tech_stack
    revenue_motion = ctx.collector_outputs.revenue_motion    # NEW

    # Skip only when ALL Section A collectors absent
    if pricing is None and tech_stack is None and revenue_motion is None:
        log.info("All Section A collectors absent; skipping observed_gtm_motion synthesis")
        return None

    # Read raw page excerpts from evidence (truncated to keep prompt size sane)
    raw_pricing_text = _read_evidence_text(
        ctx, "pricing_packaging/current.md", max_chars=3000,
    ) if pricing else ""
    raw_homepage_text = _read_evidence_text(
        ctx, "tech_stack/homepage.html", max_chars=3000,
    ) if tech_stack else ""

    system_prompt = _load_system_prompt()
    user_message = _render_user_message(
        ctx.config.domain, pricing, tech_stack, revenue_motion,    # NEW arg
        raw_pricing_text=raw_pricing_text,
        raw_homepage_text=raw_homepage_text,
    )

    # ... rest unchanged ...
```

Update `_render_user_message` signature to accept revenue_motion:

```python
def _render_user_message(
    domain: str,
    pricing,
    tech_stack,
    revenue_motion,    # NEW
    raw_pricing_text: str = "",
    raw_homepage_text: str = "",
) -> str:
    template_text = files("rrxray.prompts").joinpath("observed_gtm_motion.md").read_text()
    env = Environment(trim_blocks=True, lstrip_blocks=True)
    return env.from_string(template_text).render(
        domain=domain,
        pricing=pricing,
        tech_stack=tech_stack,
        revenue_motion=revenue_motion,    # NEW
        raw_pricing_text=raw_pricing_text,
        raw_homepage_text=raw_homepage_text,
    )
```

- [ ] **Step 4: Modify `rrxray/prompts/observed_gtm_motion.md`**

Find the framework guidance section. After the "Tech stack tells you" subsection, add:

```markdown
**Revenue motion (hiring shape) tells you:**

- AE/SDR ratio > 4 = outbound under-resourced relative to AE coverage; pipeline likely AE-self-sourced or founder-led
- AE count > 0 + SDR count == 0 = top of funnel is founder/AE responsibility; signals early-stage or recently-shifted motion
- "First sales hire" / "Founding AE" titles = motion still founder-led, transitioning
- "Enterprise AE" titles = upmarket positioning regardless of pricing
- VP Sales / CRO / Head of Revenue posted = motion in transition (current leader gone or company growing)
- Marketing leadership posted with no marketing ops = building demand-gen function from scratch
- LinkedIn job count significantly different from careers page count = channel-specific recruiting
```

After the Tech Stack signal block (and before "Raw pricing page excerpt"), add:

```jinja
{% if revenue_motion %}
**Revenue Motion signal**

- Careers page: {{ revenue_motion.careers_page_url or "not found" }}
- ATS platform: {{ revenue_motion.ats_platform or "not detected" }}
- Total open roles: {{ revenue_motion.open_roles | length }}

Role counts by category:
{% for category, count in revenue_motion.role_counts.items() %}
- {{ category }}: {{ count }}
{% endfor %}

AE-to-SDR ratio: {{ "%.1f" | format(revenue_motion.ae_to_sdr_ratio) if revenue_motion.ae_to_sdr_ratio is not none else "n/a (zero in one or both)" }}
LinkedIn employee count: {{ revenue_motion.linkedin_employee_count if revenue_motion.linkedin_employee_count is not none else "not detected" }}
LinkedIn job postings on LinkedIn Jobs: {{ revenue_motion.linkedin_job_count if revenue_motion.linkedin_job_count is not none else "not detected" }}

Specific roles open right now (up to 15):
{% for role in revenue_motion.open_roles[:15] %}
- [{{ role.category }}] {{ role.title }}{% if role.location %} ({{ role.location }}){% endif %}{% if role.source != "company_careers" %} (source: {{ role.source }}){% endif %}
{% endfor %}

Findings from the collector:
{% if revenue_motion.findings %}
{% for f in revenue_motion.findings %}
- {{ f.text }}
{% endfor %}
{% else %}
(none)
{% endif %}
{% else %}
**Revenue Motion signal:** not collected.
{% endif %}
```

- [ ] **Step 5: Run tests + ruff**

```bash
uv run pytest tests/test_synthesizer_observed_gtm_motion.py -v
uv run ruff check rrxray/ tests/
```

Expected: all synthesizer tests pass including the new `test_synth_runs_with_three_collectors`.

- [ ] **Step 6: Commit**

```bash
git add rrxray/synthesizers/observed_gtm_motion.py rrxray/prompts/observed_gtm_motion.md tests/test_synthesizer_observed_gtm_motion.py
git commit -m "Wire Section A synthesizer to read revenue_motion as third signal

Adds Revenue Motion conditional block to the prompt template and the
framework guidance for hiring-shape signal interpretation. Synthesizer
body adds one line to read revenue_motion from collector_outputs and
pass to the user-message renderer."
```

---

## Task 12: Pipeline registration + quality gate

**Files:**
- Modify: `rrxray/pipeline.py` (append `revenue_motion` to COLLECTORS)
- Modify: `tests/test_pipeline_graceful_degradation.py` (one new regression test)
- Possibly: `rrxray/prompts/observed_gtm_motion.md` (iterations from Dale review)

This task ends with a Dale-led quality gate. The implementer subagent runs the smoke and presents output for human review; iteration cycles continue until quality passes.

- [ ] **Step 1: Append regression test to `tests/test_pipeline_graceful_degradation.py`**

```python
def test_pipeline_runs_with_three_section_a_collectors(tmp_path, monkeypatch):
    """Pipeline orchestrator passes all three Section A collectors into the synthesizer context."""
    from rrxray.schemas.tech_stack import DetectedTool, TechStackData
    from rrxray.schemas.revenue_motion import JobPosting, RevenueMotionData

    config = fake_config(tmp_path)

    fake_pricing = MagicMock()
    fake_pricing.NAME = "pricing_packaging"
    async def pricing_collect(ctx):
        from rrxray.schemas.pricing_packaging import PricingPackagingData
        return PricingPackagingData(
            has_public_pricing=True, is_contact_us_gated=False,
            current_pricing_url="https://example.com/pricing",
        )
    fake_pricing.collect = pricing_collect

    fake_tech_stack = MagicMock()
    fake_tech_stack.NAME = "tech_stack"
    async def tech_collect(ctx):
        return TechStackData(
            detected_tools=[DetectedTool(
                name="HubSpot", category="marketing_automation", confidence="high",
                signature_id="hubspot:strict_js", matched_text="x",
            )],
            categories_observed=["marketing_automation"],
            categories_absent=["analytics", "tag_manager", "chat", "product_analytics",
                               "crm", "cdp", "ab_testing", "attribution"],
        )
    fake_tech_stack.collect = tech_collect

    fake_revenue_motion = MagicMock()
    fake_revenue_motion.NAME = "revenue_motion"
    async def rm_collect(ctx):
        return RevenueMotionData(
            careers_page_url="https://example.com/careers",
            open_roles=[JobPosting(title="AE", category="ae", source="company_careers")],
            role_counts={"ae": 1},
        )
    fake_revenue_motion.collect = rm_collect

    fake_synth = MagicMock()
    fake_synth.NAME = "observed_gtm_motion"

    captured_ctx = {}
    async def synth_capture(ctx):
        captured_ctx["pricing"] = ctx.collector_outputs.pricing_packaging
        captured_ctx["tech_stack"] = ctx.collector_outputs.tech_stack
        captured_ctx["revenue_motion"] = ctx.collector_outputs.revenue_motion
        return None
    fake_synth.synthesize = synth_capture

    monkeypatch.setattr(pipeline, "COLLECTORS", [fake_pricing, fake_tech_stack, fake_revenue_motion])
    monkeypatch.setattr(pipeline, "SYNTHESIZERS", [fake_synth])
    monkeypatch.setattr(pipeline, "build_collector_context", lambda c: MagicMock())
    monkeypatch.setattr(
        pipeline, "build_synthesizer_context",
        lambda c, o, v, a: MagicMock(collector_outputs=o, voice=v, anonymizer=a, config=c),
    )

    asyncio.run(pipeline.run_pipeline(config))
    assert captured_ctx["pricing"] is not None
    assert captured_ctx["tech_stack"] is not None
    assert captured_ctx["revenue_motion"] is not None
    assert captured_ctx["revenue_motion"].open_roles[0].title == "AE"
```

- [ ] **Step 2: Modify `rrxray/pipeline.py`**

Update the import line and COLLECTORS list:

```python
from rrxray.collectors import pricing_packaging, tech_stack, revenue_motion

COLLECTORS = [pricing_packaging, tech_stack, revenue_motion]
```

- [ ] **Step 3: Run full test suite + ruff**

```bash
uv run pytest -v 2>&1 | tail -10
uv run ruff check rrxray/ tests/
```

Expected: all tests pass (around 232 passed, 1 skipped). Ruff clean.

- [ ] **Step 4: Commit**

```bash
git add rrxray/pipeline.py tests/test_pipeline_graceful_degradation.py
git commit -m "Register revenue_motion in pipeline COLLECTORS list"
```

- [ ] **Step 5: Live smoke run against three domains**

```bash
unset ANTHROPIC_API_KEY FIRECRAWL_API_KEY
uv run rrxray run --domain swayable.com --no-cache 2>&1 | tail -3
uv run rrxray run --domain sqaservices.com --no-cache 2>&1 | tail -3
uv run rrxray run --domain linear.app --no-cache 2>&1 | tail -3
```

- [ ] **Step 6: Extract Section A from each rendered report**

```bash
for d in swayable-com sqaservices-com linear-app; do
  echo "================================================================"
  echo "=== $d Section A (with revenue_motion) ==="
  echo "================================================================"
  awk '/## 2\. Section A/,/## 3\./' /Users/dalezwizinski/Documents/Apps/rrxray/xray-$d-*/report.internal.md
  echo ""
done
```

Present all three Section A outputs to Dale for quality review.

- [ ] **Step 7: Dale-led quality review**

Dale reads each Section A and calls out:
- Whether revenue_motion data integrates meaningfully into the cross-signal narrative
- Phrases that read AI-generated rather than RR-authored
- Discovery questions that miss the mark or feel boilerplate
- Findings that lack specificity
- Cross-signal reasoning gaps (does revenue_motion actually inform the narrative or just sit alongside?)

- [ ] **Step 8: Iterate the prompt based on Dale's feedback**

If quality issues surface:
1. Identify which prompt section needs sharpening (framework guidance, signal blocks, "your task" instruction)
2. Modify `rrxray/prompts/observed_gtm_motion.md`
3. Re-run smoke (`uv run rrxray run --domain X --no-cache`)
4. Present new output
5. Repeat until Dale signs off

- [ ] **Step 9: Commit prompt iterations**

After each prompt edit:

```bash
git add rrxray/prompts/observed_gtm_motion.md
git commit -m "Tune Section A prompt for revenue_motion integration: <one-line description>"
```

- [ ] **Step 10: Phase 2.1c checkpoint**

Per `CLAUDE.md`, write `docs/checkpoints/2026-05-07-phase-2.1c-revenue-motion-checkpoint.md` capturing final state, quality-gate iteration count, smoke summary, and what's queued next (Phase 2.1d content_demand collector or other).

```bash
git add docs/checkpoints/2026-05-07-phase-2.1c-revenue-motion-checkpoint.md
git commit -m "Add Phase 2.1c revenue_motion checkpoint"
```

---

## Self-Review

### Spec coverage check

| Spec section | Plan task |
|---|---|
| FirecrawlClient.search() extension | T1 |
| RevenueMotionData / JobPosting schemas | T2 |
| CollectorOutputs.revenue_motion field | T3 |
| Role catalog with 8 categories | T4 |
| ATS pattern catalog | T4 |
| Careers URL discovery (4 paths) | T5 |
| ATS link follow (Lever / Greenhouse / Ashby / Workable) | T5 + T9 |
| HTML role extraction with categorization | T6 |
| LinkedIn job posting search | T7 |
| LinkedIn employee count snippet | T7 |
| Rule-based findings emission (no LLM in collector) | T8 |
| Evidence writing | T9 |
| collect() orchestration with graceful failure handling | T9 |
| Module Detail Appendix subsection | T10 |
| Synthesizer prompt third conditional block | T11 |
| Synthesizer body reads revenue_motion | T11 |
| Synthesizer test for three-collector path | T11 |
| Pipeline registration | T12 |
| Pipeline regression test for three collectors | T12 |
| Live smoke + Dale-led quality gate | T12 |
| Phase 2.1c checkpoint | T12 |

### Acceptance criteria coverage

| AC | Plan task |
|---|---|
| #1 collector registered | T12 |
| #2 search() works | T1 |
| #3 catalog has 8 categories with keywords | T4 |
| #4 careers URL discovery | T5 |
| #5 ATS detection | T5 |
| #6 role extraction | T6 |
| #7 LinkedIn search | T7 |
| #8 rule-based findings | T8 |
| #9 evidence files | T9 |
| #10 data.json round-trip | T3 |
| #11 Module Detail renders | T10 |
| #12 synthesizer reads revenue_motion | T11 |
| #13 live smoke produces hiring-shape narrative | T12 |
| #14 quality gate sign-off | T12 |

### Type / signature consistency check

- `_categorize_title(title) -> tuple[str, str | None]` defined T6, used T7
- `_extract_roles(html, source, base_url) -> list[JobPosting]` defined T6, used T9
- `_compute_role_metrics(roles) -> tuple[dict[str, int], float | None]` defined T8, used T9
- `_emit_findings(domain, careers_url, roles, counts, ratio, employee_count, ats_platform)` defined T8, used T9
- `_linkedin_search_jobs(firecrawl, domain) -> list[JobPosting]` defined T7, used T9
- `_linkedin_employee_count(firecrawl, domain) -> int | None` defined T7, used T9
- `collect(ctx) -> RevenueMotionData` defined T9, used T12
- `RevenueMotionData` fields defined T2, used T9, T10, T11
- `FirecrawlClient.search(query, limit) -> list[SearchResult]` defined T1, used T7
- `RoleCategory` Literal defined T2, used T6, T7

### Placeholder scan

Searched for: TBD, TODO, "implement later", "fill in", "add appropriate", "similar to". None found.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-07-rrxray-phase-2.1c-revenue-motion.md`. Two execution options:

**1. Subagent-Driven (recommended)** — fresh subagent per task, two-stage review for T1-T11, then T12 stops to ask Dale for the quality read.

**2. Inline Execution** — `superpowers:executing-plans` with batch checkpoints. Every diff lands in this session.

Which approach?
