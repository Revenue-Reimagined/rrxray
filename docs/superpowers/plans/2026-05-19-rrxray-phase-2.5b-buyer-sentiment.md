# Phase 2.5b: buyer_sentiment Collector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `buyer_sentiment` collector that searches G2, Capterra, Trustpilot, Reddit, and Glassdoor for public review signals, extracts themes via Haiku 4.5 LLM, and returns structured `BuyerSentimentData` — enforcing Verbatim Quarantine so raw review text never surfaces outside evidence files.

**Architecture:** Five-platform search via Firecrawl, optional scrape for G2/Trustpilot, Haiku LLM for per-platform theme extraction (unstructured NL justifies LLM per Phase 2.2 precedent), rule-based theme merging and findings. Verbatim Quarantine: all raw text writes to `evidence/buyer_sentiment/raw/<platform>.txt`; the schema holds extracted themes only. Glassdoor themes route to `sales_rep_themes` field. Collector runs concurrently with asyncio.gather. Graceful degradation on every FirecrawlError.

**Tech Stack:** Python 3.12, Pydantic v2, asyncio, Firecrawl search + scrape, Anthropic Haiku 4.5 (structured output via `complete_with_cached_system`), pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-05-17-rrxray-section-c-design.md` (Phase 2.5b section)

**Model assignments (CLAUDE.md matrix):**
- Tasks 1, 2, 7, 8: **Haiku 4.5** (mechanical schema / wiring)
- Tasks 3, 4, 5, 6: **Opus 4.7** (real logic: LLM extraction, concurrent orchestration, theme merging, rule-based findings)

---

## File Structure

| Path | Action | Responsibility |
|---|---|---|
| `rrxray/schemas/buyer_sentiment.py` | Create | `ReviewTheme` + `BuyerSentimentData` schemas |
| `rrxray/collectors/_buyer_sentiment_catalog.py` | Create | Constants + `build_platform_queries()` |
| `rrxray/services/extraction.py` | Modify | Add `ExtractedTheme`, `ExtractedSentimentThemes`, `HaikuExtractor.extract_sentiment_themes`, `GeminiFlashExtractor.extract_sentiment_themes` |
| `rrxray/collectors/buyer_sentiment.py` | Create | All collector functions + `collect()` |
| `rrxray/schemas/data.py` | Modify | Add `CollectorOutputs.buyer_sentiment` forward ref + bottom import + `model_rebuild()` (same pattern as positioning_drift) |
| `rrxray/pipeline.py` | Modify | Import `buyer_sentiment` + append to `COLLECTORS` |
| `templates/_buyer_sentiment_detail.md.jinja` | Create | Module Detail partial |
| `templates/report_internal.md.jinja` | Modify | Add buyer_sentiment include block after positioning_drift block |
| `tests/test_buyer_sentiment_schemas.py` | Create | Schema shape tests |
| `tests/test_buyer_sentiment_catalog.py` | Create | Catalog constants + query builder tests |
| `tests/test_extraction.py` | Modify | Add `extract_sentiment_themes` tests |
| `tests/test_buyer_sentiment.py` | Create | Collector helper + orchestrator tests |
| `tests/test_schemas.py` | Modify | Add `CollectorOutputs.buyer_sentiment` field test |
| `tests/test_pipeline.py` | Modify | Add `buyer_sentiment` in COLLECTORS test |
| `tests/test_render_internal.py` | Modify | Add buyer_sentiment render test |

---

### Task 1: BuyerSentimentData schemas

**Model: Haiku 4.5 (mechanical schema)**

**Files:**
- Create: `rrxray/schemas/buyer_sentiment.py`
- Create: `tests/test_buyer_sentiment_schemas.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_buyer_sentiment_schemas.py
"""Tests for buyer_sentiment schemas."""
from __future__ import annotations

import pytest

from rrxray.schemas.buyer_sentiment import BuyerSentimentData, ReviewTheme


def test_review_theme_defaults():
    t = ReviewTheme(theme="slow onboarding", sentiment="negative", source_platforms=["g2"], frequency="single")
    assert t.theme == "slow onboarding"
    assert t.sentiment == "negative"
    assert t.source_platforms == ["g2"]
    assert t.frequency == "single"


def test_review_theme_rejects_invalid_sentiment():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ReviewTheme(theme="x", sentiment="unknown", source_platforms=[], frequency="single")


def test_review_theme_rejects_invalid_frequency():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ReviewTheme(theme="x", sentiment="positive", source_platforms=[], frequency="always")


def test_buyer_sentiment_data_defaults():
    d = BuyerSentimentData()
    assert d.platforms_checked == []
    assert d.platforms_found == []
    assert d.review_count_estimate is None
    assert d.themes == []
    assert d.sales_rep_themes == []
    assert d.findings == []
    assert d.gaps == []
    assert d.discovery_questions == []
    assert d.sources == []


def test_buyer_sentiment_data_with_themes():
    t = ReviewTheme(theme="easy setup", sentiment="positive", source_platforms=["g2", "capterra"], frequency="dominant")
    d = BuyerSentimentData(
        platforms_checked=["g2", "capterra"],
        platforms_found=["g2"],
        themes=[t],
    )
    assert len(d.themes) == 1
    assert d.themes[0].frequency == "dominant"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=. uv run pytest tests/test_buyer_sentiment_schemas.py -v
```
Expected: `ImportError` or `ModuleNotFoundError` (module doesn't exist yet).

- [ ] **Step 3: Create the schemas file**

```python
# rrxray/schemas/buyer_sentiment.py
"""Schemas for the buyer_sentiment collector."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from rrxray.schemas._shared import Finding, SourceCitation


class ReviewTheme(BaseModel):
    theme: str
    sentiment: Literal["positive", "negative", "mixed"]
    source_platforms: list[str]
    frequency: Literal["single", "repeated", "dominant"]


class BuyerSentimentData(BaseModel):
    platforms_checked: list[str] = []
    platforms_found: list[str] = []
    review_count_estimate: int | None = None
    themes: list[ReviewTheme] = []
    sales_rep_themes: list[ReviewTheme] = []  # Glassdoor ex-AE/SDR specific
    findings: list[Finding] = []
    gaps: list[str] = []
    discovery_questions: list[str] = []
    sources: list[SourceCitation] = []
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
PYTHONPATH=. uv run pytest tests/test_buyer_sentiment_schemas.py -v
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add rrxray/schemas/buyer_sentiment.py tests/test_buyer_sentiment_schemas.py
git commit -m "feat(2.5b): BuyerSentimentData + ReviewTheme schemas"
```

---

### Task 2: Catalog constants and query builder

**Model: Haiku 4.5 (mechanical)**

**Files:**
- Create: `rrxray/collectors/_buyer_sentiment_catalog.py`
- Create: `tests/test_buyer_sentiment_catalog.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_buyer_sentiment_catalog.py
"""Tests for buyer_sentiment catalog constants."""
from __future__ import annotations

from rrxray.collectors._buyer_sentiment_catalog import (
    MAX_RAW_CHARS,
    MAX_SEARCH_RESULTS,
    QUARANTINE_PLATFORMS,
    SCRAPED_PLATFORMS,
    build_platform_queries,
)


def test_constants_present():
    assert isinstance(MAX_RAW_CHARS, int)
    assert MAX_RAW_CHARS >= 2000
    assert isinstance(MAX_SEARCH_RESULTS, int)
    assert MAX_SEARCH_RESULTS >= 3


def test_scraped_platforms_subset_of_quarantine():
    assert SCRAPED_PLATFORMS.issubset(QUARANTINE_PLATFORMS)


def test_quarantine_covers_all_five_platforms():
    assert {"g2", "capterra", "trustpilot", "reddit", "glassdoor"}.issubset(QUARANTINE_PLATFORMS)


def test_build_platform_queries_all_five_keys():
    queries = build_platform_queries("example.com", "Example Inc")
    assert set(queries.keys()) == {"g2", "capterra", "trustpilot", "reddit", "glassdoor"}


def test_build_platform_queries_domain_in_queries():
    queries = build_platform_queries("acme.com", None)
    for q in queries.values():
        assert "acme" in q.lower() or "acme.com" in q.lower()


def test_build_platform_queries_company_name_used_when_provided():
    queries = build_platform_queries("acme.com", "Acme Corp")
    assert "Acme Corp" in queries["g2"] or "Acme Corp" in queries["capterra"]


def test_build_platform_queries_falls_back_to_domain_when_no_name():
    queries = build_platform_queries("acme.com", None)
    assert "acme.com" in queries["g2"] or "acme" in queries["g2"].lower()


def test_glassdoor_query_contains_sales_signal():
    queries = build_platform_queries("acme.com", None)
    assert "sales" in queries["glassdoor"].lower() or "glassdoor" in queries["glassdoor"].lower()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=. uv run pytest tests/test_buyer_sentiment_catalog.py -v
```
Expected: `ImportError`.

- [ ] **Step 3: Create the catalog file**

```python
# rrxray/collectors/_buyer_sentiment_catalog.py
"""Constants for the buyer_sentiment collector."""
from __future__ import annotations

MAX_RAW_CHARS = 4000  # max chars of combined raw text sent to LLM per platform
MAX_SEARCH_RESULTS = 5  # search results to fetch per platform

# Platforms where we attempt to scrape the top search result (not just snippets)
SCRAPED_PLATFORMS: set[str] = {"g2", "trustpilot"}

# All platforms subject to Verbatim Quarantine: raw text -> evidence/raw/ only
QUARANTINE_PLATFORMS: set[str] = {"g2", "capterra", "trustpilot", "reddit", "glassdoor"}


def build_platform_queries(domain: str, company_name: str | None = None) -> dict[str, str]:
    """Build per-platform search queries for a given domain."""
    name = company_name or domain
    return {
        "g2": f'site:g2.com "{name}"',
        "capterra": f'site:capterra.com "{name}"',
        "trustpilot": f'site:trustpilot.com "{domain}"',
        "reddit": f'"{domain}" site:reddit.com',
        "glassdoor": f'site:glassdoor.com "{name}" sales',
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
PYTHONPATH=. uv run pytest tests/test_buyer_sentiment_catalog.py -v
```
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add rrxray/collectors/_buyer_sentiment_catalog.py tests/test_buyer_sentiment_catalog.py
git commit -m "feat(2.5b): buyer_sentiment catalog constants + query builder"
```

---

### Task 3: Extraction service — sentiment theme extraction

**Model: Opus 4.7 (real logic: new Pydantic models + LLM method on both extractors)**

**Files:**
- Modify: `rrxray/services/extraction.py`
- Modify: `tests/test_extraction.py`

**Scene-setting context for implementer:** `rrxray/services/extraction.py` contains `HaikuExtractor` and `GeminiFlashExtractor`. Both classes currently have `extract_exec_change` and `extract_funding_event` methods with this pattern: build a user message string, call `self.anthropic.complete_with_cached_system(system_prompt=..., user_message=..., model=..., response_schema=...)`, catch `(AnthropicError, ValidationError)`, return `response.parsed`. Add `extract_sentiment_themes` to both classes following the exact same pattern. The method should also be added to `GeminiFlashExtractor` (using `self.gemini.complete_structured`) for duck-typing consistency.

Add `ExtractedTheme` and `ExtractedSentimentThemes` Pydantic models to the module. `ExtractedSentimentThemes` is the `response_schema` for the LLM call.

The system prompt instructs Haiku to identify 1–5 recurring themes from review text (not single-mention observations), with short phrase labels (3–8 words), sentiment, and an evidence_count estimate.

- [ ] **Step 1: Write the failing tests** (add to `tests/test_extraction.py`)

Add these tests after the existing content of `tests/test_extraction.py`:

```python
# Add to tests/test_extraction.py

from rrxray.services.extraction import (
    ExtractedSentimentThemes,
    ExtractedTheme,
)


class _FakeSentimentResponse(BaseModel):
    parsed: ExtractedSentimentThemes
    model_used: str = "claude-haiku-4-5-20251001"
    cache_hit: bool = False


def test_extracted_theme_model():
    t = ExtractedTheme(theme="slow onboarding", sentiment="negative", evidence_count=3)
    assert t.theme == "slow onboarding"
    assert t.evidence_count == 3


def test_extracted_sentiment_themes_model():
    est = ExtractedSentimentThemes(
        themes=[ExtractedTheme(theme="easy setup", sentiment="positive", evidence_count=5)],
        review_count_estimate=12,
        platform="g2",
    )
    assert est.platform == "g2"
    assert len(est.themes) == 1


def test_haiku_extract_sentiment_themes_success(fake_anthropic):
    from rrxray.services.extraction import ExtractedSentimentThemes, ExtractedTheme, HaikuExtractor
    expected = ExtractedSentimentThemes(
        themes=[ExtractedTheme(theme="fast setup", sentiment="positive", evidence_count=4)],
        review_count_estimate=10,
        platform="g2",
    )
    fake_anthropic.complete_with_cached_system = AsyncMock(
        return_value=_FakeSentimentResponse(parsed=expected)
    )
    extractor = HaikuExtractor(fake_anthropic)
    result = asyncio.run(extractor.extract_sentiment_themes("some review text", "g2"))
    assert result is not None
    assert result.platform == "g2"
    assert len(result.themes) == 1


def test_haiku_extract_sentiment_themes_returns_none_on_error(fake_anthropic):
    from rrxray.services.anthropic_client import AnthropicError
    from rrxray.services.extraction import HaikuExtractor
    fake_anthropic.complete_with_cached_system = AsyncMock(side_effect=AnthropicError("fail"))
    extractor = HaikuExtractor(fake_anthropic)
    result = asyncio.run(extractor.extract_sentiment_themes("some text", "g2"))
    assert result is None


def test_haiku_extract_sentiment_themes_empty_text_returns_none(fake_anthropic):
    from rrxray.services.extraction import HaikuExtractor
    extractor = HaikuExtractor(fake_anthropic)
    result = asyncio.run(extractor.extract_sentiment_themes("", "g2"))
    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=. uv run pytest tests/test_extraction.py -k "sentiment" -v
```
Expected: `ImportError` (models not yet defined).

- [ ] **Step 3: Add models and methods to extraction.py**

After the existing `ExtractedFundingEvent` class (around line 65), add:

```python
_SENTIMENT_THEMES_SYSTEM_PROMPT = """You extract structured sentiment themes from software review platform text.

Given scraped or snippet text from a review platform, identify 1-5 themes that recur across multiple reviews. Each theme should be a short phrase (3-8 words) capturing a pattern. Omit single-mention observations.

sentiment: "positive", "negative", or "mixed".
evidence_count: your estimate of how many distinct reviews mention this theme.
review_count_estimate: if you can infer the approximate total number of reviews from the text, provide it; otherwise null.
platform: return the platform name exactly as provided in the user message.

If the text has insufficient review content (e.g., only navigation or marketing copy with no reviews), return an empty themes list.
"""


class ExtractedTheme(BaseModel):
    theme: str
    sentiment: Literal["positive", "negative", "mixed"]
    evidence_count: int


class ExtractedSentimentThemes(BaseModel):
    themes: list[ExtractedTheme]
    review_count_estimate: int | None = None
    platform: str
```

Then add `extract_sentiment_themes` to `HaikuExtractor` (after `extract_funding_event`):

```python
    async def extract_sentiment_themes(
        self, raw_text: str, platform: str,
    ) -> ExtractedSentimentThemes | None:
        from rrxray.services.anthropic_client import AnthropicError
        if not raw_text:
            return None
        user_message = f"Platform: {platform}\n\n{raw_text[:4000]}"
        try:
            response = await self.anthropic.complete_with_cached_system(
                system_prompt=_SENTIMENT_THEMES_SYSTEM_PROMPT,
                user_message=user_message,
                model="claude-haiku-4-5-20251001",
                response_schema=ExtractedSentimentThemes,
            )
        except (AnthropicError, ValidationError) as e:
            log.debug("Haiku extract_sentiment_themes failed for %s: %s", platform, e)
            return None
        return response.parsed
```

And add to `GeminiFlashExtractor` (after `extract_funding_event`, same structural pattern):

```python
    async def extract_sentiment_themes(
        self, raw_text: str, platform: str,
    ) -> ExtractedSentimentThemes | None:
        from rrxray.services.gemini_client import GeminiError
        if not raw_text:
            return None
        user_message = f"Platform: {platform}\n\n{raw_text[:4000]}"
        try:
            response = await self.gemini.complete_structured(
                system_prompt=_SENTIMENT_THEMES_SYSTEM_PROMPT,
                user_message=user_message,
                response_schema=ExtractedSentimentThemes,
                model="gemini-2.0-flash",
            )
        except (GeminiError, ValidationError) as e:
            log.debug("Gemini extract_sentiment_themes failed for %s: %s", platform, e)
            return None
        return response.parsed
```

Also add `Literal` to the existing `from typing import TYPE_CHECKING, Literal` import line (it's already there per line 23 of extraction.py).

- [ ] **Step 4: Run the new tests**

```bash
PYTHONPATH=. uv run pytest tests/test_extraction.py -v
```
Expected: all existing + 5 new tests pass.

- [ ] **Step 5: Lint**

```bash
PYTHONPATH=. uv run ruff check rrxray/services/extraction.py tests/test_extraction.py
```
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add rrxray/services/extraction.py tests/test_extraction.py
git commit -m "feat(2.5b): ExtractedSentimentThemes + extract_sentiment_themes on both extractors"
```

---

### Task 4: Collector — platform search, scrape, and quarantine

**Model: Opus 4.7 (real logic: multi-platform I/O, error handling, quarantine enforcement)**

**Files:**
- Create: `rrxray/collectors/buyer_sentiment.py` (initial, Tasks 5 and 6 will add to it)
- Create: `tests/test_buyer_sentiment.py` (initial, Tasks 5 and 6 will add to it)

**Scene-setting context:** This task creates the buyer_sentiment collector module with the platform I/O layer: `_search_platform`, `_scrape_platform`, `_collect_platform_text`. The last function writes raw text to `evidence/buyer_sentiment/raw/<platform>.txt` (Verbatim Quarantine — raw review text must never appear in the schema or rendered output, only here). Each function must catch `FirecrawlError` gracefully and return empty/None rather than raising.

`FirecrawlClient` interface:
- `await firecrawl.search(query, limit=5)` → `list[SearchResult]` where `SearchResult` has `.url: str`, `.title: str`, `.description: str`
- `await firecrawl.scrape_url(url)` → `ScrapedPage` where `ScrapedPage` has `.markdown: str`
- Both raise `FirecrawlError` on failure

`SCRAPED_PLATFORMS: set[str]` from catalog = `{"g2", "trustpilot"}` — only these get scrape attempts on the top result.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_buyer_sentiment.py
"""Tests for the buyer_sentiment collector."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from rrxray.collectors.buyer_sentiment import (
    NAME,
    _collect_platform_text,
    _scrape_platform,
    _search_platform,
)
from rrxray.schemas.buyer_sentiment import BuyerSentimentData, ReviewTheme
from rrxray.services.firecrawl_client import FirecrawlError, ScrapedPage, SearchResult


def _fake_firecrawl(search_results=None, scrape_markdown="scrape content"):
    fc = MagicMock()
    fc.search = AsyncMock(return_value=search_results or [
        SearchResult(url="https://g2.com/products/acme", title="Acme on G2", description="Great product but slow onboarding"),
    ])
    fc.scrape_url = AsyncMock(return_value=ScrapedPage(
        url="https://g2.com/products/acme",
        markdown=scrape_markdown,
        html="<html></html>",
    ))
    return fc


def test_name():
    assert NAME == "buyer_sentiment"


def test_search_platform_returns_results(tmp_path):
    fc = _fake_firecrawl()
    results = asyncio.run(_search_platform(fc, 'site:g2.com "acme"'))
    assert len(results) == 1
    assert "g2.com" in results[0].url


def test_search_platform_returns_empty_on_firecrawl_error(tmp_path):
    fc = MagicMock()
    fc.search = AsyncMock(side_effect=FirecrawlError("403"))
    results = asyncio.run(_search_platform(fc, 'site:g2.com "acme"'))
    assert results == []


def test_scrape_platform_returns_markdown():
    fc = _fake_firecrawl(scrape_markdown="# Reviews\n\nGreat product")
    md = asyncio.run(_scrape_platform(fc, "https://g2.com/products/acme"))
    assert md == "# Reviews\n\nGreat product"


def test_scrape_platform_returns_none_on_error():
    fc = MagicMock()
    fc.scrape_url = AsyncMock(side_effect=FirecrawlError("Payment Required"))
    md = asyncio.run(_scrape_platform(fc, "https://g2.com/products/acme"))
    assert md is None


def test_collect_platform_text_writes_quarantine_file(tmp_path):
    fc = _fake_firecrawl(
        search_results=[
            SearchResult(url="https://g2.com/p/acme", title="Acme G2", description="Fast setup"),
        ],
        scrape_markdown="# G2 Review\nFast setup",
    )
    raw, urls = asyncio.run(
        _collect_platform_text(fc, "g2", 'site:g2.com "acme"', tmp_path)
    )
    assert raw != ""
    assert len(urls) == 1
    quarantine_file = tmp_path / "raw" / "g2.txt"
    assert quarantine_file.exists()
    assert len(quarantine_file.read_text()) > 0


def test_collect_platform_text_returns_empty_on_no_results(tmp_path):
    fc = MagicMock()
    fc.search = AsyncMock(return_value=[])
    raw, urls = asyncio.run(
        _collect_platform_text(fc, "g2", 'site:g2.com "acme"', tmp_path)
    )
    assert raw == ""
    assert urls == []


def test_collect_platform_text_caps_at_max_raw_chars(tmp_path):
    from rrxray.collectors._buyer_sentiment_catalog import MAX_RAW_CHARS
    long_desc = "x" * 5000
    fc = _fake_firecrawl(
        search_results=[SearchResult(url="https://g2.com/p/a", title="A", description=long_desc)],
        scrape_markdown="",
    )
    # Make scrape fail so only snippets are used
    fc.scrape_url = AsyncMock(side_effect=FirecrawlError("fail"))
    raw, _ = asyncio.run(
        _collect_platform_text(fc, "g2", 'site:g2.com "acme"', tmp_path)
    )
    assert len(raw) <= MAX_RAW_CHARS
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=. uv run pytest tests/test_buyer_sentiment.py -v
```
Expected: `ImportError` or `ModuleNotFoundError`.

- [ ] **Step 3: Write the collector module (platform I/O layer only)**

```python
# rrxray/collectors/buyer_sentiment.py
"""buyer_sentiment collector: surfaces buyer and ex-rep review signals.

Verbatim Quarantine: all raw scraped/search text writes to
evidence/buyer_sentiment/raw/<platform>.txt. The schema holds
extracted themes only — never verbatim review text.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from rrxray.collectors._buyer_sentiment_catalog import (
    MAX_RAW_CHARS,
    MAX_SEARCH_RESULTS,
    SCRAPED_PLATFORMS,
    build_platform_queries,
)
from rrxray.schemas._shared import Finding, SourceCitation
from rrxray.schemas.buyer_sentiment import BuyerSentimentData, ReviewTheme
from rrxray.services.extraction import ExtractedSentimentThemes, ExtractedTheme

if TYPE_CHECKING:
    from rrxray.context import CollectorContext
    from rrxray.services.firecrawl_client import FirecrawlClient, SearchResult

NAME = "buyer_sentiment"
log = logging.getLogger(f"rrxray.collectors.{NAME}")


async def _search_platform(
    firecrawl: FirecrawlClient, query: str
) -> list[SearchResult]:
    """Search a platform. Returns empty list on FirecrawlError."""
    from rrxray.services.firecrawl_client import FirecrawlError
    try:
        return await firecrawl.search(query, limit=MAX_SEARCH_RESULTS)
    except FirecrawlError as e:
        log.debug("Search failed for %r: %s", query, e)
        return []


async def _scrape_platform(
    firecrawl: FirecrawlClient, url: str
) -> str | None:
    """Scrape a URL for full text. Returns None on FirecrawlError."""
    from rrxray.services.firecrawl_client import FirecrawlError
    try:
        page = await firecrawl.scrape_url(url)
        return page.markdown
    except FirecrawlError as e:
        log.debug("Scrape failed for %s: %s", url, e)
        return None


async def _collect_platform_text(
    firecrawl: FirecrawlClient,
    platform: str,
    query: str,
    evidence_dir: Path,
) -> tuple[str, list[str]]:
    """Search + optionally scrape one platform.

    Returns (raw_text, source_urls). Writes raw_text to
    evidence_dir/raw/<platform>.txt (Verbatim Quarantine).
    raw_text is capped at MAX_RAW_CHARS.
    """
    results = await _search_platform(firecrawl, query)
    if not results:
        return "", []

    source_urls = [r.url for r in results]
    parts: list[str] = []

    # For G2/Trustpilot: attempt to scrape top result for fuller text
    if platform in SCRAPED_PLATFORMS:
        scraped = await _scrape_platform(firecrawl, results[0].url)
        if scraped:
            parts.append(scraped[:2000])

    # Append snippets from all results
    for r in results:
        parts.append(f"[{r.title}] {r.description}")

    raw_text = "\n\n".join(parts)[:MAX_RAW_CHARS]

    # Verbatim Quarantine: quarantine raw text to evidence, never in schema
    raw_dir = evidence_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / f"{platform}.txt").write_text(raw_text, encoding="utf-8")

    return raw_text, source_urls
```

- [ ] **Step 4: Run the tests**

```bash
PYTHONPATH=. uv run pytest tests/test_buyer_sentiment.py -v
```
Expected: all 8 tests pass.

- [ ] **Step 5: Lint**

```bash
PYTHONPATH=. uv run ruff check rrxray/collectors/buyer_sentiment.py tests/test_buyer_sentiment.py
```
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add rrxray/collectors/buyer_sentiment.py tests/test_buyer_sentiment.py
git commit -m "feat(2.5b): buyer_sentiment collector — platform search + scrape + quarantine"
```

---

### Task 5: Collector — theme extraction, merging, and rule-based findings

**Model: Opus 4.7 (real logic: dedup, frequency labeling, rule-based findings)**

**Files:**
- Modify: `rrxray/collectors/buyer_sentiment.py` (add `_extract_themes`, `_merge_themes`, `_emit_findings`)
- Modify: `tests/test_buyer_sentiment.py` (add tests for these functions)

**Scene-setting context:** 

`_extract_themes(extractor, platform, raw_text)` calls `extractor.extract_sentiment_themes(raw_text, platform)`. The `extractor` may be `None` (some tests mock ctx without one), a `HaikuExtractor`, or a `GeminiFlashExtractor`. If `extractor` is None or the call returns None, return `[]`. The method `extract_sentiment_themes` exists on both extractor types (added in Task 3).

`_merge_themes(platform_themes: dict[str, list[ExtractedTheme]])` merges across platforms:
- Key = `theme.lower().strip()` for deduplication
- `frequency`: 1 platform = "single", 2 = "repeated", 3+ = "dominant"
- `sentiment`: majority vote; tie → "mixed"
- `source_platforms`: deduplicated list, order preserved
- Returns `(general_themes, sales_rep_themes)` where `sales_rep_themes` = themes exclusively from Glassdoor (platforms list == ["glassdoor"]); general_themes = everything else. Both lists sorted by frequency (dominant first).

`_emit_findings(themes, sales_rep_themes, platforms_found)` rule-based (no LLM):
- 0 platforms found → gap "No public review presence detected on G2, Capterra, Trustpilot, Reddit, or Glassdoor"
- G2 and Capterra both absent → gap "No G2 or Capterra presence detected; may indicate early-stage or channel-heavy sales motion"
- Any dominant negative theme → Finding naming theme + platforms
- Any dominant positive theme → Finding naming theme + platforms
- Any negative sales_rep_theme → Finding naming theme + discovery question about sales-side experience
- Returns `(findings, gaps, questions)`

- [ ] **Step 1: Add tests to `tests/test_buyer_sentiment.py`**

Append after the existing tests:

```python
from rrxray.collectors.buyer_sentiment import (
    _emit_findings,
    _extract_themes,
    _merge_themes,
)
from rrxray.services.extraction import ExtractedSentimentThemes, ExtractedTheme


# --- _extract_themes ---

def test_extract_themes_returns_themes_from_extractor():
    extractor = MagicMock()
    themes = [ExtractedTheme(theme="easy setup", sentiment="positive", evidence_count=3)]
    extractor.extract_sentiment_themes = AsyncMock(
        return_value=ExtractedSentimentThemes(themes=themes, platform="g2")
    )
    result = asyncio.run(_extract_themes(extractor, "g2", "review text here"))
    assert len(result) == 1
    assert result[0].theme == "easy setup"


def test_extract_themes_returns_empty_when_extractor_is_none():
    result = asyncio.run(_extract_themes(None, "g2", "some text"))
    assert result == []


def test_extract_themes_returns_empty_on_none_result():
    extractor = MagicMock()
    extractor.extract_sentiment_themes = AsyncMock(return_value=None)
    result = asyncio.run(_extract_themes(extractor, "g2", "some text"))
    assert result == []


def test_extract_themes_returns_empty_for_empty_text():
    extractor = MagicMock()
    result = asyncio.run(_extract_themes(extractor, "g2", ""))
    extractor.extract_sentiment_themes.assert_not_called()
    assert result == []


# --- _merge_themes ---

def test_merge_themes_deduplicates_across_platforms():
    platform_themes = {
        "g2": [ExtractedTheme(theme="slow onboarding", sentiment="negative", evidence_count=3)],
        "capterra": [ExtractedTheme(theme="Slow Onboarding", sentiment="negative", evidence_count=2)],
    }
    general, sales = _merge_themes(platform_themes)
    # Should merge "slow onboarding" and "Slow Onboarding" into one theme
    assert len(general) == 1
    assert general[0].frequency == "repeated"
    assert set(general[0].source_platforms) == {"g2", "capterra"}
    assert sales == []


def test_merge_themes_dominant_at_three_platforms():
    platform_themes = {
        "g2": [ExtractedTheme(theme="fast setup", sentiment="positive", evidence_count=4)],
        "capterra": [ExtractedTheme(theme="fast setup", sentiment="positive", evidence_count=2)],
        "trustpilot": [ExtractedTheme(theme="fast setup", sentiment="positive", evidence_count=5)],
    }
    general, _ = _merge_themes(platform_themes)
    assert general[0].frequency == "dominant"


def test_merge_themes_glassdoor_goes_to_sales_rep_themes():
    platform_themes = {
        "g2": [ExtractedTheme(theme="good product", sentiment="positive", evidence_count=2)],
        "glassdoor": [ExtractedTheme(theme="low quota attainment", sentiment="negative", evidence_count=4)],
    }
    general, sales = _merge_themes(platform_themes)
    assert any(t.theme == "good product" for t in general)
    assert any(t.theme == "low quota attainment" for t in sales)


def test_merge_themes_sentiment_tie_becomes_mixed():
    platform_themes = {
        "g2": [ExtractedTheme(theme="pricing", sentiment="positive", evidence_count=3)],
        "capterra": [ExtractedTheme(theme="pricing", sentiment="negative", evidence_count=3)],
    }
    general, _ = _merge_themes(platform_themes)
    assert general[0].sentiment == "mixed"


# --- _emit_findings ---

def test_emit_findings_gap_on_zero_platforms():
    findings, gaps, questions = _emit_findings([], [], [])
    assert len(gaps) == 1
    assert "review presence" in gaps[0].lower() or "No public" in gaps[0]
    assert findings == []


def test_emit_findings_gap_when_g2_and_capterra_both_absent():
    findings, gaps, questions = _emit_findings([], [], ["reddit"])
    gap_text = " ".join(gaps).lower()
    assert "g2" in gap_text or "capterra" in gap_text


def test_emit_findings_finding_for_dominant_negative_theme():
    themes = [ReviewTheme(theme="slow support", sentiment="negative", source_platforms=["g2", "capterra", "trustpilot"], frequency="dominant")]
    findings, gaps, questions = _emit_findings(themes, [], ["g2", "capterra", "trustpilot"])
    assert any("slow support" in f.text for f in findings)


def test_emit_findings_finding_and_question_for_negative_sales_rep_theme():
    sales = [ReviewTheme(theme="low quota attainment", sentiment="negative", source_platforms=["glassdoor"], frequency="single")]
    findings, gaps, questions = _emit_findings([], sales, ["glassdoor"])
    assert any("quota" in f.text.lower() for f in findings)
    assert len(questions) >= 1
```

- [ ] **Step 2: Run new tests to verify they fail**

```bash
PYTHONPATH=. uv run pytest tests/test_buyer_sentiment.py -k "extract_themes or merge_themes or emit_findings" -v
```
Expected: `ImportError` (functions not yet defined).

- [ ] **Step 3: Add the three functions to `buyer_sentiment.py`**

Append after `_collect_platform_text`:

```python
async def _extract_themes(
    extractor: object | None,
    platform: str,
    raw_text: str,
) -> list[ExtractedTheme]:
    """Extract themes from raw_text via LLM. Returns [] on any failure."""
    if not raw_text or extractor is None:
        return []
    if not hasattr(extractor, "extract_sentiment_themes"):
        return []
    result = await extractor.extract_sentiment_themes(raw_text, platform)
    if result is None:
        return []
    return result.themes


def _merge_themes(
    platform_themes: dict[str, list[ExtractedTheme]],
) -> tuple[list[ReviewTheme], list[ReviewTheme]]:
    """Merge per-platform ExtractedTheme lists into deduplicated ReviewTheme lists.

    Returns (general_themes, sales_rep_themes).
    sales_rep_themes = themes exclusively from Glassdoor.
    Frequency: 1 platform="single", 2="repeated", 3+="dominant".
    Sentiment: majority vote; tie -> "mixed".
    Both lists sorted dominant-first.
    """
    from collections import Counter, defaultdict
    from typing import Literal

    merged: dict[str, dict] = defaultdict(
        lambda: {"theme": "", "platforms": [], "sentiments": []}
    )

    for platform, themes in platform_themes.items():
        for t in themes:
            key = t.theme.lower().strip()
            if not merged[key]["theme"]:
                merged[key]["theme"] = t.theme
            merged[key]["platforms"].append(platform)
            merged[key]["sentiments"].append(t.sentiment)

    def _frequency(platforms: list[str]) -> Literal["single", "repeated", "dominant"]:
        n = len(platforms)
        if n >= 3:
            return "dominant"
        if n == 2:
            return "repeated"
        return "single"

    def _majority_sentiment(sentiments: list[str]) -> Literal["positive", "negative", "mixed"]:
        counts = Counter(sentiments)
        top_val, top_count = counts.most_common(1)[0]
        if top_count > len(sentiments) // 2:
            return top_val  # type: ignore[return-value]
        return "mixed"

    freq_order = {"dominant": 0, "repeated": 1, "single": 2}
    general: list[ReviewTheme] = []
    sales_rep: list[ReviewTheme] = []

    for data in merged.values():
        platforms = data["platforms"]
        rt = ReviewTheme(
            theme=data["theme"],
            sentiment=_majority_sentiment(data["sentiments"]),
            source_platforms=list(dict.fromkeys(platforms)),
            frequency=_frequency(platforms),
        )
        if set(platforms) == {"glassdoor"}:
            sales_rep.append(rt)
        else:
            general.append(rt)

    general.sort(key=lambda t: freq_order[t.frequency])
    sales_rep.sort(key=lambda t: freq_order[t.frequency])
    return general, sales_rep


def _emit_findings(
    themes: list[ReviewTheme],
    sales_rep_themes: list[ReviewTheme],
    platforms_found: list[str],
) -> tuple[list[Finding], list[str], list[str]]:
    """Rule-based findings, gaps, and discovery questions. No LLM."""
    now = datetime.now(UTC)
    findings: list[Finding] = []
    gaps: list[str] = []
    questions: list[str] = []
    source = SourceCitation(url="rrxray://buyer_sentiment", timestamp=now)

    if not platforms_found:
        gaps.append(
            "No public review presence detected on G2, Capterra, Trustpilot, "
            "Reddit, or Glassdoor."
        )
        return findings, gaps, questions

    # G2 + Capterra both absent
    if "g2" not in platforms_found and "capterra" not in platforms_found:
        gaps.append(
            "No G2 or Capterra presence detected; may indicate early-stage or "
            "channel-heavy sales motion where self-serve review discovery is not yet active."
        )

    # Dominant themes
    for t in themes:
        if t.frequency == "dominant":
            platforms_str = ", ".join(t.source_platforms)
            findings.append(Finding(
                text=(
                    f"Dominant {t.sentiment} theme across buyer reviews on {platforms_str}: "
                    f"\"{t.theme}\"."
                ),
                source=source,
            ))

    # Negative sales-rep themes
    for t in sales_rep_themes:
        if t.sentiment in ("negative", "mixed"):
            findings.append(Finding(
                text=(
                    f"Ex-rep Glassdoor reviews surface a {t.sentiment} theme: "
                    f"\"{t.theme}\"."
                ),
                source=source,
            ))
            questions.append(
                f"Glassdoor reviews from former sales reps mention \"{t.theme}\". "
                "Is this a known pattern, and has anything changed in the sales motion to address it?"
            )

    return findings, gaps, questions
```

- [ ] **Step 4: Run all buyer_sentiment tests**

```bash
PYTHONPATH=. uv run pytest tests/test_buyer_sentiment.py -v
```
Expected: all tests pass.

- [ ] **Step 5: Lint**

```bash
PYTHONPATH=. uv run ruff check rrxray/collectors/buyer_sentiment.py tests/test_buyer_sentiment.py
```
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add rrxray/collectors/buyer_sentiment.py tests/test_buyer_sentiment.py
git commit -m "feat(2.5b): _extract_themes + _merge_themes + _emit_findings"
```

---

### Task 6: Collector — orchestrator and evidence writer

**Model: Opus 4.7 (real logic: asyncio.gather orchestration, evidence writes)**

**Files:**
- Modify: `rrxray/collectors/buyer_sentiment.py` (add `_write_evidence`, `collect`)
- Modify: `tests/test_buyer_sentiment.py` (add orchestrator tests)

**Scene-setting context:** The `collect(ctx)` function must:
1. Build per-platform queries from catalog `build_platform_queries(ctx.domain, ctx.company_name)`
2. Run all 5 platforms concurrently via `asyncio.gather` with `return_exceptions=True`
3. Run LLM theme extraction concurrently after platform collection
4. Call `_merge_themes`, `_emit_findings`, `_write_evidence`
5. Return `BuyerSentimentData`

Evidence dir structure: `ctx.evidence_dir / NAME / raw / <platform>.txt` (raw files, written by `_collect_platform_text`) + `ctx.evidence_dir / NAME / themes.json` (merged themes, written by `_write_evidence`).

`ctx` is a `CollectorContext` dataclass with: `.domain: str`, `.company_name: str | None`, `.firecrawl: FirecrawlClient`, `.extractor: HaikuExtractor | GeminiFlashExtractor | None`, `.evidence_dir: Path`.

- [ ] **Step 1: Add orchestrator tests to `tests/test_buyer_sentiment.py`**

Append after existing tests:

```python
from rrxray.collectors.buyer_sentiment import collect, _write_evidence


# --- _write_evidence ---

def test_write_evidence_creates_themes_json(tmp_path):
    themes = [ReviewTheme(theme="easy setup", sentiment="positive", source_platforms=["g2"], frequency="single")]
    _write_evidence(tmp_path, themes, [])
    themes_file = tmp_path / "themes.json"
    assert themes_file.exists()
    data = json.loads(themes_file.read_text())
    assert "themes" in data
    assert "sales_rep_themes" in data
    assert data["themes"][0]["theme"] == "easy setup"


def test_write_evidence_creates_dir_if_missing(tmp_path):
    evidence_dir = tmp_path / "new_dir"
    _write_evidence(evidence_dir, [], [])
    assert evidence_dir.exists()
    assert (evidence_dir / "themes.json").exists()


# --- collect ---

@pytest.fixture
def fake_extractor():
    from rrxray.services.extraction import ExtractedSentimentThemes, ExtractedTheme
    ext = MagicMock()
    ext.extract_sentiment_themes = AsyncMock(return_value=ExtractedSentimentThemes(
        themes=[ExtractedTheme(theme="easy setup", sentiment="positive", evidence_count=3)],
        review_count_estimate=5,
        platform="g2",
    ))
    return ext


@pytest.fixture
def collector_ctx(tmp_path, fake_extractor):
    from rrxray.services.firecrawl_client import ScrapedPage, SearchResult
    fc = MagicMock()
    fc.search = AsyncMock(return_value=[
        SearchResult(url="https://g2.com/products/acme", title="Acme G2", description="Good product"),
    ])
    fc.scrape_url = AsyncMock(return_value=ScrapedPage(
        url="https://g2.com/products/acme", markdown="# Reviews\nGood product", html=""
    ))
    ctx = MagicMock()
    ctx.domain = "acme.com"
    ctx.company_name = "Acme"
    ctx.firecrawl = fc
    ctx.extractor = fake_extractor
    ctx.evidence_dir = tmp_path / "evidence"
    return ctx


def test_collect_returns_buyer_sentiment_data(collector_ctx):
    result = asyncio.run(collect(collector_ctx))
    assert isinstance(result, BuyerSentimentData)
    assert "g2" in result.platforms_checked
    assert "capterra" in result.platforms_checked
    assert "glassdoor" in result.platforms_checked


def test_collect_writes_evidence_files(collector_ctx):
    asyncio.run(collect(collector_ctx))
    evidence = collector_ctx.evidence_dir / "buyer_sentiment"
    assert (evidence / "themes.json").exists()


def test_collect_graceful_degradation_on_all_platforms_failing(tmp_path):
    from rrxray.services.firecrawl_client import FirecrawlError
    fc = MagicMock()
    fc.search = AsyncMock(side_effect=FirecrawlError("503"))
    ctx = MagicMock()
    ctx.domain = "acme.com"
    ctx.company_name = None
    ctx.firecrawl = fc
    ctx.extractor = None
    ctx.evidence_dir = tmp_path / "evidence"
    result = asyncio.run(collect(ctx))
    assert isinstance(result, BuyerSentimentData)
    assert result.platforms_found == []
    assert len(result.gaps) >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=. uv run pytest tests/test_buyer_sentiment.py -k "write_evidence or collect" -v
```
Expected: `ImportError` for `collect` and `_write_evidence`.

- [ ] **Step 3: Add `_write_evidence` and `collect` to `buyer_sentiment.py`**

Append after `_emit_findings`:

```python
def _write_evidence(
    evidence_dir: Path,
    themes: list[ReviewTheme],
    sales_rep_themes: list[ReviewTheme],
) -> None:
    """Write merged themes to evidence/buyer_sentiment/themes.json."""
    evidence_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "themes": [t.model_dump() for t in themes],
        "sales_rep_themes": [t.model_dump() for t in sales_rep_themes],
    }
    (evidence_dir / "themes.json").write_text(
        json.dumps(data, indent=2), encoding="utf-8"
    )


async def collect(ctx: CollectorContext) -> BuyerSentimentData:
    """Collect buyer sentiment from review platforms."""
    queries = build_platform_queries(ctx.domain, ctx.company_name)
    evidence_base = ctx.evidence_dir / NAME

    platforms_checked = list(queries.keys())
    platforms_found: list[str] = []
    all_source_urls: list[str] = []
    platform_raw_texts: dict[str, str] = {}

    # Collect raw text from all platforms concurrently
    async def _collect_one(platform: str) -> tuple[str, str, list[str]]:
        raw, urls = await _collect_platform_text(
            ctx.firecrawl, platform, queries[platform], evidence_base
        )
        return platform, raw, urls

    collection_results = await asyncio.gather(
        *[_collect_one(p) for p in platforms_checked],
        return_exceptions=True,
    )

    for result in collection_results:
        if isinstance(result, BaseException):
            log.warning("Platform collection raised: %s", result)
            continue
        platform, raw, urls = result
        if raw:
            platforms_found.append(platform)
            platform_raw_texts[platform] = raw
            all_source_urls.extend(urls)

    # Extract themes per platform concurrently
    async def _extract_one(platform: str) -> tuple[str, list[ExtractedTheme]]:
        t = await _extract_themes(ctx.extractor, platform, platform_raw_texts[platform])
        return platform, t

    theme_results = await asyncio.gather(
        *[_extract_one(p) for p in platforms_found],
        return_exceptions=True,
    )

    platform_themes: dict[str, list[ExtractedTheme]] = {}
    review_count_estimate: int | None = None
    for result in theme_results:
        if isinstance(result, BaseException):
            log.debug("Theme extraction raised: %s", result)
            continue
        platform, themes = result
        platform_themes[platform] = themes

    # Merge and emit
    themes, sales_rep_themes = _merge_themes(platform_themes)
    findings, gaps, questions = _emit_findings(themes, sales_rep_themes, platforms_found)

    # Write evidence (themes.json; raw/ files written by _collect_platform_text)
    _write_evidence(evidence_base, themes, sales_rep_themes)

    now = datetime.now(UTC)
    sources = [SourceCitation(url=url, timestamp=now) for url in all_source_urls]

    return BuyerSentimentData(
        platforms_checked=platforms_checked,
        platforms_found=platforms_found,
        review_count_estimate=review_count_estimate,
        themes=themes,
        sales_rep_themes=sales_rep_themes,
        findings=findings,
        gaps=gaps,
        discovery_questions=questions,
        sources=sources,
    )
```

- [ ] **Step 4: Run full test suite**

```bash
PYTHONPATH=. uv run pytest tests/test_buyer_sentiment.py -v
```
Expected: all tests pass (8 from Task 4 + 16 from Tasks 5–6).

- [ ] **Step 5: Lint**

```bash
PYTHONPATH=. uv run ruff check rrxray/collectors/buyer_sentiment.py tests/test_buyer_sentiment.py
```
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add rrxray/collectors/buyer_sentiment.py tests/test_buyer_sentiment.py
git commit -m "feat(2.5b): _write_evidence + collect() orchestrator"
```

---

### Task 7: CollectorOutputs wiring and pipeline registration

**Model: Haiku 4.5 (mechanical)**

**Files:**
- Modify: `rrxray/schemas/data.py`
- Modify: `rrxray/pipeline.py`
- Modify: `tests/test_schemas.py`
- Modify: `tests/test_pipeline.py`

**Scene-setting context:** `CollectorOutputs` in `data.py` uses string-quoted forward references for all collector fields. The import resolves at the bottom of the file, before `CollectorOutputs.model_rebuild()`. Follow the exact same pattern as the `positioning_drift` field added in Phase 2.5a (line 52: `positioning_drift: "PositioningDriftData | None" = None  # Phase 2.5a`). Add `buyer_sentiment` immediately after it.

In `pipeline.py`, the `COLLECTORS` list already imports and includes `positioning_drift`. Add `buyer_sentiment` the same way: import it at line ~15 in the collectors import block, append it to `COLLECTORS` after `positioning_drift`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_schemas.py`, find the test for `positioning_drift` field and add:

```python
def test_collector_outputs_has_buyer_sentiment_field():
    from rrxray.schemas.buyer_sentiment import BuyerSentimentData
    from rrxray.schemas.data import CollectorOutputs
    c = CollectorOutputs()
    assert c.buyer_sentiment is None
    theme = ReviewTheme(
        theme="easy setup", sentiment="positive",
        source_platforms=["g2"], frequency="single",
    )
    from rrxray.schemas.buyer_sentiment import BuyerSentimentData, ReviewTheme
    c = CollectorOutputs(buyer_sentiment=BuyerSentimentData(themes=[theme]))
    assert len(c.buyer_sentiment.themes) == 1
```

In `tests/test_pipeline.py`, find the test for `positioning_drift` in COLLECTORS and add:

```python
def test_collectors_includes_buyer_sentiment():
    from rrxray.pipeline import COLLECTORS
    names = [c.NAME for c in COLLECTORS]
    assert "buyer_sentiment" in names
```

- [ ] **Step 2: Run the new tests to verify they fail**

```bash
PYTHONPATH=. uv run pytest tests/test_schemas.py::test_collector_outputs_has_buyer_sentiment_field tests/test_pipeline.py::test_collectors_includes_buyer_sentiment -v
```
Expected: `AttributeError` or `AssertionError` (field/module not registered yet).

- [ ] **Step 3: Update `data.py`**

In `rrxray/schemas/data.py`, after line 52 (`positioning_drift: "PositioningDriftData | None" = None  # Phase 2.5a`), add:

```python
    buyer_sentiment: "BuyerSentimentData | None" = None  # Phase 2.5b
```

Then at the bottom of the file, after the `PositioningDriftData` import line and before `CollectorOutputs.model_rebuild()`, add:

```python
from rrxray.schemas.buyer_sentiment import BuyerSentimentData  # noqa: E402
```

The bottom of `data.py` should now read:

```python
# Resolve forward references
from rrxray.schemas.content_demand import ContentDemandData  # noqa: E402
from rrxray.schemas.funding_trajectory import FundingTrajectoryData  # noqa: E402
from rrxray.schemas.leadership_stability import LeadershipStabilityData  # noqa: E402
from rrxray.schemas.positioning_drift import PositioningDriftData  # noqa: E402
from rrxray.schemas.buyer_sentiment import BuyerSentimentData  # noqa: E402
from rrxray.schemas.pricing_packaging import PricingPackagingData  # noqa: E402
from rrxray.schemas.revenue_motion import RevenueMotionData  # noqa: E402
from rrxray.schemas.tech_stack import TechStackData  # noqa: E402

CollectorOutputs.model_rebuild()
```

- [ ] **Step 4: Update `pipeline.py`**

In `rrxray/pipeline.py`, add `buyer_sentiment` to the collectors import block:

```python
from rrxray.collectors import (
    buyer_sentiment,
    content_demand,
    funding_trajectory,
    leadership_stability,
    positioning_drift,
    pricing_packaging,
    revenue_motion,
    tech_stack,
)
```

And append to `COLLECTORS`:

```python
COLLECTORS = [
    pricing_packaging,
    tech_stack,
    revenue_motion,
    content_demand,
    leadership_stability,
    funding_trajectory,
    positioning_drift,
    buyer_sentiment,
]
```

- [ ] **Step 5: Run the tests and full suite**

```bash
PYTHONPATH=. uv run pytest tests/test_schemas.py tests/test_pipeline.py -v
```
Expected: all tests pass including the two new ones.

```bash
PYTHONPATH=. uv run pytest tests/ -q --tb=short
```
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add rrxray/schemas/data.py rrxray/pipeline.py tests/test_schemas.py tests/test_pipeline.py
git commit -m "feat(2.5b): register buyer_sentiment in CollectorOutputs + pipeline"
```

---

### Task 8: Template partial and report include

**Model: Haiku 4.5 (mechanical)**

**Files:**
- Create: `templates/_buyer_sentiment_detail.md.jinja`
- Modify: `templates/report_internal.md.jinja`
- Modify: `tests/test_render_internal.py`

**Scene-setting context:** Follow the exact pattern of `_positioning_drift_detail.md.jinja` and its include block in `report_internal.md.jinja`. The Module Detail Appendix (Section 5) now ends with the `{% if data.collectors.positioning_drift %}` block. Add the `buyer_sentiment` block immediately after that block and before the closing `---`. Use `voice_collector` filter on all text fields. The template must NOT render any field that could contain verbatim review text — `themes` and `sales_rep_themes` hold theme labels only; do NOT render `sources` raw text or any field not defined in the schema. Do not render `platforms_checked` as a table if `platforms_found` is empty (avoid empty tables).

- [ ] **Step 1: Write the failing test** (append to `tests/test_render_internal.py`)

```python
def test_render_includes_buyer_sentiment_detail():
    """When buyer_sentiment data is present, the detail block renders."""
    from datetime import UTC, datetime

    from rrxray.rendering.markdown import render_internal
    from rrxray.schemas.buyer_sentiment import BuyerSentimentData, ReviewTheme
    from rrxray.schemas.data import (
        CollectorOutputs,
        InputParams,
        RunMetadata,
        SynthesizerOutputs,
        XrayData,
    )
    from rrxray.voice.anonymizer import Anonymizer
    from rrxray.voice.rr_voice import VoicePostProcessor

    theme = ReviewTheme(
        theme="implementation support gaps",
        sentiment="negative",
        source_platforms=["g2", "capterra"],
        frequency="repeated",
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
            buyer_sentiment=BuyerSentimentData(
                platforms_checked=["g2", "capterra"],
                platforms_found=["g2", "capterra"],
                themes=[theme],
            )
        ),
        synthesizers=SynthesizerOutputs(),
    )
    report = render_internal(data, Anonymizer(), VoicePostProcessor())
    assert "Buyer Sentiment" in report
    assert "implementation support gaps" in report
```

- [ ] **Step 2: Run test to verify it fails**

```bash
PYTHONPATH=. uv run pytest tests/test_render_internal.py::test_render_includes_buyer_sentiment_detail -v
```
Expected: `AssertionError` ("Buyer Sentiment" not in rendered output).

- [ ] **Step 3: Create the template partial**

```jinja
{# templates/_buyer_sentiment_detail.md.jinja #}
{% set bs = data.collectors.buyer_sentiment %}
**Platforms checked:** {{ bs.platforms_checked | join(", ") or "none" }}
**Platforms with results:** {{ bs.platforms_found | join(", ") or "none" }}
{% if bs.review_count_estimate %}
**Estimated review count:** {{ bs.review_count_estimate }}
{% endif %}

{% if bs.themes %}
**Buyer themes:**

| Theme | Sentiment | Frequency | Platforms |
|---|---|---|---|
{% for t in bs.themes %}
| {{ t.theme | voice_collector }} | {{ t.sentiment }} | {{ t.frequency }} | {{ t.source_platforms | join(", ") }} |
{% endfor %}

{% endif %}
{% if bs.sales_rep_themes %}
**Sales-rep themes (Glassdoor):**

| Theme | Sentiment | Frequency |
|---|---|---|
{% for t in bs.sales_rep_themes %}
| {{ t.theme | voice_collector }} | {{ t.sentiment }} | {{ t.frequency }} |
{% endfor %}

{% endif %}
{% if bs.findings %}
**Findings:**

{% for f in bs.findings %}
- {{ f.text | voice_collector }} *(source: [{{ f.source.url }}]({{ f.source.url }}))*
{% endfor %}
{% endif %}
{% if bs.gaps %}
**Gaps:**

{% for g in bs.gaps %}
→ {{ g | voice_collector }}
{% endfor %}
{% endif %}
{% if bs.discovery_questions %}
**Discovery questions:**

{% for q in bs.discovery_questions %}
- {{ q | voice_collector }}
{% endfor %}
{% endif %}
```

- [ ] **Step 4: Add the include block to `report_internal.md.jinja`**

In `templates/report_internal.md.jinja`, find the positioning_drift include block (ends with `{% endif %}`). Immediately after that `{% endif %}`, add:

```jinja
{% if data.collectors.buyer_sentiment %}
### Buyer Sentiment

{% include "_buyer_sentiment_detail.md.jinja" %}
{% endif %}
```

The Module Detail Appendix section should now end with:

```jinja
{% if data.collectors.positioning_drift %}
### Positioning Drift

{% include "_positioning_drift_detail.md.jinja" %}
{% endif %}

{% if data.collectors.buyer_sentiment %}
### Buyer Sentiment

{% include "_buyer_sentiment_detail.md.jinja" %}
{% endif %}

---

## 6. Discovery Questions
```

- [ ] **Step 5: Run the test**

```bash
PYTHONPATH=. uv run pytest tests/test_render_internal.py::test_render_includes_buyer_sentiment_detail -v
```
Expected: PASS.

- [ ] **Step 6: Run the full suite and lint**

```bash
PYTHONPATH=. uv run pytest tests/ -q --tb=short
```
Expected: all tests pass.

```bash
PYTHONPATH=. uv run ruff check rrxray/ tests/
```
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add templates/_buyer_sentiment_detail.md.jinja templates/report_internal.md.jinja tests/test_render_internal.py
git commit -m "feat(2.5b): buyer_sentiment Module Detail partial + report template include"
```

---

## Post-task: Final quality gate

After all 8 tasks are committed, run the full suite and lint as a controller-level verification:

```bash
PYTHONPATH=. uv run pytest tests/ -v 2>&1 | tail -10
PYTHONPATH=. uv run ruff check rrxray/ tests/
```

Both must pass cleanly before dispatching the final Opus whole-branch code reviewer.

---

## Success criteria (whole plan)

- `rrxray/schemas/buyer_sentiment.py` — `ReviewTheme` + `BuyerSentimentData`
- `rrxray/collectors/_buyer_sentiment_catalog.py` — constants + `build_platform_queries`
- `rrxray/services/extraction.py` — `ExtractedTheme` + `ExtractedSentimentThemes` + `extract_sentiment_themes` on both extractors
- `rrxray/collectors/buyer_sentiment.py` — all 8 functions + `collect()`
- `rrxray/schemas/data.py` — `buyer_sentiment` field wired
- `rrxray/pipeline.py` — `buyer_sentiment` in `COLLECTORS`
- `templates/_buyer_sentiment_detail.md.jinja` + report include
- All tests pass; ruff clean; no verbatim review text in schema or template
