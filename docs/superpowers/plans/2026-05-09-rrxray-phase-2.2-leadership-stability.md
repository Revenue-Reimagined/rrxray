# rrxray Phase 2.2 leadership_stability + observed_stability_trajectory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the `leadership_stability` collector (first Section B signal) plus the new `observed_stability_trajectory` Section B synthesizer. Surfaces exec changes via press-release search, current C-suite via LinkedIn search, and founder tenure via `/about` parse with Wayback fallback. Populates the anonymizer name registry. Ships a thin `GeminiClient` and a duck-typed extractor module so press/LinkedIn snippets can be parsed via Haiku 4.5 (default) or Gemini Flash (`--extractor=gemini-flash`).

**Architecture:** Same module-pattern collector as Phase 2.1c `revenue_motion`. Adds two new service classes: `GeminiClient` (sibling to `AnthropicClient`; no provider-abstraction layer) and an `extraction` module with `HaikuExtractor` + `GeminiFlashExtractor` + `make_extractor()` factory. Collector returns `name_registrations` on its schema; pipeline applies anonymizer side effects post-collection. Section B synthesizer pre-aggregates collector data into name-free `StabilityAggregates` before rendering its prompt.

**Tech Stack:** Python 3.12+, pydantic v2, jinja2, firecrawl-py (existing), anthropic SDK (existing), `google-genai` SDK (NEW — Dale-approved), pytest + pytest-asyncio, ruff.

**Spec reference:** [docs/superpowers/specs/2026-05-09-rrxray-phase-2.2-leadership-stability-design.md](../specs/2026-05-09-rrxray-phase-2.2-leadership-stability-design.md)

---

## File Structure

`[T#]` indicates the task that creates or modifies each file.

```
NEW:
  rrxray/services/gemini_client.py                      [T1: GeminiClient + ParsedResponse + GeminiError]
  rrxray/services/extraction.py                         [T2: HaikuExtractor + GeminiFlashExtractor + make_extractor + Extracted* models]
  rrxray/schemas/leadership_stability.py                [T3: LeadershipStabilityData + ExecChange + CurrentIncumbent + FounderTenure + NameRegistration]
  rrxray/collectors/_leadership_stability_catalog.py    [T4: LEADERSHIP_ROLES + PRESS_ACTION_QUERIES + ROLE_DISPLAY + thresholds]
  rrxray/collectors/leadership_stability.py             [T7-T11: collector body]
  rrxray/synthesizers/observed_stability_trajectory.py  [T14: synthesizer body]
  rrxray/prompts/observed_stability_trajectory.md       [T14: prompt template]
  templates/_leadership_stability_detail.md.jinja       [T13: Module Detail partial]
  tests/test_gemini_client.py                           [T1]
  tests/test_extraction.py                              [T2]
  tests/test_leadership_stability_schemas.py            [T3]
  tests/test_leadership_stability_catalog.py            [T4]
  tests/test_leadership_stability.py                    [T7-T11]
  tests/test_observed_stability_trajectory.py           [T14]
  tests/fixtures/synthetic/leadership_stability/        [T7-T9: search responses + HTML]

MODIFIED:
  pyproject.toml                                        [T1: add google-genai dep]
  rrxray/schemas/data.py                                [T5: add leadership_stability + ObservedStabilityTrajectoryNarrative + observed_stability_trajectory]
  rrxray/config.py                                      [T6: add GEMINI_API_KEY + extractor_model fields]
  rrxray/cli.py                                         [T6: add --extractor flag]
  rrxray/context.py                                     [T7: add extractor on CollectorContext]
  rrxray/pipeline.py                                    [T12, T15: anonymizer registration loop + COLLECTORS/SYNTHESIZERS appends + extractor wire-up]
  templates/report_internal.md.jinja                    [T13: include partial + render Section B narrative]
  roadmap.md                                            [T16: one-line entry post-quality-gate]
```

---

## Task overview

16 tasks. T1-T2 are foundation (new client + extractor). T3-T6 are mechanical scaffolding (schemas, catalog, schema field, config + CLI). T7-T11 build the collector. T12 wires anonymizer registration. T13 ships the renderer partial. T14 ships the synthesizer. T15 registers in pipeline. T16 is the Dale-led quality gate (bounded by sign-off, not time).

| # | Task | Type |
|---|---|---|
| T1 | GeminiClient | Real-logic |
| T2 | Extractors (HaikuExtractor + GeminiFlashExtractor + factory) | Real-logic |
| T3 | LeadershipStabilityData + nested schemas | Mechanical |
| T4 | Role + action catalog | Mechanical |
| T5 | data.py — CollectorOutputs + SynthesizerOutputs additions | Mechanical |
| T6 | Config + CLI `--extractor` flag | Mechanical |
| T7 | Collector skeleton + press release search + extraction | Real-logic |
| T8 | LinkedIn current C-suite search + extraction | Real-logic |
| T9 | Founder tenure inference (F1 + F2) | Real-logic |
| T10 | Name registrations + findings emission | Real-logic |
| T11 | Evidence writing + full `collect()` orchestration | Real-logic |
| T12 | Pipeline anonymizer registration loop | Real-logic |
| T13 | Renderer Module Detail partial + report integration | Mechanical |
| T14 | Synthesizer + prompt template | Real-logic |
| T15 | Pipeline registration (COLLECTORS + SYNTHESIZERS) | Mechanical |
| T16 | Quality gate (Dale-led) | Manual |

**Two-stage review (spec-compliance + code-quality):** apply on real-logic tasks (T1, T2, T7, T8, T9, T10, T11, T12, T14). Skip on mechanical tasks (T3, T4, T5, T6, T13, T15) per Phase 2.1c precedent.

**Local verification after each implementer task:** `uv run pytest -v 2>&1 | tail -3` and confirm test count + pass/fail before dispatching review subagents.

**Baseline test count entering Phase 2.2:** 251 passed, 1 skipped. Expected end state: ~301 passed (50 new tests).

---

## Task 1: GeminiClient

**Files:**
- Modify: `pyproject.toml` (add `google-genai` dependency)
- Create: `rrxray/services/gemini_client.py`
- Create: `tests/test_gemini_client.py`

- [ ] **Step 1: Add google-genai dependency**

```bash
/Users/dalezwizinski/Library/Python/3.9/bin/uv add google-genai
```

Expected: `pyproject.toml` updated with `google-genai >= X.Y.Z`; `uv.lock` updated; install succeeds.

- [ ] **Step 2: Inspect the google-genai SDK to confirm the structured-output method shape**

```bash
/Users/dalezwizinski/Library/Python/3.9/bin/uv run python -c "
from google import genai
import inspect
print('genai.Client signature:')
print(inspect.signature(genai.Client.__init__))
print()
print('models attribute methods:')
client = genai.Client(api_key='test')
methods = [m for m in dir(client.models) if not m.startswith('_')]
print(methods)
print()
print('async aio methods:')
print([m for m in dir(client.aio.models) if not m.startswith('_')])
"
```

Expected: shows `Client(api_key=..., ...)` constructor, `generate_content` method on `client.models`, `client.aio.models.generate_content` for async. If the SDK shape differs from what's documented in this plan, adapt the wrapper accordingly (matches the Phase 2.1a discipline of `inspect`-then-adapt).

- [ ] **Step 3: Write failing tests in `tests/test_gemini_client.py`**

```python
"""GeminiClient: thin async wrapper around google-genai for structured output."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import BaseModel

from rrxray.services.gemini_client import GeminiClient, GeminiError, ParsedResponse


class _DemoSchema(BaseModel):
    name: str
    age: int


@pytest.fixture
def fake_sdk():
    """A MagicMock standing in for the google-genai Client."""
    sdk = MagicMock()
    sdk.aio = MagicMock()
    sdk.aio.models = MagicMock()
    sdk.aio.models.generate_content = AsyncMock()
    return sdk


@pytest.fixture
def client(fake_sdk):
    return GeminiClient(api_key="test-key", _client_factory=lambda: fake_sdk)


def test_complete_structured_returns_parsed_response(client, fake_sdk):
    """Mocked SDK call yields a ParsedResponse with parsed pydantic model."""
    fake_sdk.aio.models.generate_content.return_value = MagicMock(
        parsed=_DemoSchema(name="Alice", age=30),
        text='{"name": "Alice", "age": 30}',
    )

    response = asyncio.run(client.complete_structured(
        system_prompt="You extract names and ages.",
        user_message="Alice is 30.",
        response_schema=_DemoSchema,
        model="gemini-2.0-flash",
    ))

    assert isinstance(response, ParsedResponse)
    assert isinstance(response.parsed, _DemoSchema)
    assert response.parsed.name == "Alice"
    assert response.parsed.age == 30
    assert response.model_used == "gemini-2.0-flash"
    assert response.cache_hit is False


def test_complete_structured_raises_on_sdk_error(client, fake_sdk):
    fake_sdk.aio.models.generate_content.side_effect = RuntimeError("simulated SDK failure")

    with pytest.raises(GeminiError):
        asyncio.run(client.complete_structured(
            system_prompt="x",
            user_message="y",
            response_schema=_DemoSchema,
        ))


def test_complete_structured_uses_injected_factory(fake_sdk):
    """Confirm the test seam works: the factory we pass is the SDK we get."""
    factory_calls = []

    def factory():
        factory_calls.append(True)
        return fake_sdk

    GeminiClient(api_key="test-key", _client_factory=factory)
    assert len(factory_calls) == 1


def test_complete_structured_returns_none_parsed_when_sdk_returns_text_only(client, fake_sdk):
    """If the SDK returns only text (no .parsed), we attempt JSON-parse fallback."""
    fake_sdk.aio.models.generate_content.return_value = MagicMock(
        parsed=None,
        text='{"name": "Bob", "age": 25}',
    )

    response = asyncio.run(client.complete_structured(
        system_prompt="x",
        user_message="y",
        response_schema=_DemoSchema,
    ))
    assert response.parsed.name == "Bob"
    assert response.parsed.age == 25
```

- [ ] **Step 4: Run tests to verify they fail**

```bash
/Users/dalezwizinski/Library/Python/3.9/bin/uv run pytest tests/test_gemini_client.py -v
```

Expected: ERRORS with `ModuleNotFoundError: No module named 'rrxray.services.gemini_client'`.

- [ ] **Step 5: Create `rrxray/services/gemini_client.py`**

```python
"""GeminiClient: thin async wrapper around google-genai for structured output.

Sibling to AnthropicClient. No provider abstraction layer (deferred to Phase 3
per roadmap.md line 87). Used by extraction.GeminiFlashExtractor for press
release / LinkedIn snippet parsing.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

log = logging.getLogger("rrxray.gemini")


class GeminiError(Exception):
    pass


class ParsedResponse(BaseModel):
    parsed: BaseModel
    model_used: str
    cache_hit: bool = False


class GeminiClient:
    def __init__(
        self,
        api_key: str,
        _client_factory: Callable[[], Any] | None = None,
    ):
        """`_client_factory` is a test seam — production defaults to google-genai SDK Client."""
        self.api_key = api_key
        if _client_factory is not None:
            self._sdk = _client_factory()
        else:
            from google import genai
            self._sdk = genai.Client(api_key=api_key)

    async def complete_structured(
        self,
        system_prompt: str,
        user_message: str,
        response_schema: type[BaseModel],
        model: str = "gemini-2.0-flash",
    ) -> ParsedResponse:
        """Structured-output completion. Wraps google-genai's generate_content.

        Returns a ParsedResponse with parsed pydantic model. Raises GeminiError
        on SDK failure (the SDK's own retry behavior runs first; we surface
        terminal errors).
        """
        # Concatenate system + user; google-genai uses role-based contents.
        contents = f"{system_prompt}\n\n{user_message}"
        config = {
            "response_mime_type": "application/json",
            "response_schema": response_schema,
        }

        try:
            response = await self._sdk.aio.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.warning("Gemini generate_content failed: %s", e)
            raise GeminiError(f"generate_content failed: {e}") from e

        # google-genai may return .parsed (preferred) or only .text (JSON string).
        parsed = getattr(response, "parsed", None)
        if parsed is None:
            text = getattr(response, "text", "")
            try:
                parsed = response_schema.model_validate(json.loads(text))
            except Exception as e:
                raise GeminiError(f"Failed to parse Gemini response as {response_schema.__name__}: {e}") from e

        return ParsedResponse(
            parsed=parsed,
            model_used=model,
            cache_hit=False,
        )
```

- [ ] **Step 6: Run tests to verify they pass + ruff**

```bash
/Users/dalezwizinski/Library/Python/3.9/bin/uv run pytest tests/test_gemini_client.py -v
/Users/dalezwizinski/Library/Python/3.9/bin/uv run ruff check rrxray/ tests/
```

Expected: 4 tests pass. Ruff clean. Total project: 255 passed, 1 skipped.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock rrxray/services/gemini_client.py tests/test_gemini_client.py
git commit -m "$(cat <<'EOF'
Add GeminiClient (sibling to AnthropicClient, no abstraction layer)

Thin async wrapper around google-genai for structured-output completion.
No prompt caching, no streaming, no batch — just complete_structured()
that returns a ParsedResponse with a parsed pydantic model.

Used by Phase 2.2 extraction.GeminiFlashExtractor for press release /
LinkedIn snippet parsing when --extractor=gemini-flash is set. Phase 3
will refactor both AnthropicClient and GeminiClient into a unified
services/llm.py provider abstraction; until then they sit side-by-side.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Extractors (HaikuExtractor + GeminiFlashExtractor + factory)

**Files:**
- Create: `rrxray/services/extraction.py`
- Create: `tests/test_extraction.py`

- [ ] **Step 1: Write failing tests in `tests/test_extraction.py`**

```python
"""Extractor tests: HaikuExtractor + GeminiFlashExtractor + make_extractor factory."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import BaseModel

from rrxray.services.extraction import (
    ExecAction,
    ExtractedExecChange,
    ExtractedLinkedInIncumbent,
    GeminiFlashExtractor,
    HaikuExtractor,
    make_extractor,
)


class _FakeAnthropicResponse(BaseModel):
    parsed: ExtractedExecChange | ExtractedLinkedInIncumbent
    model_used: str = "claude-haiku-4-5-20251001"
    cache_hit: bool = False


@pytest.fixture
def fake_anthropic():
    a = MagicMock()
    a.complete_with_cached_system = AsyncMock()
    return a


@pytest.fixture
def fake_gemini():
    g = MagicMock()
    g.complete_structured = AsyncMock()
    return g


def test_haiku_extractor_extracts_hire_announcement(fake_anthropic):
    fake_anthropic.complete_with_cached_system.return_value = _FakeAnthropicResponse(
        parsed=ExtractedExecChange(
            name="Jane Doe",
            role_canonical="cro",
            role_raw="Chief Revenue Officer",
            action=ExecAction.HIRE,
            is_relevant=True,
        ),
    )

    extractor = HaikuExtractor(fake_anthropic)
    result = asyncio.run(extractor.extract_exec_change(
        title="Acme Names Jane Doe as Chief Revenue Officer",
        snippet="Acme Corp today announced the appointment of Jane Doe as CRO.",
    ))

    assert result is not None
    assert result.name == "Jane Doe"
    assert result.role_canonical == "cro"
    assert result.action == ExecAction.HIRE
    assert result.is_relevant is True


def test_haiku_extractor_returns_none_on_irrelevant(fake_anthropic):
    fake_anthropic.complete_with_cached_system.return_value = _FakeAnthropicResponse(
        parsed=ExtractedExecChange(
            name="",
            role_canonical="cro",
            role_raw="",
            action=ExecAction.HIRE,
            is_relevant=False,
        ),
    )

    extractor = HaikuExtractor(fake_anthropic)
    result = asyncio.run(extractor.extract_exec_change(
        title="Acme Q3 Earnings Call",
        snippet="Quarterly results discussed.",
    ))
    assert result is None


def test_haiku_extractor_returns_none_on_anthropic_error(fake_anthropic):
    from rrxray.services.anthropic_client import AnthropicError
    fake_anthropic.complete_with_cached_system.side_effect = AnthropicError("simulated")

    extractor = HaikuExtractor(fake_anthropic)
    result = asyncio.run(extractor.extract_exec_change("title", "snippet"))
    assert result is None


def test_haiku_extractor_extract_linkedin_role(fake_anthropic):
    fake_anthropic.complete_with_cached_system.return_value = _FakeAnthropicResponse(
        parsed=ExtractedLinkedInIncumbent(
            name="Bob Smith",
            role_canonical="cmo",
            role_raw="Chief Marketing Officer",
            is_relevant=True,
        ),
    )

    extractor = HaikuExtractor(fake_anthropic)
    result = asyncio.run(extractor.extract_linkedin_role(
        title="Bob Smith - Chief Marketing Officer at Acme - LinkedIn",
        snippet="Bob Smith. Chief Marketing Officer at Acme Corp. New York, NY.",
        role_query="cmo",
    ))

    assert result is not None
    assert result.name == "Bob Smith"
    assert result.role_canonical == "cmo"


class _FakeGeminiResponse(BaseModel):
    parsed: ExtractedExecChange | ExtractedLinkedInIncumbent
    model_used: str = "gemini-2.0-flash"
    cache_hit: bool = False


def test_gemini_flash_extractor_extracts_hire_announcement(fake_gemini):
    fake_gemini.complete_structured.return_value = _FakeGeminiResponse(
        parsed=ExtractedExecChange(
            name="Jane Doe",
            role_canonical="cro",
            role_raw="Chief Revenue Officer",
            action=ExecAction.HIRE,
            is_relevant=True,
        ),
    )

    extractor = GeminiFlashExtractor(fake_gemini)
    result = asyncio.run(extractor.extract_exec_change(
        title="Acme Names Jane Doe as Chief Revenue Officer",
        snippet="...",
    ))
    assert result is not None
    assert result.name == "Jane Doe"


def test_gemini_flash_extractor_returns_none_on_irrelevant(fake_gemini):
    fake_gemini.complete_structured.return_value = _FakeGeminiResponse(
        parsed=ExtractedExecChange(
            name="",
            role_canonical="cro",
            role_raw="",
            action=ExecAction.HIRE,
            is_relevant=False,
        ),
    )

    extractor = GeminiFlashExtractor(fake_gemini)
    result = asyncio.run(extractor.extract_exec_change("x", "y"))
    assert result is None


def test_gemini_flash_extractor_returns_none_on_gemini_error(fake_gemini):
    from rrxray.services.gemini_client import GeminiError
    fake_gemini.complete_structured.side_effect = GeminiError("simulated")

    extractor = GeminiFlashExtractor(fake_gemini)
    result = asyncio.run(extractor.extract_exec_change("x", "y"))
    assert result is None


def test_make_extractor_picks_haiku_by_default(fake_anthropic, fake_gemini):
    from rrxray.config import Config
    config = Config(domain="example.com", extractor_model="haiku")
    extractor = make_extractor(config, fake_anthropic, fake_gemini)
    assert isinstance(extractor, HaikuExtractor)


def test_make_extractor_picks_gemini_with_flag(fake_anthropic, fake_gemini):
    from rrxray.config import Config
    config = Config(domain="example.com", extractor_model="gemini-flash")
    extractor = make_extractor(config, fake_anthropic, fake_gemini)
    assert isinstance(extractor, GeminiFlashExtractor)


def test_make_extractor_raises_when_gemini_key_missing(fake_anthropic):
    from rrxray.config import Config
    from rrxray.services.extraction import ExtractorConfigError
    config = Config(domain="example.com", extractor_model="gemini-flash")
    with pytest.raises(ExtractorConfigError):
        make_extractor(config, fake_anthropic, gemini=None)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
/Users/dalezwizinski/Library/Python/3.9/bin/uv run pytest tests/test_extraction.py -v
```

Expected: ERRORS with `ModuleNotFoundError: No module named 'rrxray.services.extraction'`. (Some tests also depend on T6's `Config.extractor_model` field — those will fail with ValidationError once the module exists. T6 lands the field; the test file pre-references it. The implementer should run T6 before re-running T2's tests if execution is interleaved; the canonical order in this plan is sequential.)

- [ ] **Step 3: Create `rrxray/services/extraction.py`**

```python
"""LLM-based extraction for press release titles and LinkedIn snippets.

Used by leadership_stability collector to parse unstructured natural-language
content (press releases and LinkedIn search snippets) into structured records.

Phase 2.1c rule "no LLM in collector path" is amended to "no LLM in collector
path unless the data is genuinely unstructured natural language and a
deterministic alternative would degrade quality." Press release name + role +
action extraction is exactly that case; regex coverage is too patchy to be
useful.

Two concrete extractors share a duck-typed interface (no formal Protocol;
defer that to Phase 3's services/llm.py provider abstraction). HaikuExtractor
calls Anthropic Haiku 4.5; GeminiFlashExtractor calls Gemini 2.0 Flash. Both
return None on irrelevant or extraction failure so the collector can iterate
over results without per-call try/except.
"""
from __future__ import annotations

import logging
from enum import StrEnum
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ValidationError

if TYPE_CHECKING:
    from rrxray.config import Config
    from rrxray.services.anthropic_client import AnthropicClient
    from rrxray.services.gemini_client import GeminiClient

log = logging.getLogger("rrxray.extraction")


class ExtractorConfigError(Exception):
    pass


class ExecAction(StrEnum):
    HIRE = "hire"
    DEPARTURE = "departure"
    PROMOTION = "promotion"


RoleCanonical = Literal[
    "ceo", "cro", "vp_sales", "vp_revenue",
    "cmo", "vp_marketing", "founder",
]


class ExtractedExecChange(BaseModel):
    name: str
    role_canonical: RoleCanonical
    role_raw: str
    action: ExecAction
    is_relevant: bool


class ExtractedLinkedInIncumbent(BaseModel):
    name: str
    role_canonical: RoleCanonical
    role_raw: str
    is_relevant: bool


_EXEC_CHANGE_SYSTEM_PROMPT = """You extract structured exec-change records from press release titles and snippets.

Given a title and snippet, identify whether it announces an executive hire, departure, or promotion. If yes, extract the person's name, the role they're moving into (or out of), and the action.

Set is_relevant=True ONLY if both name and role are clearly stated. Set is_relevant=False if the title is not actually announcing an exec change (e.g., quarterly earnings, product launches, partnerships).

Map the role to one of these canonical values:
- ceo
- cro
- vp_sales
- vp_revenue
- cmo
- vp_marketing
- founder

If the role doesn't map to one of these, pick the closest match and let role_raw preserve the original wording. If no match is reasonable, set is_relevant=False.

Action must be one of: hire, departure, promotion. Promotion = internal move (e.g., "promotes X to CRO"). Hire = external (e.g., "names", "appoints", "joins"). Departure = leaving (e.g., "departs", "resigns", "steps down").
"""


_LINKEDIN_INCUMBENT_SYSTEM_PROMPT = """You extract a person's name and current role from a LinkedIn search result.

Given a search result title, snippet, and the role we were searching for, identify whether this result names a current incumbent in that role at the company.

Set is_relevant=True ONLY if both name and role are clearly stated AND the role appears to be current (not a past role or unrelated context).

Map role_canonical to: ceo, cro, vp_sales, vp_revenue, cmo, vp_marketing, founder. role_raw should preserve the wording from the result.
"""


class HaikuExtractor:
    def __init__(self, anthropic: AnthropicClient):
        self.anthropic = anthropic

    async def extract_exec_change(self, title: str, snippet: str) -> ExtractedExecChange | None:
        from rrxray.services.anthropic_client import AnthropicError
        try:
            response = await self.anthropic.complete_with_cached_system(
                system_prompt=_EXEC_CHANGE_SYSTEM_PROMPT,
                user_message=f"Title: {title}\n\nSnippet: {snippet}",
                model="claude-haiku-4-5-20251001",
                response_schema=ExtractedExecChange,
            )
        except (AnthropicError, ValidationError) as e:
            log.debug("Haiku extract_exec_change failed: %s", e)
            return None
        result = response.parsed
        return result if result.is_relevant else None

    async def extract_linkedin_role(
        self, title: str, snippet: str, role_query: str,
    ) -> ExtractedLinkedInIncumbent | None:
        from rrxray.services.anthropic_client import AnthropicError
        try:
            response = await self.anthropic.complete_with_cached_system(
                system_prompt=_LINKEDIN_INCUMBENT_SYSTEM_PROMPT,
                user_message=f"Role we were searching for: {role_query}\n\nTitle: {title}\n\nSnippet: {snippet}",
                model="claude-haiku-4-5-20251001",
                response_schema=ExtractedLinkedInIncumbent,
            )
        except (AnthropicError, ValidationError) as e:
            log.debug("Haiku extract_linkedin_role failed: %s", e)
            return None
        result = response.parsed
        return result if result.is_relevant else None


class GeminiFlashExtractor:
    def __init__(self, gemini: GeminiClient):
        self.gemini = gemini

    async def extract_exec_change(self, title: str, snippet: str) -> ExtractedExecChange | None:
        from rrxray.services.gemini_client import GeminiError
        try:
            response = await self.gemini.complete_structured(
                system_prompt=_EXEC_CHANGE_SYSTEM_PROMPT,
                user_message=f"Title: {title}\n\nSnippet: {snippet}",
                response_schema=ExtractedExecChange,
                model="gemini-2.0-flash",
            )
        except (GeminiError, ValidationError) as e:
            log.debug("Gemini extract_exec_change failed: %s", e)
            return None
        result = response.parsed
        return result if result.is_relevant else None

    async def extract_linkedin_role(
        self, title: str, snippet: str, role_query: str,
    ) -> ExtractedLinkedInIncumbent | None:
        from rrxray.services.gemini_client import GeminiError
        try:
            response = await self.gemini.complete_structured(
                system_prompt=_LINKEDIN_INCUMBENT_SYSTEM_PROMPT,
                user_message=f"Role we were searching for: {role_query}\n\nTitle: {title}\n\nSnippet: {snippet}",
                response_schema=ExtractedLinkedInIncumbent,
                model="gemini-2.0-flash",
            )
        except (GeminiError, ValidationError) as e:
            log.debug("Gemini extract_linkedin_role failed: %s", e)
            return None
        result = response.parsed
        return result if result.is_relevant else None


def make_extractor(
    config: Config,
    anthropic: AnthropicClient,
    gemini: GeminiClient | None,
) -> HaikuExtractor | GeminiFlashExtractor:
    """Factory: picks an extractor based on config.extractor_model.

    Raises ExtractorConfigError if extractor_model='gemini-flash' but gemini is None
    (i.e., GEMINI_API_KEY was not set).
    """
    if config.extractor_model == "gemini-flash":
        if gemini is None:
            raise ExtractorConfigError(
                "extractor_model='gemini-flash' but no GeminiClient available — "
                "set GEMINI_API_KEY in environment or .env."
            )
        return GeminiFlashExtractor(gemini)
    return HaikuExtractor(anthropic)
```

- [ ] **Step 4: Run tests to verify they pass + ruff**

NOTE: This task's tests reference `Config(extractor_model=...)`. T6 adds the `extractor_model` field. The plan's canonical order is: T1 → T2 → T3 → T4 → T5 → T6 → ... so T2 will fail until T6 lands. Document this dependency: at T6 completion, re-run T2 tests.

```bash
/Users/dalezwizinski/Library/Python/3.9/bin/uv run pytest tests/test_extraction.py -v
```

Expected (interleaved with T6): 10 tests pass. Ruff clean. (If T6 hasn't landed yet, expect ValidationError on `extractor_model`; mark this task partially blocked until T6.)

- [ ] **Step 5: Commit (only the extraction module + its tests; defer Config touch to T6)**

```bash
git add rrxray/services/extraction.py tests/test_extraction.py
git commit -m "$(cat <<'EOF'
Add LLM extractor module (HaikuExtractor + GeminiFlashExtractor + factory)

Two duck-typed extractor classes for parsing press release titles and
LinkedIn snippets into structured ExtractedExecChange /
ExtractedLinkedInIncumbent records.

Both extractors return None on irrelevant or extraction failure so the
caller can iterate over results without per-call try/except. The factory
picks one based on config.extractor_model; raises ExtractorConfigError if
gemini-flash is requested but GEMINI_API_KEY is unset.

Phase 3's services/llm.py provider abstraction will subsume both;
defer that until then.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: LeadershipStabilityData + nested schemas

**Files:**
- Create: `rrxray/schemas/leadership_stability.py`
- Create: `tests/test_leadership_stability_schemas.py`

- [ ] **Step 1: Write failing tests in `tests/test_leadership_stability_schemas.py`**

```python
"""Schema round-trip + validation for leadership_stability data shapes."""
from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from rrxray.schemas.leadership_stability import (
    CurrentIncumbent,
    ExecAction,
    ExecChange,
    FounderTenure,
    LeadershipStabilityData,
    NameRegistration,
)


def test_exec_change_minimal():
    e = ExecChange(
        name="Jane Doe",
        role_canonical="cro",
        role_raw="Chief Revenue Officer",
        action=ExecAction.HIRE,
        press_url="https://example.com/press/1",
        press_title="Acme Names Jane Doe as CRO",
    )
    assert e.name == "Jane Doe"
    assert e.action == ExecAction.HIRE
    assert e.occurred_at is None


def test_exec_change_validates_canonical_role():
    with pytest.raises(ValidationError):
        ExecChange(
            name="x",
            role_canonical="not_a_role",  # type: ignore[arg-type]
            role_raw="x",
            action=ExecAction.HIRE,
            press_url="x",
            press_title="x",
        )


def test_current_incumbent_default_high_confidence():
    c = CurrentIncumbent(name="Bob", role_canonical="cmo", role_raw="CMO")
    assert c.confidence == "high"


def test_founder_tenure_default_unknown_source():
    f = FounderTenure()
    assert f.source == "unknown"
    assert f.inferred_year is None


def test_name_registration_default_whitelist_false():
    """Default whitelist is False (safer default) per spec."""
    n = NameRegistration(name="Bob Smith", role_descriptor="Acme's CMO")
    assert n.whitelist is False


def test_leadership_stability_data_defaults_empty():
    d = LeadershipStabilityData()
    assert d.exec_changes == []
    assert d.current_incumbents == []
    assert d.founder_tenure is None
    assert d.name_registrations == []
    assert d.findings == []
    assert d.gaps == []
    assert d.discovery_questions == []
    assert d.sources == []


def test_leadership_stability_data_round_trips():
    d = LeadershipStabilityData(
        exec_changes=[
            ExecChange(
                name="Jane Doe",
                role_canonical="cro",
                role_raw="Chief Revenue Officer",
                action=ExecAction.HIRE,
                press_url="https://example.com/p/1",
                press_title="Acme Names Jane Doe as CRO",
            ),
        ],
        current_incumbents=[
            CurrentIncumbent(name="Jane Doe", role_canonical="cro", role_raw="CRO", confidence="high"),
        ],
        founder_tenure=FounderTenure(inferred_year=2018, source="about_page", raw_evidence="Founded in 2018"),
        name_registrations=[
            NameRegistration(name="Jane Doe", role_descriptor="Acme's CRO", whitelist=True),
        ],
    )
    serialized = d.model_dump_json()
    restored = LeadershipStabilityData.model_validate(json.loads(serialized))
    assert len(restored.exec_changes) == 1
    assert restored.exec_changes[0].name == "Jane Doe"
    assert restored.founder_tenure.inferred_year == 2018
    assert restored.name_registrations[0].whitelist is True
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
/Users/dalezwizinski/Library/Python/3.9/bin/uv run pytest tests/test_leadership_stability_schemas.py -v
```

Expected: ERRORS with `ModuleNotFoundError: No module named 'rrxray.schemas.leadership_stability'`.

- [ ] **Step 3: Create `rrxray/schemas/leadership_stability.py`**

```python
"""Schemas specific to the leadership_stability collector."""
from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel

from rrxray.schemas._shared import Finding, SourceCitation


RoleCanonical = Literal[
    "ceo", "cro", "vp_sales", "vp_revenue",
    "cmo", "vp_marketing", "founder",
]


class ExecAction(StrEnum):
    HIRE = "hire"
    DEPARTURE = "departure"
    PROMOTION = "promotion"


class ExecChange(BaseModel):
    name: str
    role_canonical: RoleCanonical
    role_raw: str
    action: ExecAction
    occurred_at: date | None = None
    press_url: str
    press_title: str


class CurrentIncumbent(BaseModel):
    name: str
    role_canonical: RoleCanonical
    role_raw: str
    linkedin_url: str | None = None
    confidence: Literal["high", "low"] = "high"


class FounderTenure(BaseModel):
    inferred_year: int | None = None
    source: Literal["about_page", "wayback_homepage", "unknown"] = "unknown"
    raw_evidence: str | None = None


class NameRegistration(BaseModel):
    name: str
    role_descriptor: str
    whitelist: bool = False


class LeadershipStabilityData(BaseModel):
    exec_changes: list[ExecChange] = []
    current_incumbents: list[CurrentIncumbent] = []
    founder_tenure: FounderTenure | None = None
    name_registrations: list[NameRegistration] = []
    findings: list[Finding] = []
    gaps: list[str] = []
    discovery_questions: list[str] = []
    sources: list[SourceCitation] = []
```

- [ ] **Step 4: Run tests + ruff**

```bash
/Users/dalezwizinski/Library/Python/3.9/bin/uv run pytest tests/test_leadership_stability_schemas.py -v
/Users/dalezwizinski/Library/Python/3.9/bin/uv run ruff check rrxray/ tests/
```

Expected: 7 tests pass. Ruff clean.

- [ ] **Step 5: Commit**

```bash
git add rrxray/schemas/leadership_stability.py tests/test_leadership_stability_schemas.py
git commit -m "Add LeadershipStabilityData and nested schemas"
```

---

## Task 4: Role + action catalog

**Files:**
- Create: `rrxray/collectors/_leadership_stability_catalog.py`
- Create: `tests/test_leadership_stability_catalog.py`

- [ ] **Step 1: Write failing tests in `tests/test_leadership_stability_catalog.py`**

```python
"""Catalog integrity tests for leadership_stability."""
from __future__ import annotations

from rrxray.collectors._leadership_stability_catalog import (
    FOUNDED_YEAR_PATTERNS,
    LEADERSHIP_ROLES,
    PRESS_ACTION_QUERIES,
    PRESS_LOOKBACK_MONTHS,
    RECENT_THRESHOLD_DAYS,
    ROLE_DISPLAY,
)


def test_seven_canonical_roles():
    canonicals = [c for c, _ in LEADERSHIP_ROLES]
    assert canonicals == ["ceo", "cro", "vp_sales", "vp_revenue", "cmo", "vp_marketing", "founder"]


def test_three_action_query_groups():
    actions = [a for a, _ in PRESS_ACTION_QUERIES]
    assert set(actions) == {"hire", "departure", "promotion"}


def test_role_display_covers_all_canonicals():
    for canonical, _ in LEADERSHIP_ROLES:
        assert canonical in ROLE_DISPLAY, f"missing display for {canonical}"


def test_thresholds_are_sensible():
    assert PRESS_LOOKBACK_MONTHS == 18
    assert RECENT_THRESHOLD_DAYS == 270


def test_role_search_keywords_quoted():
    """Each search keyword fragment uses quoted phrases for multi-word terms."""
    for canonical, query in LEADERSHIP_ROLES:
        # Single-word canonicals (founder, ceo, cmo, cro) may be unquoted.
        # Multi-word phrases must be quoted.
        if " " in query and '"' not in query:
            raise AssertionError(f"{canonical}: multi-word query must use quoted phrases: {query!r}")


def test_founded_year_patterns_match_common_phrasings():
    import re
    text_samples = [
        ("Founded in 2018 by...", "2018"),
        ("Since 2015, we've...", "2015"),
        ("Founded 2020.", "2020"),
        ("Established in 2010", "2010"),
        ("Established 2012", "2012"),
    ]
    for text, expected_year in text_samples:
        matched = False
        for pat in FOUNDED_YEAR_PATTERNS:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                assert m.group(1) == expected_year, f"{text!r} matched {pat} but got {m.group(1)}"
                matched = True
                break
        assert matched, f"No pattern matched {text!r}"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
/Users/dalezwizinski/Library/Python/3.9/bin/uv run pytest tests/test_leadership_stability_catalog.py -v
```

Expected: ERRORS with `ModuleNotFoundError`.

- [ ] **Step 3: Create `rrxray/collectors/_leadership_stability_catalog.py`**

```python
"""Static catalog data for the leadership_stability collector.

Hardcoded keyword catalogs and threshold constants. No LLM in this module;
catalog data is deterministic.
"""
from __future__ import annotations


# (canonical, LinkedIn search keyword fragment)
LEADERSHIP_ROLES: list[tuple[str, str]] = [
    ("ceo",            '"CEO"'),
    ("cro",            '"CRO" OR "Chief Revenue Officer"'),
    ("vp_sales",       '"VP Sales" OR "VP of Sales" OR "Head of Sales"'),
    ("vp_revenue",     '"VP Revenue" OR "VP of Revenue" OR "Head of Revenue"'),
    ("cmo",            '"CMO" OR "Chief Marketing Officer"'),
    ("vp_marketing",   '"VP Marketing" OR "VP of Marketing" OR "Head of Marketing"'),
    ("founder",        '"Founder" OR "Co-founder"'),
]


# (action label, query keywords for Google search)
PRESS_ACTION_QUERIES: list[tuple[str, str]] = [
    ("hire",      "appoints OR names OR hires OR welcomes OR joins"),
    ("departure", 'departs OR resigns OR "steps down" OR "stepping down"'),
    ("promotion", "promoted OR promotion"),
]


# canonical → display string for findings text + role descriptors
ROLE_DISPLAY: dict[str, str] = {
    "ceo":          "CEO",
    "cro":          "CRO",
    "vp_sales":     "VP Sales",
    "vp_revenue":   "VP Revenue",
    "cmo":          "CMO",
    "vp_marketing": "VP Marketing",
    "founder":      "founder",
}


PRESS_LOOKBACK_MONTHS: int = 18
RECENT_THRESHOLD_DAYS: int = 270  # ~9 months


# Regex patterns for inferring founding year from /about page copy.
FOUNDED_YEAR_PATTERNS: list[str] = [
    r"founded\s+in\s+(\d{4})",
    r"since\s+(\d{4})",
    r"founded\s+(\d{4})",
    r"established\s+in\s+(\d{4})",
    r"established\s+(\d{4})",
]
```

- [ ] **Step 4: Run tests + ruff**

```bash
/Users/dalezwizinski/Library/Python/3.9/bin/uv run pytest tests/test_leadership_stability_catalog.py -v
/Users/dalezwizinski/Library/Python/3.9/bin/uv run ruff check rrxray/ tests/
```

Expected: 6 tests pass. Ruff clean.

- [ ] **Step 5: Commit**

```bash
git add rrxray/collectors/_leadership_stability_catalog.py tests/test_leadership_stability_catalog.py
git commit -m "Add leadership_stability catalog (roles, action queries, thresholds, patterns)"
```

---

## Task 5: data.py — CollectorOutputs + SynthesizerOutputs additions

**Files:**
- Modify: `rrxray/schemas/data.py` (add `leadership_stability` field; add `ObservedStabilityTrajectoryNarrative`; extend `SynthesizerOutputs`; update bottom-of-file imports + model_rebuild)

- [ ] **Step 1: Read current `rrxray/schemas/data.py` to confirm shape**

Already reviewed; pattern: forward-ref string in CollectorOutputs, bottom-of-file import, single `CollectorOutputs.model_rebuild()` call.

- [ ] **Step 2: Edit `rrxray/schemas/data.py`**

Replace the `CollectorOutputs` definition to add the new field:

```python
class CollectorOutputs(BaseModel):
    """One field per collector. None = not run or failed gracefully."""
    model_config = ConfigDict(validate_assignment=True)
    pricing_packaging: "PricingPackagingData | None" = None  # forward ref
    tech_stack: "TechStackData | None" = None  # forward ref
    revenue_motion: "RevenueMotionData | None" = None  # forward ref
    leadership_stability: "LeadershipStabilityData | None" = None  # forward ref
```

Add the new narrative class after `ObservedGtmMotionNarrative`:

```python
class ObservedStabilityTrajectoryNarrative(BaseModel):
    narrative_paragraphs: list[str]
    findings: list[Finding] = []
    gaps: list[str] = []
    discovery_questions: list[str] = []
    model_used: str
    cache_hit: bool
```

Replace `SynthesizerOutputs`:

```python
class SynthesizerOutputs(BaseModel):
    model_config = ConfigDict(validate_assignment=True)
    observed_gtm_motion: ObservedGtmMotionNarrative | None = None
    observed_stability_trajectory: ObservedStabilityTrajectoryNarrative | None = None
```

Add the bottom-of-file import + model_rebuild update:

```python
# Resolve forward references
from rrxray.schemas.leadership_stability import LeadershipStabilityData  # noqa: E402
from rrxray.schemas.pricing_packaging import PricingPackagingData  # noqa: E402
from rrxray.schemas.revenue_motion import RevenueMotionData  # noqa: E402
from rrxray.schemas.tech_stack import TechStackData  # noqa: E402

CollectorOutputs.model_rebuild()
```

- [ ] **Step 3: Add a round-trip test to existing data tests**

Append to `tests/test_data.py` (or create if missing — check existing layout first):

```python
def test_data_json_round_trips_with_leadership_stability():
    """XrayData round-trips with leadership_stability collector output populated."""
    from rrxray.schemas.leadership_stability import LeadershipStabilityData, FounderTenure
    from rrxray.schemas.data import CollectorOutputs, XrayData, RunMetadata, InputParams
    from datetime import datetime, UTC

    data = XrayData(
        domain="example.com",
        run_metadata=RunMetadata(
            timestamp=datetime.now(UTC),
            tool_version="0.1",
            modes_built=["internal"],
            model_used="claude-sonnet-4-6",
        ),
        inputs=InputParams(domain="example.com"),
        collectors=CollectorOutputs(
            leadership_stability=LeadershipStabilityData(
                founder_tenure=FounderTenure(inferred_year=2018, source="about_page"),
            ),
        ),
    )
    serialized = data.model_dump_json()
    import json
    restored = XrayData.model_validate(json.loads(serialized))
    assert restored.collectors.leadership_stability.founder_tenure.inferred_year == 2018
```

- [ ] **Step 4: Run full test suite + ruff**

```bash
/Users/dalezwizinski/Library/Python/3.9/bin/uv run pytest -v 2>&1 | tail -3
/Users/dalezwizinski/Library/Python/3.9/bin/uv run ruff check rrxray/ tests/
```

Expected: all tests pass. Ruff clean.

- [ ] **Step 5: Commit**

```bash
git add rrxray/schemas/data.py tests/test_data.py
git commit -m "Add leadership_stability + observed_stability_trajectory fields to data.py"
```

---

## Task 6: Config + CLI `--extractor` flag

**Files:**
- Modify: `rrxray/config.py` (add `gemini_api_key` + `extractor_model` fields)
- Modify: `rrxray/cli.py` (add `--extractor` flag plumbed into config)

- [ ] **Step 1: Edit `rrxray/config.py`**

Add `gemini_api_key` after the existing API-key fields:

```python
    # API keys (loaded from bare env names)
    anthropic_api_key: SecretStr | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    firecrawl_api_key: SecretStr | None = Field(default=None, alias="FIRECRAWL_API_KEY")
    gamma_api_key: SecretStr | None = Field(default=None, alias="GAMMA_API_KEY")
    gemini_api_key: SecretStr | None = Field(default=None, alias="GEMINI_API_KEY")
```

Add `extractor_model` field after the existing `model` field:

```python
    model: str = "claude-sonnet-4-6"
    extractor_model: Literal["haiku", "gemini-flash"] = "haiku"
```

- [ ] **Step 2: Edit `rrxray/cli.py`** — add `--extractor` flag to the `run` command

Find the existing `run` command's option block. Add:

```python
    extractor: str = typer.Option(
        "haiku",
        "--extractor",
        help="LLM model used for press-release / LinkedIn extraction in leadership_stability. "
             "Choices: haiku (default), gemini-flash. gemini-flash requires GEMINI_API_KEY.",
    ),
```

In the `run` function body, pass `extractor` to `_build_config`:

```python
    config = _build_config(
        domain=domain,
        ...,
        extractor_model=extractor,
    )
```

- [ ] **Step 3: Add tests**

Append to `tests/test_config.py` (or create if missing — check existing layout):

```python
def test_extractor_model_default_haiku():
    from rrxray.config import Config
    c = Config(domain="example.com")
    assert c.extractor_model == "haiku"


def test_extractor_model_can_be_gemini_flash():
    from rrxray.config import Config
    c = Config(domain="example.com", extractor_model="gemini-flash")
    assert c.extractor_model == "gemini-flash"


def test_extractor_model_rejects_invalid():
    from rrxray.config import Config
    from pydantic import ValidationError
    import pytest
    with pytest.raises(ValidationError):
        Config(domain="example.com", extractor_model="claude-opus")
```

Append to `tests/test_cli.py` (or extend existing):

```python
def test_run_command_accepts_extractor_flag():
    from typer.testing import CliRunner
    from rrxray.cli import app
    runner = CliRunner()
    result = runner.invoke(app, ["run", "--domain", "example.com", "--dry-run", "--extractor", "gemini-flash"])
    assert result.exit_code == 0, result.stdout
    # Dry-run plan should mention the chosen extractor (or at minimum not error).
```

- [ ] **Step 4: Run tests + ruff + re-run T2 tests now that Config has extractor_model**

```bash
/Users/dalezwizinski/Library/Python/3.9/bin/uv run pytest tests/test_config.py tests/test_cli.py tests/test_extraction.py -v
/Users/dalezwizinski/Library/Python/3.9/bin/uv run ruff check rrxray/ tests/
```

Expected: T2 extraction tests now all pass (the Config dependency is satisfied). New config + cli tests pass. Ruff clean.

- [ ] **Step 5: Commit**

```bash
git add rrxray/config.py rrxray/cli.py tests/test_config.py tests/test_cli.py
git commit -m "Add GEMINI_API_KEY config + --extractor CLI flag"
```

---

## Task 7: Collector skeleton + press release search + extraction

**Files:**
- Modify: `rrxray/context.py` (add `extractor` field to `CollectorContext`)
- Create: `rrxray/collectors/leadership_stability.py` (initial skeleton with press search + extraction)
- Create: `tests/test_leadership_stability.py`
- Create: `tests/fixtures/synthetic/leadership_stability/press_search_hires_response.json`
- Create: `tests/fixtures/synthetic/leadership_stability/press_search_departures_response.json`
- Create: `tests/fixtures/synthetic/leadership_stability/press_search_promotions_response.json`

- [ ] **Step 1: Edit `rrxray/context.py`** — add extractor

```python
if TYPE_CHECKING:
    from rrxray.config import Config
    from rrxray.schemas.data import CollectorOutputs
    from rrxray.services.anthropic_client import AnthropicClient
    from rrxray.services.extraction import GeminiFlashExtractor, HaikuExtractor
    from rrxray.services.firecrawl_client import FirecrawlClient
    from rrxray.services.wayback_client import WaybackClient
    from rrxray.voice.anonymizer import Anonymizer
    from rrxray.voice.rr_voice import VoicePostProcessor


@dataclass(frozen=True)
class CollectorContext:
    domain: str
    company_name: str | None
    firecrawl: FirecrawlClient
    wayback: WaybackClient
    evidence_dir: Path
    config: Config
    extractor: HaikuExtractor | GeminiFlashExtractor | None = None
```

(Optional `None` default keeps existing tests that construct CollectorContext without an extractor working. Real pipeline runs always pass one in.)

- [ ] **Step 2: Create the three press-search fixtures**

`tests/fixtures/synthetic/leadership_stability/press_search_hires_response.json`:

```json
[
  {"url": "https://example.com/press/cro-hire", "title": "Acme Names Jane Doe as Chief Revenue Officer", "description": "Acme Corp today announced the appointment of Jane Doe as CRO, effective March 1, 2026."},
  {"url": "https://example.com/press/vp-sales", "title": "Acme Welcomes Bob Smith as VP of Sales", "description": "Acme appointed Bob Smith as VP Sales in early 2026."},
  {"url": "https://example.com/press/cmo-hire", "title": "Sara Lee Joins Acme as Chief Marketing Officer", "description": "Veteran marketer Sara Lee starts at Acme as CMO."},
  {"url": "https://example.com/press/q3-earnings", "title": "Acme Reports Q3 Earnings", "description": "Strong revenue growth in Q3."}
]
```

`tests/fixtures/synthetic/leadership_stability/press_search_departures_response.json`:

```json
[
  {"url": "https://example.com/press/cmo-departs", "title": "Sara Lee Departs Acme After Three Years", "description": "Acme CMO Sara Lee is stepping down."},
  {"url": "https://example.com/press/cro-resigns", "title": "Acme CRO Mike Jones Resigns", "description": "Mike Jones, who joined as CRO in 2024, resigned today."}
]
```

`tests/fixtures/synthetic/leadership_stability/press_search_promotions_response.json`:

```json
[
  {"url": "https://example.com/press/promotion", "title": "Acme Promotes Lisa Park to Chief Revenue Officer", "description": "Acme today promoted Lisa Park, formerly VP of Sales, to CRO."}
]
```

- [ ] **Step 3: Write failing tests in `tests/test_leadership_stability.py`** — collector skeleton + press search

```python
"""Tests for leadership_stability collector — press release path."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from rrxray.collectors import leadership_stability
from rrxray.collectors.leadership_stability import (
    _extract_exec_changes,
    _search_press_releases,
)
from rrxray.schemas.leadership_stability import ExecAction


FIXTURES = Path(__file__).parent / "fixtures" / "synthetic" / "leadership_stability"


def _load_search_response(name: str):
    """Load a search-response fixture as a list of dicts."""
    return json.loads((FIXTURES / name).read_text())


def _make_search_results(payload):
    from rrxray.services.firecrawl_client import SearchResult
    return [SearchResult(**r) for r in payload]


@pytest.fixture
def fake_firecrawl():
    f = MagicMock()
    f.search = AsyncMock()
    return f


def test_collector_module_has_NAME():
    assert leadership_stability.NAME == "leadership_stability"


def test_search_press_releases_runs_three_action_queries(fake_firecrawl):
    fake_firecrawl.search.side_effect = [
        _make_search_results(_load_search_response("press_search_hires_response.json")),
        _make_search_results(_load_search_response("press_search_departures_response.json")),
        _make_search_results(_load_search_response("press_search_promotions_response.json")),
    ]

    results = asyncio.run(_search_press_releases(fake_firecrawl, company="Acme"))

    assert fake_firecrawl.search.call_count == 3
    # Verify the three action keywords appear in the queries
    queries = [call.args[0] for call in fake_firecrawl.search.call_args_list]
    assert any("appoints" in q.lower() for q in queries)
    assert any("departs" in q.lower() for q in queries)
    assert any("promoted" in q.lower() for q in queries)


def test_search_press_releases_dedupes_by_url(fake_firecrawl):
    """Same URL across two action queries appears once in the result list."""
    fake_firecrawl.search.side_effect = [
        _make_search_results([
            {"url": "https://example.com/press/1", "title": "A", "description": "B"},
        ]),
        _make_search_results([
            {"url": "https://example.com/press/1", "title": "A", "description": "B"},  # duplicate
            {"url": "https://example.com/press/2", "title": "C", "description": "D"},
        ]),
        _make_search_results([]),
    ]

    results = asyncio.run(_search_press_releases(fake_firecrawl, company="Acme"))

    urls = [r.url for r in results]
    assert urls == ["https://example.com/press/1", "https://example.com/press/2"]


def test_search_press_releases_handles_failure_gracefully(fake_firecrawl):
    """One action-query failure does not abort other action queries."""
    from rrxray.services.firecrawl_client import FirecrawlError

    fake_firecrawl.search.side_effect = [
        _make_search_results(_load_search_response("press_search_hires_response.json")),
        FirecrawlError("simulated departures failure"),
        _make_search_results(_load_search_response("press_search_promotions_response.json")),
    ]

    results = asyncio.run(_search_press_releases(fake_firecrawl, company="Acme"))
    # Got hires + promotions but not departures
    assert len(results) >= 1
    assert fake_firecrawl.search.call_count == 3


def test_extract_exec_changes_filters_irrelevant():
    """Extractor returning is_relevant=False results are dropped."""
    from rrxray.services.extraction import ExtractedExecChange
    from rrxray.services.firecrawl_client import SearchResult

    results = [
        SearchResult(url="u1", title="Acme Names Jane Doe as CRO", description="..."),
        SearchResult(url="u2", title="Acme Q3 Earnings Call", description="..."),
    ]

    extractor = MagicMock()
    extractor.extract_exec_change = AsyncMock(side_effect=[
        ExtractedExecChange(name="Jane Doe", role_canonical="cro", role_raw="CRO", action=ExecAction.HIRE, is_relevant=True),
        None,  # irrelevant
    ])

    changes = asyncio.run(_extract_exec_changes(results, extractor))

    assert len(changes) == 1
    assert changes[0].name == "Jane Doe"
    assert changes[0].press_url == "u1"


def test_extract_exec_changes_handles_extractor_none():
    """Extractor returning None for a result skips it without error."""
    from rrxray.services.firecrawl_client import SearchResult

    results = [
        SearchResult(url="u1", title="x", description="y"),
        SearchResult(url="u2", title="x", description="y"),
    ]

    extractor = MagicMock()
    extractor.extract_exec_change = AsyncMock(side_effect=[None, None])

    changes = asyncio.run(_extract_exec_changes(results, extractor))
    assert changes == []
```

- [ ] **Step 4: Run tests to verify they fail**

```bash
/Users/dalezwizinski/Library/Python/3.9/bin/uv run pytest tests/test_leadership_stability.py -v
```

Expected: ERRORS / failures with `ModuleNotFoundError: No module named 'rrxray.collectors.leadership_stability'`.

- [ ] **Step 5: Create `rrxray/collectors/leadership_stability.py` (initial skeleton)**

```python
"""leadership_stability collector — first Section B signal.

Surfaces exec-change history (press search), current C-suite (LinkedIn search),
and founder tenure (/about scrape with Wayback fallback). Populates the
anonymizer name registry via name_registrations on the schema; pipeline
applies side effects post-collection.

LLM is used in this collector path for press / LinkedIn snippet extraction
(see rrxray/services/extraction.py for the rule amendment rationale).
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from rrxray.collectors._leadership_stability_catalog import (
    PRESS_ACTION_QUERIES,
)
from rrxray.schemas.leadership_stability import (
    ExecChange,
    LeadershipStabilityData,
)

if TYPE_CHECKING:
    from rrxray.context import CollectorContext
    from rrxray.services.extraction import GeminiFlashExtractor, HaikuExtractor
    from rrxray.services.firecrawl_client import FirecrawlClient, SearchResult


NAME = "leadership_stability"
log = logging.getLogger(f"rrxray.collectors.{NAME}")


async def _search_press_releases(
    firecrawl: FirecrawlClient, company: str,
) -> list[SearchResult]:
    """Run 3 per-action queries against Firecrawl search; dedupe by URL.

    Each action-query failure is logged and skipped; remaining queries continue.
    Returns the deduped union of all successful queries.
    """
    from rrxray.services.firecrawl_client import FirecrawlError

    seen_urls: set[str] = set()
    all_results: list[SearchResult] = []

    for action_label, action_keywords in PRESS_ACTION_QUERIES:
        query = f'"{company}" ({action_keywords}) (CEO OR CRO OR "Chief Revenue" OR "VP Sales" OR "VP of Sales" OR CMO OR "Chief Marketing" OR "VP Marketing" OR "VP of Marketing" OR Founder)'
        try:
            results = await firecrawl.search(query, limit=10)
        except FirecrawlError as e:
            log.warning("press search failed for action=%s: %s", action_label, e)
            continue

        for r in results:
            if r.url in seen_urls:
                continue
            seen_urls.add(r.url)
            all_results.append(r)

    return all_results


async def _extract_exec_changes(
    results: list[SearchResult],
    extractor: HaikuExtractor | GeminiFlashExtractor,
) -> list[ExecChange]:
    """Per-result extraction; filter is_relevant=False; preserve URL + title."""
    changes: list[ExecChange] = []
    for r in results:
        extracted = await extractor.extract_exec_change(r.title, r.description)
        if extracted is None:
            continue
        changes.append(ExecChange(
            name=extracted.name,
            role_canonical=extracted.role_canonical,
            role_raw=extracted.role_raw,
            action=extracted.action,
            occurred_at=None,  # Phase 2.2-deep may extract from snippet metadata
            press_url=r.url,
            press_title=r.title,
        ))
    return changes


async def collect(ctx: CollectorContext) -> LeadershipStabilityData:
    """Orchestrator. Phase 2.2 T7-T11 incrementally fills this in."""
    company = ctx.company_name or ctx.domain.split(".")[0].title()
    if ctx.extractor is None:
        return LeadershipStabilityData(
            findings=[],  # T10 will fill in graceful-degradation finding
        )

    press_results = await _search_press_releases(ctx.firecrawl, company)
    exec_changes = await _extract_exec_changes(press_results, ctx.extractor)

    # T8-T11 fill in the rest
    return LeadershipStabilityData(
        exec_changes=exec_changes,
    )
```

- [ ] **Step 6: Run tests to verify they pass + ruff**

```bash
/Users/dalezwizinski/Library/Python/3.9/bin/uv run pytest tests/test_leadership_stability.py -v
/Users/dalezwizinski/Library/Python/3.9/bin/uv run ruff check rrxray/ tests/
```

Expected: 6 tests pass. Ruff clean.

- [ ] **Step 7: Commit**

```bash
git add rrxray/context.py rrxray/collectors/leadership_stability.py tests/test_leadership_stability.py tests/fixtures/synthetic/leadership_stability/
git commit -m "$(cat <<'EOF'
Add leadership_stability collector skeleton with press release search

Implements _search_press_releases (3 per-action queries, deduped by URL,
graceful per-query failure) and _extract_exec_changes (per-result LLM
extraction, irrelevant-filter, URL/title preservation).

T8-T11 add LinkedIn current C-suite, founder tenure, name registrations,
findings, and full collect() orchestration.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: LinkedIn current C-suite search + extraction

**Files:**
- Modify: `rrxray/collectors/leadership_stability.py` (add `_search_linkedin_incumbents` + `_extract_current_incumbents`)
- Modify: `tests/test_leadership_stability.py`
- Create: `tests/fixtures/synthetic/leadership_stability/linkedin_cro_response.json`
- Create: `tests/fixtures/synthetic/leadership_stability/linkedin_cmo_response.json`
- Create: `tests/fixtures/synthetic/leadership_stability/linkedin_empty_response.json`

- [ ] **Step 1: Create the LinkedIn fixtures**

`tests/fixtures/synthetic/leadership_stability/linkedin_cro_response.json`:

```json
[
  {"url": "https://www.linkedin.com/in/jane-doe-cro", "title": "Jane Doe — Chief Revenue Officer at Acme Corp — LinkedIn", "description": "Jane Doe. CRO at Acme Corp. New York, NY. Greater New York Area."},
  {"url": "https://www.linkedin.com/in/random-person", "title": "Random Person — VP Sales at Other Co — LinkedIn", "description": "Random Person. VP Sales at Other Co (not the company we asked about)."}
]
```

`tests/fixtures/synthetic/leadership_stability/linkedin_cmo_response.json`:

```json
[
  {"url": "https://www.linkedin.com/posts/sara-lee_cmo-acme-activity-12345", "title": "Sara Lee — Chief Marketing Officer at Acme — LinkedIn", "description": "Sara Lee. CMO at Acme Corp."}
]
```

`tests/fixtures/synthetic/leadership_stability/linkedin_empty_response.json`:

```json
[]
```

- [ ] **Step 2: Append failing tests to `tests/test_leadership_stability.py`**

```python
def test_search_linkedin_incumbents_runs_seven_role_queries(fake_firecrawl):
    from rrxray.collectors.leadership_stability import _search_linkedin_incumbents

    fake_firecrawl.search.side_effect = [
        _make_search_results(_load_search_response("linkedin_cro_response.json")),
        _make_search_results(_load_search_response("linkedin_empty_response.json")),
        _make_search_results(_load_search_response("linkedin_empty_response.json")),
        _make_search_results(_load_search_response("linkedin_empty_response.json")),
        _make_search_results(_load_search_response("linkedin_cmo_response.json")),
        _make_search_results(_load_search_response("linkedin_empty_response.json")),
        _make_search_results(_load_search_response("linkedin_empty_response.json")),
    ]

    results_by_role = asyncio.run(_search_linkedin_incumbents(fake_firecrawl, company="Acme"))

    assert fake_firecrawl.search.call_count == 7
    assert set(results_by_role.keys()) == {"ceo", "cro", "vp_sales", "vp_revenue", "cmo", "vp_marketing", "founder"}
    assert len(results_by_role["cro"]) == 2  # CRO fixture had 2 results
    assert len(results_by_role["cmo"]) == 1


def test_search_linkedin_incumbents_handles_per_role_failure(fake_firecrawl):
    from rrxray.collectors.leadership_stability import _search_linkedin_incumbents
    from rrxray.services.firecrawl_client import FirecrawlError

    # First role (ceo) fails; rest return empty
    fake_firecrawl.search.side_effect = [
        FirecrawlError("simulated"),
    ] + [_make_search_results([])] * 6

    results_by_role = asyncio.run(_search_linkedin_incumbents(fake_firecrawl, company="Acme"))

    # Failed role gets empty list, not missing key
    assert results_by_role["ceo"] == []
    assert fake_firecrawl.search.call_count == 7


def test_extract_current_incumbents_dedupes_by_role_name():
    """Same (role, name) returned by LinkedIn search across queries: one record."""
    from rrxray.collectors.leadership_stability import _extract_current_incumbents
    from rrxray.services.extraction import ExtractedLinkedInIncumbent
    from rrxray.services.firecrawl_client import SearchResult

    results_by_role = {
        "cro": [
            SearchResult(url="https://www.linkedin.com/in/jane-doe-1", title="Jane Doe CRO", description="..."),
            SearchResult(url="https://www.linkedin.com/in/jane-doe-2", title="Jane Doe CRO", description="..."),
        ],
        "cmo": [],
        "ceo": [],
        "vp_sales": [],
        "vp_revenue": [],
        "vp_marketing": [],
        "founder": [],
    }

    extractor = MagicMock()
    extractor.extract_linkedin_role = AsyncMock(side_effect=[
        ExtractedLinkedInIncumbent(name="Jane Doe", role_canonical="cro", role_raw="CRO", is_relevant=True),
        ExtractedLinkedInIncumbent(name="Jane Doe", role_canonical="cro", role_raw="CRO", is_relevant=True),
    ])

    incumbents = asyncio.run(_extract_current_incumbents(results_by_role, extractor))

    assert len(incumbents) == 1
    assert incumbents[0].name == "Jane Doe"
    assert incumbents[0].role_canonical == "cro"


def test_extract_current_incumbents_marks_post_url_low_confidence():
    """LinkedIn /posts/ URL gets confidence='low'; /in/ URL gets confidence='high'."""
    from rrxray.collectors.leadership_stability import _extract_current_incumbents
    from rrxray.services.extraction import ExtractedLinkedInIncumbent
    from rrxray.services.firecrawl_client import SearchResult

    results_by_role = {
        "cmo": [
            SearchResult(url="https://www.linkedin.com/posts/sara-lee_cmo-acme-activity-12345", title="Sara Lee CMO", description="..."),
        ],
        "cro": [
            SearchResult(url="https://www.linkedin.com/in/bob-cro", title="Bob CRO", description="..."),
        ],
        "ceo": [],
        "vp_sales": [],
        "vp_revenue": [],
        "vp_marketing": [],
        "founder": [],
    }

    extractor = MagicMock()
    extractor.extract_linkedin_role = AsyncMock(side_effect=[
        ExtractedLinkedInIncumbent(name="Sara Lee", role_canonical="cmo", role_raw="CMO", is_relevant=True),
        ExtractedLinkedInIncumbent(name="Bob", role_canonical="cro", role_raw="CRO", is_relevant=True),
    ])

    incumbents = asyncio.run(_extract_current_incumbents(results_by_role, extractor))

    by_name = {i.name: i for i in incumbents}
    assert by_name["Sara Lee"].confidence == "low"
    assert by_name["Bob"].confidence == "high"


def test_extract_current_incumbents_drops_irrelevant():
    from rrxray.collectors.leadership_stability import _extract_current_incumbents
    from rrxray.services.firecrawl_client import SearchResult

    results_by_role = {
        "cro": [SearchResult(url="https://www.linkedin.com/in/x", title="x", description="y")],
        "ceo": [], "cmo": [], "vp_sales": [], "vp_revenue": [], "vp_marketing": [], "founder": [],
    }
    extractor = MagicMock()
    extractor.extract_linkedin_role = AsyncMock(return_value=None)

    incumbents = asyncio.run(_extract_current_incumbents(results_by_role, extractor))
    assert incumbents == []
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
/Users/dalezwizinski/Library/Python/3.9/bin/uv run pytest tests/test_leadership_stability.py -v
```

Expected: 5 new tests fail (`ImportError` for `_search_linkedin_incumbents` / `_extract_current_incumbents`).

- [ ] **Step 4: Add `_search_linkedin_incumbents` + `_extract_current_incumbents` to `rrxray/collectors/leadership_stability.py`**

Add the imports + helpers (insert after `_extract_exec_changes`):

```python
from rrxray.collectors._leadership_stability_catalog import (
    LEADERSHIP_ROLES,
    PRESS_ACTION_QUERIES,
)
from rrxray.schemas.leadership_stability import (
    CurrentIncumbent,
    ExecChange,
    LeadershipStabilityData,
)


async def _search_linkedin_incumbents(
    firecrawl: FirecrawlClient, company: str,
) -> dict[str, list[SearchResult]]:
    """Run 7 per-role LinkedIn /in/ searches; group results by canonical role.

    Per-role search failures are logged and yield empty list for that role
    (not missing-key); other roles continue.
    """
    from rrxray.services.firecrawl_client import FirecrawlError

    results_by_role: dict[str, list[SearchResult]] = {}

    for canonical, role_query in LEADERSHIP_ROLES:
        query = f'site:linkedin.com/in "{company}" {role_query}'
        try:
            results = await firecrawl.search(query, limit=3)
        except FirecrawlError as e:
            log.warning("linkedin search failed for role=%s: %s", canonical, e)
            results_by_role[canonical] = []
            continue
        results_by_role[canonical] = list(results)

    return results_by_role


def _confidence_for_linkedin_url(url: str) -> str:
    """LinkedIn /in/ profile URLs are 'high' confidence; /posts/ URLs are 'low'."""
    if "/in/" in url:
        return "high"
    return "low"


async def _extract_current_incumbents(
    results_by_role: dict[str, list[SearchResult]],
    extractor: HaikuExtractor | GeminiFlashExtractor,
) -> list[CurrentIncumbent]:
    """Per-result LLM extraction; dedupe by (role, name); preserve LinkedIn URL.

    For each role, walk results in order; the first relevant extraction
    becomes the incumbent for that role. Subsequent same-role-same-name
    matches are skipped (dedup).
    """
    incumbents: list[CurrentIncumbent] = []
    seen: set[tuple[str, str]] = set()  # (role_canonical, name)

    for role_canonical, results in results_by_role.items():
        for r in results:
            extracted = await extractor.extract_linkedin_role(
                r.title, r.description, role_canonical,
            )
            if extracted is None:
                continue
            key = (extracted.role_canonical, extracted.name)
            if key in seen:
                continue
            seen.add(key)
            incumbents.append(CurrentIncumbent(
                name=extracted.name,
                role_canonical=extracted.role_canonical,
                role_raw=extracted.role_raw,
                linkedin_url=r.url,
                confidence=_confidence_for_linkedin_url(r.url),  # type: ignore[arg-type]
            ))

    return incumbents
```

Update the `collect()` orchestrator to also call LinkedIn search + extraction:

```python
async def collect(ctx: CollectorContext) -> LeadershipStabilityData:
    company = ctx.company_name or ctx.domain.split(".")[0].title()
    if ctx.extractor is None:
        return LeadershipStabilityData()

    press_results = await _search_press_releases(ctx.firecrawl, company)
    exec_changes = await _extract_exec_changes(press_results, ctx.extractor)

    linkedin_results = await _search_linkedin_incumbents(ctx.firecrawl, company)
    current_incumbents = await _extract_current_incumbents(linkedin_results, ctx.extractor)

    return LeadershipStabilityData(
        exec_changes=exec_changes,
        current_incumbents=current_incumbents,
    )
```

- [ ] **Step 5: Run tests + ruff**

```bash
/Users/dalezwizinski/Library/Python/3.9/bin/uv run pytest tests/test_leadership_stability.py -v
/Users/dalezwizinski/Library/Python/3.9/bin/uv run ruff check rrxray/ tests/
```

Expected: 11 tests pass (6 from T7 + 5 from T8). Ruff clean.

- [ ] **Step 6: Commit**

```bash
git add rrxray/collectors/leadership_stability.py tests/test_leadership_stability.py tests/fixtures/synthetic/leadership_stability/
git commit -m "$(cat <<'EOF'
Add LinkedIn current C-suite search + extraction to leadership_stability

Implements _search_linkedin_incumbents (7 per-role queries; per-role
failure is logged and yields empty list, other roles continue) and
_extract_current_incumbents (per-result LLM extraction; dedup by
(role, name); confidence=high for /in/ URLs, low for /posts/ URLs).

collect() orchestrator now runs both press and LinkedIn paths.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Founder tenure inference (F1 + F2)

**Files:**
- Modify: `rrxray/collectors/leadership_stability.py` (add `_infer_founder_tenure`)
- Modify: `tests/test_leadership_stability.py`
- Create: `tests/fixtures/synthetic/leadership_stability/about_page_with_founding_year.html`
- Create: `tests/fixtures/synthetic/leadership_stability/about_page_no_founding_year.html`

- [ ] **Step 1: Create the about-page fixtures**

`tests/fixtures/synthetic/leadership_stability/about_page_with_founding_year.html`:

```html
<!doctype html>
<html><head><title>About Acme</title></head><body>
<h1>About Acme Corp</h1>
<p>Acme was founded in 2018 by Jane Doe and team to solve the problem of...</p>
<p>Since then, we've grown to over 200 employees across three continents.</p>
</body></html>
```

`tests/fixtures/synthetic/leadership_stability/about_page_no_founding_year.html`:

```html
<!doctype html>
<html><head><title>About Acme</title></head><body>
<h1>About Acme Corp</h1>
<p>Acme builds enterprise software for the modern revenue team.</p>
<p>We are headquartered in San Francisco.</p>
</body></html>
```

- [ ] **Step 2: Append failing tests**

```python
def test_infer_founder_tenure_about_page_path(fake_firecrawl):
    """F1 path: /about page with 'Founded in YYYY' → FounderTenure(source='about_page')."""
    from rrxray.collectors.leadership_stability import _infer_founder_tenure
    from rrxray.services.firecrawl_client import ScrapedPage

    about_html = (FIXTURES / "about_page_with_founding_year.html").read_text()
    fake_firecrawl.scrape_url = AsyncMock(return_value=ScrapedPage(
        url="https://acme.com/about", html=about_html, markdown=about_html,
    ))

    fake_wayback = MagicMock()
    fake_wayback.snapshots = AsyncMock()  # should not be called

    tenure = asyncio.run(_infer_founder_tenure(fake_firecrawl, fake_wayback, "acme.com"))

    assert tenure.inferred_year == 2018
    assert tenure.source == "about_page"
    assert tenure.raw_evidence is not None
    fake_wayback.snapshots.assert_not_called()


def test_infer_founder_tenure_wayback_fallback(fake_firecrawl):
    """F1 yields no year → F2 (Wayback oldest snapshot) provides year."""
    from datetime import UTC, datetime
    from rrxray.collectors.leadership_stability import _infer_founder_tenure
    from rrxray.services.firecrawl_client import ScrapedPage
    from rrxray.services.wayback_client import Snapshot

    about_html = (FIXTURES / "about_page_no_founding_year.html").read_text()
    fake_firecrawl.scrape_url = AsyncMock(return_value=ScrapedPage(
        url="https://acme.com/about", html=about_html, markdown=about_html,
    ))

    fake_wayback = MagicMock()
    fake_wayback.snapshots = AsyncMock(return_value=[
        Snapshot(
            timestamp=datetime(2020, 6, 1, tzinfo=UTC),
            archive_url="https://web.archive.org/web/20200601000000/https://acme.com",
            html="<html>...</html>",
            markdown="...",
        ),
        Snapshot(
            timestamp=datetime(2014, 6, 1, tzinfo=UTC),
            archive_url="https://web.archive.org/web/20140601000000/https://acme.com",
            html="<html>...</html>",
            markdown="...",
        ),
    ])

    tenure = asyncio.run(_infer_founder_tenure(fake_firecrawl, fake_wayback, "acme.com"))

    assert tenure.inferred_year == 2014
    assert tenure.source == "wayback_homepage"


def test_infer_founder_tenure_unknown(fake_firecrawl):
    """Both F1 and F2 fail → source='unknown'."""
    from rrxray.collectors.leadership_stability import _infer_founder_tenure
    from rrxray.services.firecrawl_client import FirecrawlError

    fake_firecrawl.scrape_url = AsyncMock(side_effect=FirecrawlError("about page unreachable"))

    fake_wayback = MagicMock()
    fake_wayback.snapshots = AsyncMock(return_value=[])

    tenure = asyncio.run(_infer_founder_tenure(fake_firecrawl, fake_wayback, "acme.com"))

    assert tenure.inferred_year is None
    assert tenure.source == "unknown"


def test_infer_founder_tenure_about_page_failure_falls_through(fake_firecrawl):
    """Firecrawl error on /about → still tries Wayback fallback."""
    from datetime import UTC, datetime
    from rrxray.collectors.leadership_stability import _infer_founder_tenure
    from rrxray.services.firecrawl_client import FirecrawlError
    from rrxray.services.wayback_client import Snapshot

    fake_firecrawl.scrape_url = AsyncMock(side_effect=FirecrawlError("about unreachable"))

    fake_wayback = MagicMock()
    fake_wayback.snapshots = AsyncMock(return_value=[
        Snapshot(
            timestamp=datetime(2016, 1, 1, tzinfo=UTC),
            archive_url="https://web.archive.org/web/20160101000000/https://acme.com",
            html="x", markdown="y",
        ),
    ])

    tenure = asyncio.run(_infer_founder_tenure(fake_firecrawl, fake_wayback, "acme.com"))

    assert tenure.source == "wayback_homepage"
    assert tenure.inferred_year == 2016
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
/Users/dalezwizinski/Library/Python/3.9/bin/uv run pytest tests/test_leadership_stability.py -v -k tenure
```

Expected: 4 new tests fail (ImportError for `_infer_founder_tenure`).

- [ ] **Step 4: Add `_infer_founder_tenure` to `rrxray/collectors/leadership_stability.py`**

Add the imports + helper (after `_extract_current_incumbents`):

```python
import re

from rrxray.collectors._leadership_stability_catalog import (
    FOUNDED_YEAR_PATTERNS,
    LEADERSHIP_ROLES,
    PRESS_ACTION_QUERIES,
)
from rrxray.schemas.leadership_stability import (
    CurrentIncumbent,
    ExecChange,
    FounderTenure,
    LeadershipStabilityData,
)

if TYPE_CHECKING:
    from rrxray.services.wayback_client import WaybackClient


def _parse_founding_year_from_about(html: str) -> tuple[int, str] | None:
    """Returns (year, raw_evidence_quote) on first match; None if no pattern matches."""
    text = re.sub(r"<[^>]+>", " ", html)  # strip tags crudely
    for pattern in FOUNDED_YEAR_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            year = int(m.group(1))
            # Capture a small surrounding quote for evidence
            start = max(0, m.start() - 20)
            end = min(len(text), m.end() + 20)
            quote = text[start:end].strip()
            return year, quote
    return None


async def _infer_founder_tenure(
    firecrawl: FirecrawlClient,
    wayback: WaybackClient,
    domain: str,
) -> FounderTenure:
    """F1: scrape /about, regex for founding year. F2 fallback: Wayback oldest snapshot.

    Returns FounderTenure(source='unknown') if both fail.
    """
    from rrxray.services.firecrawl_client import FirecrawlError

    # F1: try /about
    about_url = f"https://{domain}/about"
    try:
        page = await firecrawl.scrape_url(about_url, only_main_content=True)
    except FirecrawlError as e:
        log.warning("about page scrape failed: %s", e)
        page = None

    if page is not None:
        parsed = _parse_founding_year_from_about(page.html or page.markdown or "")
        if parsed is not None:
            year, evidence = parsed
            return FounderTenure(
                inferred_year=year,
                source="about_page",
                raw_evidence=evidence,
            )

    # F2: Wayback fallback — oldest reachable homepage snapshot
    try:
        snapshots = await wayback.snapshots(
            f"https://{domain}",
            interval_months=12,
            span_months=120,  # 10 years
        )
    except Exception as e:  # WaybackError or transient
        log.warning("wayback snapshots failed: %s", e)
        snapshots = []

    if snapshots:
        oldest = min(snapshots, key=lambda s: s.timestamp)
        return FounderTenure(
            inferred_year=oldest.timestamp.year,
            source="wayback_homepage",
            raw_evidence=f"Oldest reachable Wayback snapshot: {oldest.archive_url}",
        )

    return FounderTenure(source="unknown")
```

Update the `collect()` orchestrator to also call founder tenure:

```python
async def collect(ctx: CollectorContext) -> LeadershipStabilityData:
    company = ctx.company_name or ctx.domain.split(".")[0].title()
    if ctx.extractor is None:
        return LeadershipStabilityData()

    press_results = await _search_press_releases(ctx.firecrawl, company)
    exec_changes = await _extract_exec_changes(press_results, ctx.extractor)

    linkedin_results = await _search_linkedin_incumbents(ctx.firecrawl, company)
    current_incumbents = await _extract_current_incumbents(linkedin_results, ctx.extractor)

    founder_tenure = await _infer_founder_tenure(ctx.firecrawl, ctx.wayback, ctx.domain)

    return LeadershipStabilityData(
        exec_changes=exec_changes,
        current_incumbents=current_incumbents,
        founder_tenure=founder_tenure,
    )
```

- [ ] **Step 5: Run tests + ruff**

```bash
/Users/dalezwizinski/Library/Python/3.9/bin/uv run pytest tests/test_leadership_stability.py -v
/Users/dalezwizinski/Library/Python/3.9/bin/uv run ruff check rrxray/ tests/
```

Expected: 15 tests pass (11 + 4 new). Ruff clean.

- [ ] **Step 6: Commit**

```bash
git add rrxray/collectors/leadership_stability.py tests/test_leadership_stability.py tests/fixtures/synthetic/leadership_stability/about_page_*.html
git commit -m "$(cat <<'EOF'
Add founder tenure inference to leadership_stability (F1 + F2)

F1: scrape /about page, regex for FOUNDED_YEAR_PATTERNS.
F2 fallback: oldest reachable Wayback homepage snapshot.

Returns FounderTenure(source='unknown') when both paths yield no year.
F1 failure (FirecrawlError) falls through to F2 rather than aborting.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Name registrations + findings emission

**Files:**
- Modify: `rrxray/collectors/leadership_stability.py` (add `_build_name_registrations` + `_emit_findings`)
- Modify: `tests/test_leadership_stability.py`

- [ ] **Step 1: Append failing tests for name registration**

```python
def test_build_name_registrations_press_whitelisted():
    from rrxray.collectors.leadership_stability import _build_name_registrations
    from rrxray.schemas.leadership_stability import ExecAction, ExecChange

    exec_changes = [
        ExecChange(
            name="Jane Doe", role_canonical="cro", role_raw="CRO",
            action=ExecAction.HIRE,
            press_url="https://example.com/p/1",
            press_title="Acme Names Jane Doe as CRO",
        ),
    ]
    registrations = _build_name_registrations(exec_changes, [], company="Acme")

    assert len(registrations) == 1
    assert registrations[0].name == "Jane Doe"
    assert registrations[0].whitelist is True
    assert "CRO" in registrations[0].role_descriptor
    assert "Acme" in registrations[0].role_descriptor


def test_build_name_registrations_linkedin_not_whitelisted():
    from rrxray.collectors.leadership_stability import _build_name_registrations
    from rrxray.schemas.leadership_stability import CurrentIncumbent

    incumbents = [
        CurrentIncumbent(name="Bob Smith", role_canonical="cmo", role_raw="CMO"),
    ]
    registrations = _build_name_registrations([], incumbents, company="Acme")

    assert len(registrations) == 1
    assert registrations[0].name == "Bob Smith"
    assert registrations[0].whitelist is False


def test_build_name_registrations_dedupes():
    """Same name in press + LinkedIn → single registration; press takes precedence."""
    from rrxray.collectors.leadership_stability import _build_name_registrations
    from rrxray.schemas.leadership_stability import (
        CurrentIncumbent, ExecAction, ExecChange,
    )

    exec_changes = [
        ExecChange(
            name="Jane Doe", role_canonical="cro", role_raw="CRO",
            action=ExecAction.HIRE,
            press_url="x", press_title="y",
        ),
    ]
    incumbents = [
        CurrentIncumbent(name="Jane Doe", role_canonical="cro", role_raw="CRO"),
    ]
    registrations = _build_name_registrations(exec_changes, incumbents, company="Acme")

    assert len(registrations) == 1
    assert registrations[0].whitelist is True  # press wins


def test_build_name_registrations_role_descriptor_format():
    from rrxray.collectors.leadership_stability import _build_name_registrations
    from rrxray.schemas.leadership_stability import CurrentIncumbent

    incumbents = [
        CurrentIncumbent(name="Bob Smith", role_canonical="vp_sales", role_raw="VP of Sales"),
    ]
    registrations = _build_name_registrations([], incumbents, company="Acme")

    # Format: "Acme's VP Sales"
    assert registrations[0].role_descriptor == "Acme's VP Sales"
```

- [ ] **Step 2: Append failing tests for findings emission**

```python
def test_emit_findings_seat_turnover():
    """≥2 changes in same seat in past 18 months → seat-turnover finding."""
    from datetime import date, timedelta
    from rrxray.collectors.leadership_stability import _emit_findings
    from rrxray.schemas.leadership_stability import ExecAction, ExecChange, FounderTenure

    today = date.today()
    exec_changes = [
        ExecChange(
            name="Person A", role_canonical="cro", role_raw="CRO",
            action=ExecAction.HIRE,
            occurred_at=today - timedelta(days=400),
            press_url="x", press_title="y",
        ),
        ExecChange(
            name="Person B", role_canonical="cro", role_raw="CRO",
            action=ExecAction.HIRE,
            occurred_at=today - timedelta(days=120),
            press_url="x", press_title="y",
        ),
    ]
    findings, gaps, questions = _emit_findings(
        exec_changes, current_incumbents=[], founder_tenure=FounderTenure(),
    )

    finding_texts = [f.text for f in findings]
    assert any("turned over" in t.lower() and "cro" in t.lower() for t in finding_texts)


def test_emit_findings_recent_change():
    """1 change in seat within 270 days → in-transition finding."""
    from datetime import date, timedelta
    from rrxray.collectors.leadership_stability import _emit_findings
    from rrxray.schemas.leadership_stability import (
        CurrentIncumbent, ExecAction, ExecChange, FounderTenure,
    )

    today = date.today()
    exec_changes = [
        ExecChange(
            name="Jane", role_canonical="cro", role_raw="CRO",
            action=ExecAction.HIRE,
            occurred_at=today - timedelta(days=120),
            press_url="x", press_title="y",
        ),
    ]
    incumbents = [CurrentIncumbent(name="Jane", role_canonical="cro", role_raw="CRO")]
    findings, gaps, questions = _emit_findings(
        exec_changes, incumbents, FounderTenure(),
    )

    finding_texts = [f.text for f in findings]
    assert any("transition" in t.lower() for t in finding_texts)


def test_emit_findings_concurrent_revenue_marketing():
    """Recent CRO/VP Sales hire AND recent VP Marketing/CMO hire → cross-function finding."""
    from datetime import date, timedelta
    from rrxray.collectors.leadership_stability import _emit_findings
    from rrxray.schemas.leadership_stability import ExecAction, ExecChange, FounderTenure

    today = date.today()
    exec_changes = [
        ExecChange(
            name="A", role_canonical="cro", role_raw="CRO",
            action=ExecAction.HIRE,
            occurred_at=today - timedelta(days=100),
            press_url="x", press_title="y",
        ),
        ExecChange(
            name="B", role_canonical="cmo", role_raw="CMO",
            action=ExecAction.HIRE,
            occurred_at=today - timedelta(days=150),
            press_url="x", press_title="y",
        ),
    ]
    findings, gaps, questions = _emit_findings(exec_changes, [], FounderTenure())

    finding_texts = [f.text for f in findings]
    assert any("revenue and marketing" in t.lower() or "redesigned" in t.lower() for t in finding_texts)


def test_emit_findings_founder_led_long_tenure():
    """Founder ≥7 years AND current CEO incumbent matches founder → stability finding."""
    from rrxray.collectors.leadership_stability import _emit_findings
    from rrxray.schemas.leadership_stability import CurrentIncumbent, FounderTenure
    from datetime import date

    incumbents = [
        CurrentIncumbent(name="Jane Doe", role_canonical="ceo", role_raw="CEO"),
        CurrentIncumbent(name="Jane Doe", role_canonical="founder", role_raw="Founder"),
    ]
    tenure = FounderTenure(inferred_year=date.today().year - 8, source="about_page")

    findings, gaps, questions = _emit_findings([], incumbents, tenure)

    finding_texts = [f.text for f in findings]
    assert any("founder-led" in t.lower() for t in finding_texts)


def test_emit_findings_no_press_signal():
    """LinkedIn returned ≥1 incumbent AND zero exec changes → stability inferred."""
    from rrxray.collectors.leadership_stability import _emit_findings
    from rrxray.schemas.leadership_stability import CurrentIncumbent, FounderTenure

    incumbents = [
        CurrentIncumbent(name="x", role_canonical="cro", role_raw="CRO"),
    ]
    findings, gaps, questions = _emit_findings([], incumbents, FounderTenure())

    finding_texts = [f.text for f in findings]
    assert any("stability inferred" in t.lower() or "no public exec announcements" in t.lower() for t in finding_texts)


def test_emit_findings_total_signal_loss():
    """All paths empty → 'signal not recovered' finding."""
    from rrxray.collectors.leadership_stability import _emit_findings
    from rrxray.schemas.leadership_stability import FounderTenure

    findings, gaps, questions = _emit_findings([], [], FounderTenure(source="unknown"))

    finding_texts = [f.text for f in findings]
    assert any("not recovered" in t.lower() or "discovery" in t.lower() for t in finding_texts)
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
/Users/dalezwizinski/Library/Python/3.9/bin/uv run pytest tests/test_leadership_stability.py -v -k "registration or emit_findings"
```

Expected: 10 new tests fail with ImportError.

- [ ] **Step 4: Add `_build_name_registrations` + `_emit_findings` to `rrxray/collectors/leadership_stability.py`**

Add the imports + helpers (after `_infer_founder_tenure`):

```python
from datetime import date

from rrxray.collectors._leadership_stability_catalog import (
    FOUNDED_YEAR_PATTERNS,
    LEADERSHIP_ROLES,
    PRESS_ACTION_QUERIES,
    RECENT_THRESHOLD_DAYS,
    ROLE_DISPLAY,
)
from rrxray.schemas._shared import Finding, SourceCitation
from rrxray.schemas.leadership_stability import (
    CurrentIncumbent,
    ExecAction,
    ExecChange,
    FounderTenure,
    LeadershipStabilityData,
    NameRegistration,
)


def _build_name_registrations(
    exec_changes: list[ExecChange],
    current_incumbents: list[CurrentIncumbent],
    company: str,
) -> list[NameRegistration]:
    """Build deduped name registrations.

    Press names: whitelist=True. LinkedIn-only names: whitelist=False.
    Same name in both → single record; press takes precedence (whitelist=True wins).
    """
    by_name: dict[str, NameRegistration] = {}

    # Press names first (whitelist=True)
    for change in exec_changes:
        if not change.name:
            continue
        descriptor = f"{company}'s {ROLE_DISPLAY.get(change.role_canonical, change.role_raw)}"
        by_name[change.name] = NameRegistration(
            name=change.name,
            role_descriptor=descriptor,
            whitelist=True,
        )

    # LinkedIn names — only register if not already in press (don't downgrade whitelist)
    for inc in current_incumbents:
        if not inc.name or inc.name in by_name:
            continue
        descriptor = f"{company}'s {ROLE_DISPLAY.get(inc.role_canonical, inc.role_raw)}"
        by_name[inc.name] = NameRegistration(
            name=inc.name,
            role_descriptor=descriptor,
            whitelist=False,
        )

    return list(by_name.values())


def _months_ago(d: date | None) -> int | None:
    if d is None:
        return None
    today = date.today()
    return (today.year - d.year) * 12 + (today.month - d.month)


def _emit_findings(
    exec_changes: list[ExecChange],
    current_incumbents: list[CurrentIncumbent],
    founder_tenure: FounderTenure,
) -> tuple[list[Finding], list[str], list[str]]:
    """Rule-based findings, gaps, and discovery questions per spec rules table."""
    findings: list[Finding] = []
    gaps: list[str] = []
    questions: list[str] = []
    today = date.today()

    # Rule 1: ≥2 changes in same seat in past 18 months → seat-turnover finding
    seat_counts: dict[str, int] = {}
    for c in exec_changes:
        seat_counts[c.role_canonical] = seat_counts.get(c.role_canonical, 0) + 1
    for role, count in seat_counts.items():
        if count >= 2:
            display = ROLE_DISPLAY.get(role, role)
            findings.append(Finding(
                text=f"{display} seat has turned over {count} times in the past 18 months → buyer-side ownership of the conversation may shift mid-cycle.",
                source=SourceCitation(label=f"leadership_stability.exec_changes.{role}"),
            ))

    # Rule 2: 1 change in seat ≤RECENT_THRESHOLD_DAYS → in-transition finding
    recent_role_changes: dict[str, ExecChange] = {}
    for c in exec_changes:
        if c.occurred_at is None:
            continue
        days_ago = (today - c.occurred_at).days
        if days_ago <= RECENT_THRESHOLD_DAYS:
            # Only flag once per role; latest change wins
            existing = recent_role_changes.get(c.role_canonical)
            if existing is None or (existing.occurred_at and c.occurred_at > existing.occurred_at):
                recent_role_changes[c.role_canonical] = c
    for role, change in recent_role_changes.items():
        if seat_counts.get(role, 0) >= 2:
            continue  # already covered by Rule 1
        display = ROLE_DISPLAY.get(role, role)
        days_ago = (today - change.occurred_at).days  # type: ignore[operator]
        months_in_role = max(1, days_ago // 30)
        findings.append(Finding(
            text=f"{display} is in transition; current incumbent in seat ~{months_in_role} months → motion direction likely still being defined.",
            source=SourceCitation(label=change.press_url),
        ))

    # Rule 3: concurrent recent revenue + marketing leadership change
    revenue_recent = any(r in recent_role_changes for r in ("cro", "vp_sales", "vp_revenue"))
    marketing_recent = any(r in recent_role_changes for r in ("cmo", "vp_marketing"))
    if revenue_recent and marketing_recent:
        findings.append(Finding(
            text="Both revenue and marketing leadership turned over within 9 months → top-of-funnel and pipeline motion both being redesigned simultaneously.",
            source=SourceCitation(label="leadership_stability.cross_function"),
        ))

    # Rule 4: founder ≥7 years AND current CEO incumbent matches founder name
    founder_names = {i.name for i in current_incumbents if i.role_canonical == "founder"}
    ceo_incumbent_names = {i.name for i in current_incumbents if i.role_canonical == "ceo"}
    founder_in_ceo_seat = bool(founder_names & ceo_incumbent_names)
    tenure_years = (
        today.year - founder_tenure.inferred_year if founder_tenure.inferred_year else None
    )
    if founder_in_ceo_seat and tenure_years is not None and tenure_years >= 7:
        findings.append(Finding(
            text=f"Founder-led for {tenure_years} years → decision authority concentrated; commitment risk on multi-quarter buying decisions is lower than at professionally-led peers.",
            source=SourceCitation(label="leadership_stability.founder_tenure"),
        ))

    # Rule 5: founder tenure unknown AND zero current incumbents
    if founder_tenure.source == "unknown" and not current_incumbents:
        findings.append(Finding(
            text="Leadership signal not recovered from public sources → discovery should establish leadership stability and recent change directly.",
            source=SourceCitation(label="leadership_stability.signal_loss"),
        ))
        questions.append("Who is your current CRO and CMO? How long have they been in seat?")

    # Rule 6: incumbents present AND zero exec changes
    if current_incumbents and not exec_changes:
        findings.append(Finding(
            text="No public exec announcements in past 18 months → leadership stability inferred (within the limits of public-record visibility).",
            source=SourceCitation(label="leadership_stability.no_press_signal"),
        ))

    return findings, gaps, questions
```

Update `collect()`:

```python
async def collect(ctx: CollectorContext) -> LeadershipStabilityData:
    company = ctx.company_name or ctx.domain.split(".")[0].title()
    if ctx.extractor is None:
        return LeadershipStabilityData()

    press_results = await _search_press_releases(ctx.firecrawl, company)
    exec_changes = await _extract_exec_changes(press_results, ctx.extractor)

    linkedin_results = await _search_linkedin_incumbents(ctx.firecrawl, company)
    current_incumbents = await _extract_current_incumbents(linkedin_results, ctx.extractor)

    founder_tenure = await _infer_founder_tenure(ctx.firecrawl, ctx.wayback, ctx.domain)

    name_registrations = _build_name_registrations(
        exec_changes, current_incumbents, company,
    )
    findings, gaps, questions = _emit_findings(
        exec_changes, current_incumbents, founder_tenure,
    )

    return LeadershipStabilityData(
        exec_changes=exec_changes,
        current_incumbents=current_incumbents,
        founder_tenure=founder_tenure,
        name_registrations=name_registrations,
        findings=findings,
        gaps=gaps,
        discovery_questions=questions,
    )
```

- [ ] **Step 5: Run tests + ruff**

```bash
/Users/dalezwizinski/Library/Python/3.9/bin/uv run pytest tests/test_leadership_stability.py -v
/Users/dalezwizinski/Library/Python/3.9/bin/uv run ruff check rrxray/ tests/
```

Expected: 25 tests pass (15 + 10 new). Ruff clean.

- [ ] **Step 6: Commit**

```bash
git add rrxray/collectors/leadership_stability.py tests/test_leadership_stability.py
git commit -m "$(cat <<'EOF'
Add name registrations + rule-based findings to leadership_stability

_build_name_registrations: press names get whitelist=True; LinkedIn-only
names get whitelist=False; same name in both deduped with press
precedence. Role descriptor format: '<Company>'s <ROLE_DISPLAY>'.

_emit_findings: six rules per spec — seat turnover (>=2), in-transition
(<=270d), concurrent rev+marketing change, founder-led >=7y, total
signal loss, and stability inferred (incumbents but no press).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: Evidence writing + full collect() orchestration

**Files:**
- Modify: `rrxray/collectors/leadership_stability.py` (add `_write_evidence`; finalize `collect()` with graceful error handling)
- Modify: `tests/test_leadership_stability.py`

- [ ] **Step 1: Append failing tests for evidence + full happy path + total failure**

```python
def test_collect_writes_evidence(tmp_path):
    """All four evidence files written under evidence/leadership_stability/."""
    from rrxray.collectors.leadership_stability import collect
    from rrxray.config import Config
    from rrxray.context import CollectorContext
    from rrxray.services.extraction import ExecAction, ExtractedExecChange
    from rrxray.services.firecrawl_client import ScrapedPage, SearchResult

    fake_firecrawl = MagicMock()
    fake_firecrawl.search = AsyncMock(side_effect=[
        # press hires/departures/promotions
        [SearchResult(url="u1", title="Acme Names Jane Doe as CRO", description="...")],
        [],
        [],
        # 7 LinkedIn role queries
        [SearchResult(url="https://www.linkedin.com/in/jane-doe", title="Jane CRO", description="...")],
        [], [], [], [], [], [],
    ])
    fake_firecrawl.scrape_url = AsyncMock(return_value=ScrapedPage(
        url="https://example.com/about",
        html="<html>Founded in 2018</html>",
        markdown="Founded in 2018",
    ))

    fake_wayback = MagicMock()
    fake_wayback.snapshots = AsyncMock(return_value=[])

    fake_extractor = MagicMock()
    fake_extractor.extract_exec_change = AsyncMock(return_value=ExtractedExecChange(
        name="Jane Doe", role_canonical="cro", role_raw="CRO",
        action=ExecAction.HIRE, is_relevant=True,
    ))
    from rrxray.services.extraction import ExtractedLinkedInIncumbent
    fake_extractor.extract_linkedin_role = AsyncMock(return_value=ExtractedLinkedInIncumbent(
        name="Jane Doe", role_canonical="cro", role_raw="CRO", is_relevant=True,
    ))

    config = Config(domain="example.com")
    ctx = CollectorContext(
        domain="example.com",
        company_name="Acme",
        firecrawl=fake_firecrawl,
        wayback=fake_wayback,
        evidence_dir=tmp_path,
        config=config,
        extractor=fake_extractor,
    )

    asyncio.run(collect(ctx))

    evidence_dir = tmp_path / "leadership_stability"
    assert evidence_dir.exists()
    assert (evidence_dir / "press_search.json").exists()
    assert (evidence_dir / "linkedin_search.json").exists()
    assert (evidence_dir / "exec_changes.json").exists()
    assert (evidence_dir / "current_incumbents.json").exists()


def test_collect_returns_full_happy_path(tmp_path):
    """All paths populated → fully populated LeadershipStabilityData."""
    from rrxray.collectors.leadership_stability import collect
    from rrxray.config import Config
    from rrxray.context import CollectorContext
    from rrxray.services.extraction import (
        ExecAction, ExtractedExecChange, ExtractedLinkedInIncumbent,
    )
    from rrxray.services.firecrawl_client import ScrapedPage, SearchResult

    fake_firecrawl = MagicMock()
    fake_firecrawl.search = AsyncMock(side_effect=[
        [SearchResult(url="https://example.com/p/1", title="Acme Names Jane Doe as CRO", description="...")],
        [],
        [],
        [SearchResult(url="https://www.linkedin.com/in/jane-doe", title="Jane CRO", description="...")],
        [], [], [], [], [], [],
    ])
    fake_firecrawl.scrape_url = AsyncMock(return_value=ScrapedPage(
        url="https://example.com/about", html="<p>Founded in 2018</p>", markdown="Founded in 2018",
    ))
    fake_wayback = MagicMock()
    fake_wayback.snapshots = AsyncMock(return_value=[])

    fake_extractor = MagicMock()
    fake_extractor.extract_exec_change = AsyncMock(return_value=ExtractedExecChange(
        name="Jane Doe", role_canonical="cro", role_raw="CRO",
        action=ExecAction.HIRE, is_relevant=True,
    ))
    fake_extractor.extract_linkedin_role = AsyncMock(return_value=ExtractedLinkedInIncumbent(
        name="Jane Doe", role_canonical="cro", role_raw="CRO", is_relevant=True,
    ))

    ctx = CollectorContext(
        domain="example.com", company_name="Acme",
        firecrawl=fake_firecrawl, wayback=fake_wayback,
        evidence_dir=tmp_path, config=Config(domain="example.com"),
        extractor=fake_extractor,
    )
    data = asyncio.run(collect(ctx))

    assert len(data.exec_changes) == 1
    assert data.exec_changes[0].name == "Jane Doe"
    assert len(data.current_incumbents) == 1
    assert data.founder_tenure.inferred_year == 2018
    assert len(data.name_registrations) == 1
    assert data.name_registrations[0].whitelist is True  # press takes precedence


def test_collect_handles_total_failure(tmp_path):
    """All Firecrawl calls fail; collector returns LeadershipStabilityData with signal-loss finding."""
    from rrxray.collectors.leadership_stability import collect
    from rrxray.config import Config
    from rrxray.context import CollectorContext
    from rrxray.services.firecrawl_client import FirecrawlError

    fake_firecrawl = MagicMock()
    fake_firecrawl.search = AsyncMock(side_effect=FirecrawlError("simulated"))
    fake_firecrawl.scrape_url = AsyncMock(side_effect=FirecrawlError("simulated"))

    fake_wayback = MagicMock()
    fake_wayback.snapshots = AsyncMock(return_value=[])

    fake_extractor = MagicMock()
    # Should never be called since search returned no results, but provide stubs
    fake_extractor.extract_exec_change = AsyncMock(return_value=None)
    fake_extractor.extract_linkedin_role = AsyncMock(return_value=None)

    ctx = CollectorContext(
        domain="example.com", company_name="Acme",
        firecrawl=fake_firecrawl, wayback=fake_wayback,
        evidence_dir=tmp_path, config=Config(domain="example.com"),
        extractor=fake_extractor,
    )
    data = asyncio.run(collect(ctx))

    # Graceful: no exception, finding emitted
    assert data.exec_changes == []
    assert data.current_incumbents == []
    assert data.founder_tenure.source == "unknown"
    finding_texts = [f.text for f in data.findings]
    assert any("not recovered" in t.lower() for t in finding_texts)


def test_collect_handles_press_search_failure_only(tmp_path):
    """Press search fails entirely; LinkedIn + founder still work."""
    from rrxray.collectors.leadership_stability import collect
    from rrxray.config import Config
    from rrxray.context import CollectorContext
    from rrxray.services.extraction import ExtractedLinkedInIncumbent
    from rrxray.services.firecrawl_client import FirecrawlError, ScrapedPage, SearchResult

    fake_firecrawl = MagicMock()
    # First 3 calls (press hires/departures/promotions) all fail
    # Next 7 (LinkedIn) return one CRO result
    fake_firecrawl.search = AsyncMock(side_effect=[
        FirecrawlError("simulated press failure"),
        FirecrawlError("simulated press failure"),
        FirecrawlError("simulated press failure"),
        [SearchResult(url="https://www.linkedin.com/in/jane", title="Jane CRO", description="...")],
        [], [], [], [], [], [],
    ])
    fake_firecrawl.scrape_url = AsyncMock(return_value=ScrapedPage(
        url="https://example.com/about", html="<p>Founded in 2018</p>", markdown="Founded in 2018",
    ))
    fake_wayback = MagicMock()
    fake_wayback.snapshots = AsyncMock(return_value=[])

    fake_extractor = MagicMock()
    fake_extractor.extract_exec_change = AsyncMock(return_value=None)
    fake_extractor.extract_linkedin_role = AsyncMock(return_value=ExtractedLinkedInIncumbent(
        name="Jane", role_canonical="cro", role_raw="CRO", is_relevant=True,
    ))

    ctx = CollectorContext(
        domain="example.com", company_name="Acme",
        firecrawl=fake_firecrawl, wayback=fake_wayback,
        evidence_dir=tmp_path, config=Config(domain="example.com"),
        extractor=fake_extractor,
    )
    data = asyncio.run(collect(ctx))

    # Press path silent; LinkedIn + founder populated
    assert data.exec_changes == []
    assert len(data.current_incumbents) == 1
    assert data.founder_tenure.inferred_year == 2018


def test_collect_excludes_names_from_synthesizer_visible_data(tmp_path):
    """Defense-in-depth: confirm collector output keeps names confined to expected fields."""
    from rrxray.collectors.leadership_stability import collect
    from rrxray.config import Config
    from rrxray.context import CollectorContext
    from rrxray.services.extraction import (
        ExecAction, ExtractedExecChange, ExtractedLinkedInIncumbent,
    )
    from rrxray.services.firecrawl_client import ScrapedPage, SearchResult

    fake_firecrawl = MagicMock()
    fake_firecrawl.search = AsyncMock(side_effect=[
        [SearchResult(url="u1", title="Acme Names Jane Doe as CRO", description="...")],
        [],
        [],
        [SearchResult(url="https://www.linkedin.com/in/jane", title="Jane CRO", description="...")],
        [], [], [], [], [], [],
    ])
    fake_firecrawl.scrape_url = AsyncMock(return_value=ScrapedPage(
        url="https://example.com/about", html="<p>Founded in 2018</p>", markdown="...",
    ))
    fake_wayback = MagicMock()
    fake_wayback.snapshots = AsyncMock(return_value=[])

    fake_extractor = MagicMock()
    fake_extractor.extract_exec_change = AsyncMock(return_value=ExtractedExecChange(
        name="Jane Doe", role_canonical="cro", role_raw="CRO",
        action=ExecAction.HIRE, is_relevant=True,
    ))
    fake_extractor.extract_linkedin_role = AsyncMock(return_value=ExtractedLinkedInIncumbent(
        name="Jane Doe", role_canonical="cro", role_raw="CRO", is_relevant=True,
    ))

    ctx = CollectorContext(
        domain="example.com", company_name="Acme",
        firecrawl=fake_firecrawl, wayback=fake_wayback,
        evidence_dir=tmp_path, config=Config(domain="example.com"),
        extractor=fake_extractor,
    )
    data = asyncio.run(collect(ctx))

    # Names appear in expected fields only
    assert data.exec_changes[0].name == "Jane Doe"
    assert data.current_incumbents[0].name == "Jane Doe"
    assert data.name_registrations[0].name == "Jane Doe"

    # Names should NOT leak into findings text (those are collector-emitted strings)
    for finding in data.findings:
        assert "Jane Doe" not in finding.text, f"Name leaked into finding: {finding.text!r}"
    for q in data.discovery_questions:
        assert "Jane Doe" not in q
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
/Users/dalezwizinski/Library/Python/3.9/bin/uv run pytest tests/test_leadership_stability.py -v -k "writes_evidence or happy_path or total_failure or press_search_failure_only or excludes_names"
```

Expected: 5 new tests fail.

- [ ] **Step 3: Add `_write_evidence` and finalize `collect()`**

Add `_write_evidence` after `_emit_findings`:

```python
import json
from pathlib import Path


def _write_evidence(
    evidence_dir: Path,
    press_results: list[SearchResult],
    linkedin_results_by_role: dict[str, list[SearchResult]],
    exec_changes: list[ExecChange],
    current_incumbents: list[CurrentIncumbent],
) -> None:
    """Write evidence files under evidence_dir/leadership_stability/."""
    out_dir = evidence_dir / "leadership_stability"
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "press_search.json").write_text(
        json.dumps([r.model_dump() for r in press_results], indent=2)
    )
    (out_dir / "linkedin_search.json").write_text(
        json.dumps(
            {role: [r.model_dump() for r in results]
             for role, results in linkedin_results_by_role.items()},
            indent=2,
        )
    )
    (out_dir / "exec_changes.json").write_text(
        json.dumps([c.model_dump(mode="json") for c in exec_changes], indent=2)
    )
    (out_dir / "current_incumbents.json").write_text(
        json.dumps([i.model_dump() for i in current_incumbents], indent=2)
    )
```

Replace `collect()` with the final version:

```python
async def collect(ctx: CollectorContext) -> LeadershipStabilityData:
    """Orchestrator. Runs press + LinkedIn + founder paths in sequence;
    each handles its own errors gracefully. Returns a fully-validated
    LeadershipStabilityData with name_registrations populated for the
    pipeline's anonymizer registration loop.
    """
    company = ctx.company_name or ctx.domain.split(".")[0].title()

    if ctx.extractor is None:
        log.warning("leadership_stability: no extractor on context; returning empty data")
        return LeadershipStabilityData(
            findings=[Finding(
                text="Leadership stability collector skipped: no extractor configured.",
                source=SourceCitation(label="leadership_stability.config"),
            )],
        )

    # Press path
    press_results = await _search_press_releases(ctx.firecrawl, company)
    exec_changes = await _extract_exec_changes(press_results, ctx.extractor)

    # LinkedIn path
    linkedin_results_by_role = await _search_linkedin_incumbents(ctx.firecrawl, company)
    current_incumbents = await _extract_current_incumbents(
        linkedin_results_by_role, ctx.extractor,
    )

    # Founder tenure path
    founder_tenure = await _infer_founder_tenure(ctx.firecrawl, ctx.wayback, ctx.domain)

    # Build derived data
    name_registrations = _build_name_registrations(
        exec_changes, current_incumbents, company,
    )
    findings, gaps, questions = _emit_findings(
        exec_changes, current_incumbents, founder_tenure,
    )

    # Write evidence
    try:
        _write_evidence(
            ctx.evidence_dir,
            press_results,
            linkedin_results_by_role,
            exec_changes,
            current_incumbents,
        )
    except OSError as e:
        log.warning("evidence write failed: %s", e)

    return LeadershipStabilityData(
        exec_changes=exec_changes,
        current_incumbents=current_incumbents,
        founder_tenure=founder_tenure,
        name_registrations=name_registrations,
        findings=findings,
        gaps=gaps,
        discovery_questions=questions,
    )
```

- [ ] **Step 4: Run full test file + ruff**

```bash
/Users/dalezwizinski/Library/Python/3.9/bin/uv run pytest tests/test_leadership_stability.py -v
/Users/dalezwizinski/Library/Python/3.9/bin/uv run ruff check rrxray/ tests/
```

Expected: 30 tests pass (25 + 5 new). Ruff clean.

- [ ] **Step 5: Commit**

```bash
git add rrxray/collectors/leadership_stability.py tests/test_leadership_stability.py
git commit -m "$(cat <<'EOF'
Finalize leadership_stability collector with evidence + orchestration

_write_evidence writes press_search.json, linkedin_search.json,
exec_changes.json, and current_incumbents.json under
evidence/leadership_stability/.

collect() orchestrator runs press + LinkedIn + founder paths in sequence
with graceful per-path error handling. Returns a full LeadershipStabilityData
even on total signal loss, with the appropriate signal-not-recovered
finding.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: Pipeline anonymizer registration loop

**Files:**
- Modify: `rrxray/pipeline.py` (post-collection registration loop + extractor wire-up)
- Modify: `tests/test_pipeline.py` (add registration test)

- [ ] **Step 1: Read current `rrxray/pipeline.py` to confirm context-construction shape**

```bash
sed -n '1,80p' rrxray/pipeline.py
sed -n '120,180p' rrxray/pipeline.py
```

Expected: shows where `CollectorContext` is built, where collectors run, where Anonymizer is instantiated. Find the spot between collector runs and synthesizer runs.

- [ ] **Step 2: Append failing test to `tests/test_pipeline.py`**

```python
def test_pipeline_registers_leadership_stability_name_registrations(tmp_path):
    """Pipeline post-collection: anonymizer.register_individual called per name_registration;
    whitelist_from_press called for whitelisted entries.
    """
    from unittest.mock import MagicMock
    from rrxray.schemas.leadership_stability import (
        LeadershipStabilityData, NameRegistration,
    )
    from rrxray.voice.anonymizer import Anonymizer

    anonymizer = Anonymizer()
    data = LeadershipStabilityData(
        name_registrations=[
            NameRegistration(name="Jane Doe", role_descriptor="Acme's CRO", whitelist=True),
            NameRegistration(name="Bob Smith", role_descriptor="Acme's CMO", whitelist=False),
        ],
    )

    from rrxray.pipeline import _register_collector_names
    _register_collector_names(anonymizer, data.name_registrations)

    # Both registered
    assert "Jane Doe" in anonymizer.name_to_role
    assert "Bob Smith" in anonymizer.name_to_role
    # Only Jane is whitelisted (press)
    assert "Jane Doe" in anonymizer.whitelisted_names
    assert "Bob Smith" not in anonymizer.whitelisted_names
```

- [ ] **Step 3: Run test to verify it fails**

```bash
/Users/dalezwizinski/Library/Python/3.9/bin/uv run pytest tests/test_pipeline.py::test_pipeline_registers_leadership_stability_name_registrations -v
```

Expected: ImportError for `_register_collector_names`.

- [ ] **Step 4: Add `_register_collector_names` helper + call site in `rrxray/pipeline.py`**

Add the helper near the top (after imports):

```python
def _register_collector_names(anonymizer, name_registrations) -> None:
    """Apply NameRegistration entries to the anonymizer.

    Called by the pipeline post-collection. Press-whitelisted names get
    both register_individual + whitelist_from_press; LinkedIn-only names
    get register_individual only.
    """
    for reg in name_registrations:
        anonymizer.register_individual(reg.name, reg.role_descriptor)
        if reg.whitelist:
            anonymizer.whitelist_from_press(reg.name)
```

In the main `run_pipeline` (or equivalent orchestration function), after collectors complete and before synthesizers run, add:

```python
    # Apply per-collector name registrations to the anonymizer.
    leadership = collector_outputs.leadership_stability
    if leadership is not None:
        _register_collector_names(anonymizer, leadership.name_registrations)
```

(If pipeline.py grows a per-collector hook pattern in the future, generalize this to iterate over all collector outputs that expose `name_registrations`. Phase 2.2 only has one such collector; explicit reference is fine.)

In context construction, also wire up the extractor. Add Gemini client setup conditional on `gemini_api_key`, then build the extractor:

```python
    from rrxray.services.extraction import make_extractor
    from rrxray.services.gemini_client import GeminiClient

    gemini = None
    if config.gemini_api_key is not None:
        gemini = GeminiClient(api_key=config.gemini_api_key.get_secret_value())

    extractor = make_extractor(config, anthropic, gemini)

    # Pass extractor into CollectorContext when building it (find the existing
    # build_collector_context call and add extractor=extractor)
```

- [ ] **Step 5: Run tests + ruff**

```bash
/Users/dalezwizinski/Library/Python/3.9/bin/uv run pytest tests/test_pipeline.py -v
/Users/dalezwizinski/Library/Python/3.9/bin/uv run ruff check rrxray/ tests/
```

Expected: new test passes; existing pipeline tests still pass. Ruff clean.

- [ ] **Step 6: Commit**

```bash
git add rrxray/pipeline.py tests/test_pipeline.py
git commit -m "$(cat <<'EOF'
Wire pipeline anonymizer registration + extractor for leadership_stability

_register_collector_names: applies NameRegistration entries to the
anonymizer post-collection (register_individual + optional
whitelist_from_press for press-sourced names).

Pipeline now also instantiates GeminiClient when GEMINI_API_KEY is set
and builds an extractor via make_extractor; passes the extractor through
CollectorContext for use by the leadership_stability collector.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 13: Renderer Module Detail partial + report integration

**Files:**
- Create: `templates/_leadership_stability_detail.md.jinja`
- Modify: `templates/report_internal.md.jinja` (include partial in Module Detail Appendix; render Section B narrative)
- Modify: `tests/test_render.py` (or wherever existing renderer tests live)

- [ ] **Step 1: Create `templates/_leadership_stability_detail.md.jinja`**

```jinja
{% set ls = data.collectors.leadership_stability %}

#### Founder tenure

{% if ls.founder_tenure and ls.founder_tenure.inferred_year %}
- Inferred founding year: {{ ls.founder_tenure.inferred_year }} (source: {{ ls.founder_tenure.source }})
{% if ls.founder_tenure.raw_evidence %}
- Evidence: `{{ ls.founder_tenure.raw_evidence }}`
{% endif %}
{% else %}
- Not inferable from public sources.
{% endif %}

#### Current incumbents (LinkedIn snippet inference)

{% if ls.current_incumbents %}
| Role | Name | Confidence | LinkedIn |
|---|---|---|---|
{% for inc in ls.current_incumbents %}
| {{ inc.role_canonical }} | {{ inc.name | anonymize }} | {{ inc.confidence }} | {% if inc.linkedin_url %}[link]({{ inc.linkedin_url }}){% else %}—{% endif %} |
{% endfor %}
{% else %}
None recovered from public sources.
{% endif %}

#### Exec changes (past 18 months, press-release sourced)

{% if ls.exec_changes %}
| Role | Action | Name | Date | Source |
|---|---|---|---|---|
{% for change in ls.exec_changes %}
| {{ change.role_canonical }} | {{ change.action }} | {{ change.name | anonymize }} | {{ change.occurred_at or "—" }} | [press]({{ change.press_url }}) |
{% endfor %}
{% else %}
No public exec announcements recovered.
{% endif %}

{% if ls.findings %}
#### Findings

{% for finding in ls.findings %}
- {{ finding.text }}
{% endfor %}
{% endif %}

{% if ls.gaps %}
#### Gaps

{% for gap in ls.gaps %}
- {{ gap }}
{% endfor %}
{% endif %}

{% if ls.discovery_questions %}
#### Discovery questions

{% for q in ls.discovery_questions %}
- {{ q }}
{% endfor %}
{% endif %}
```

(Press-whitelisted names pass through `anonymize` filter unchanged; LinkedIn-only names get replaced with role descriptors. The `anonymize` filter is registered globally in `rrxray/rendering/markdown.py:58`.)

- [ ] **Step 2: Edit `templates/report_internal.md.jinja`**

Find the Section A narrative block. After it, add Section B narrative:

```jinja
{% if data.synthesizers.observed_stability_trajectory %}

## Section B: Observed Stability and Trajectory

{% for paragraph in data.synthesizers.observed_stability_trajectory.narrative_paragraphs %}
{{ paragraph | anonymize }}

{% endfor %}

{% if data.synthesizers.observed_stability_trajectory.gaps %}
### Gaps

{% for gap in data.synthesizers.observed_stability_trajectory.gaps %}
- {{ gap }}
{% endfor %}
{% endif %}

{% if data.synthesizers.observed_stability_trajectory.discovery_questions %}
### Discovery questions

{% for q in data.synthesizers.observed_stability_trajectory.discovery_questions %}
- {{ q }}
{% endfor %}
{% endif %}
{% endif %}
```

In the Module Detail Appendix section, after the Revenue Motion subsection, add:

```jinja
{% if data.collectors.leadership_stability %}
### Leadership Stability

{% include "_leadership_stability_detail.md.jinja" %}
{% endif %}
```

- [ ] **Step 3: Add render tests**

Append to existing render test file (e.g., `tests/test_render.py`):

```python
def test_leadership_stability_module_detail_renders():
    """Module Detail Appendix renders Leadership Stability subsection with full data."""
    from datetime import UTC, date, datetime
    from rrxray.rendering.markdown import render_internal
    from rrxray.schemas.data import (
        CollectorOutputs, InputParams, ObservedStabilityTrajectoryNarrative,
        RunMetadata, SynthesizerOutputs, XrayData,
    )
    from rrxray.schemas.leadership_stability import (
        CurrentIncumbent, ExecAction, ExecChange, FounderTenure,
        LeadershipStabilityData, NameRegistration,
    )
    from rrxray.voice.anonymizer import Anonymizer
    from rrxray.voice.rr_voice import VoicePostProcessor

    anonymizer = Anonymizer()
    voice = VoicePostProcessor()

    ls_data = LeadershipStabilityData(
        exec_changes=[
            ExecChange(
                name="Jane Doe", role_canonical="cro", role_raw="CRO",
                action=ExecAction.HIRE,
                occurred_at=date(2025, 9, 1),
                press_url="https://example.com/p/1",
                press_title="Acme Names Jane Doe as CRO",
            ),
        ],
        current_incumbents=[
            CurrentIncumbent(name="Jane Doe", role_canonical="cro", role_raw="CRO"),
            CurrentIncumbent(name="Bob Smith", role_canonical="cmo", role_raw="CMO"),
        ],
        founder_tenure=FounderTenure(inferred_year=2018, source="about_page"),
        name_registrations=[
            NameRegistration(name="Jane Doe", role_descriptor="Acme's CRO", whitelist=True),
            NameRegistration(name="Bob Smith", role_descriptor="Acme's CMO", whitelist=False),
        ],
    )

    # Apply registrations to anonymizer (mirrors what pipeline does)
    for reg in ls_data.name_registrations:
        anonymizer.register_individual(reg.name, reg.role_descriptor)
        if reg.whitelist:
            anonymizer.whitelist_from_press(reg.name)

    data = XrayData(
        domain="example.com",
        run_metadata=RunMetadata(
            timestamp=datetime.now(UTC),
            tool_version="0.1",
            modes_built=["internal"],
            model_used="claude-sonnet-4-6",
        ),
        inputs=InputParams(domain="example.com"),
        collectors=CollectorOutputs(leadership_stability=ls_data),
    )

    rendered = render_internal(data, anonymizer, voice)

    assert "Leadership Stability" in rendered
    assert "Founder tenure" in rendered
    assert "Current incumbents" in rendered
    # Whitelisted name: passes through
    assert "Jane Doe" in rendered
    # Non-whitelisted LinkedIn-only name: replaced with role descriptor
    assert "Bob Smith" not in rendered
    assert "Acme's CMO" in rendered


def test_leadership_stability_module_detail_omits_when_no_collector():
    """Module Detail Appendix omits Leadership Stability section when collector is None."""
    from datetime import UTC, datetime
    from rrxray.rendering.markdown import render_internal
    from rrxray.schemas.data import (
        CollectorOutputs, InputParams, RunMetadata, XrayData,
    )
    from rrxray.voice.anonymizer import Anonymizer
    from rrxray.voice.rr_voice import VoicePostProcessor

    data = XrayData(
        domain="example.com",
        run_metadata=RunMetadata(
            timestamp=datetime.now(UTC),
            tool_version="0.1",
            modes_built=["internal"],
            model_used="claude-sonnet-4-6",
        ),
        inputs=InputParams(domain="example.com"),
        collectors=CollectorOutputs(),  # no leadership_stability
    )

    rendered = render_internal(data, Anonymizer(), VoicePostProcessor())
    assert "Leadership Stability" not in rendered
    assert "Founder tenure" not in rendered


def test_render_anonymizes_linkedin_names_preserves_press_names():
    """LinkedIn-only names get replaced; press-whitelisted names pass through."""
    from datetime import UTC, datetime
    from rrxray.rendering.markdown import render_internal
    from rrxray.schemas.data import (
        CollectorOutputs, InputParams, RunMetadata, XrayData,
    )
    from rrxray.schemas.leadership_stability import (
        CurrentIncumbent, LeadershipStabilityData, NameRegistration,
    )
    from rrxray.voice.anonymizer import Anonymizer
    from rrxray.voice.rr_voice import VoicePostProcessor

    anonymizer = Anonymizer()
    anonymizer.register_individual("Press Person", "Acme's CRO")
    anonymizer.whitelist_from_press("Press Person")
    anonymizer.register_individual("LinkedIn Person", "Acme's CMO")
    # NOT whitelisted

    ls = LeadershipStabilityData(
        current_incumbents=[
            CurrentIncumbent(name="Press Person", role_canonical="cro", role_raw="CRO"),
            CurrentIncumbent(name="LinkedIn Person", role_canonical="cmo", role_raw="CMO"),
        ],
        name_registrations=[
            NameRegistration(name="Press Person", role_descriptor="Acme's CRO", whitelist=True),
            NameRegistration(name="LinkedIn Person", role_descriptor="Acme's CMO", whitelist=False),
        ],
    )
    data = XrayData(
        domain="example.com",
        run_metadata=RunMetadata(
            timestamp=datetime.now(UTC),
            tool_version="0.1",
            modes_built=["internal"],
            model_used="claude-sonnet-4-6",
        ),
        inputs=InputParams(domain="example.com"),
        collectors=CollectorOutputs(leadership_stability=ls),
    )

    rendered = render_internal(data, anonymizer, VoicePostProcessor())
    assert "Press Person" in rendered
    assert "LinkedIn Person" not in rendered
    assert "Acme's CMO" in rendered
```

- [ ] **Step 4: Run tests + ruff**

```bash
/Users/dalezwizinski/Library/Python/3.9/bin/uv run pytest tests/test_render.py -v
/Users/dalezwizinski/Library/Python/3.9/bin/uv run ruff check rrxray/ tests/
```

Expected: 3 new tests pass. Ruff clean.

- [ ] **Step 5: Commit**

```bash
git add templates/_leadership_stability_detail.md.jinja templates/report_internal.md.jinja tests/test_render.py
git commit -m "Add Leadership Stability rendering: Section B narrative + Module Detail partial"
```

---

## Task 14: Synthesizer + prompt template

**Files:**
- Create: `rrxray/synthesizers/observed_stability_trajectory.py`
- Create: `rrxray/prompts/observed_stability_trajectory.md`
- Create: `tests/test_observed_stability_trajectory.py`

- [ ] **Step 1: Create the prompt template `rrxray/prompts/observed_stability_trajectory.md`**

```markdown
Domain: {{ domain }}

# Section B: Observed Stability and Trajectory

You are diagnosing the prospect's leadership stability and trajectory based on publicly observable signals.

You will receive aggregated leadership data — counts and tenures, never names. Do not invent names. Refer to roles by descriptor only ("the CRO", "the CEO", "the founder").

## Aggregated leadership signals

**Seat changes (past 18 months):**
{% if aggregates.seat_changes %}
{% for role, count in aggregates.seat_changes.items() %}
- {{ role }}: {{ count }} change(s)
{% endfor %}
{% else %}
- No exec-change records recovered.
{% endif %}

**Recent changes (within 9 months):**
{% if aggregates.recent_changes %}
{% for change in aggregates.recent_changes %}
- {{ change.role }}: {{ change.action }} ~{{ change.occurred_at_months_ago }} months ago
{% endfor %}
{% else %}
- None.
{% endif %}

**Current incumbents (high confidence only):**
{% if aggregates.current_incumbents_by_role %}
{% for role, info in aggregates.current_incumbents_by_role.items() %}
- {{ role }}: in seat ~{{ info.tenure_months or "unknown" }} months ({{ info.confidence }} confidence)
{% endfor %}
{% else %}
- None recovered.
{% endif %}

**Founder presence:**
- Founder in CEO seat: {{ "yes" if aggregates.founder_present_in_ceo_seat else "no" }}
{% if aggregates.founder_tenure_years %}
- Founder tenure: ~{{ aggregates.founder_tenure_years }} years
{% endif %}

**Seats with no public change in 18 months:** {{ aggregates.seats_with_no_change_18mo | join(", ") if aggregates.seats_with_no_change_18mo else "none" }}

**Collector findings (rule-based):**
{% if aggregates.collector_findings %}
{% for f in aggregates.collector_findings %}
- {{ f }}
{% endfor %}
{% else %}
- (none)
{% endif %}

## Diagnostic posture

Commit to a single hypothesis about this company's leadership stability and trajectory. Do not enumerate possibilities; pick the strongest read of the data and write it.

Possible hypotheses:
- **Stable, founder-led** — founder still in CEO seat with multi-year tenure, no recent exec changes
- **Stable, professionalized** — non-founder CEO with tenure, no recent changes
- **In active transition** — one or more recent exec changes (≤9 months); motion direction likely shifting
- **Unstable / churning** — multiple changes in same seat in past 18 months; motion uncertainty high
- **Signal not recovered** — public sources insufficient to commit to a hypothesis; discovery must establish

Output 2-4 paragraphs. Each paragraph commits to a specific observation and its diagnostic implication. Use → for recommendation bullets when applicable. Avoid em dashes; use commas, periods, or colons. Do not use the words: leverage, leveraging, leveraged, synergies, synergy, holistic, streamline, impactful. Use GTM Gap™ on first reference if relevant.

Also produce findings, gaps, and discovery questions if applicable.
```

- [ ] **Step 2: Write failing tests in `tests/test_observed_stability_trajectory.py`**

```python
"""observed_stability_trajectory synthesizer tests."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from rrxray.schemas._shared import Finding
from rrxray.schemas.leadership_stability import (
    CurrentIncumbent, ExecAction, ExecChange, FounderTenure,
    LeadershipStabilityData, NameRegistration,
)
from rrxray.synthesizers.observed_stability_trajectory import (
    NarrativeResponse, _build_aggregates, synthesize,
)


def _full_data():
    from datetime import date, timedelta
    today = date.today()
    return LeadershipStabilityData(
        exec_changes=[
            ExecChange(
                name="Jane Doe", role_canonical="cro", role_raw="CRO",
                action=ExecAction.HIRE,
                occurred_at=today - timedelta(days=120),
                press_url="https://example.com/p/1",
                press_title="x",
            ),
        ],
        current_incumbents=[
            CurrentIncumbent(name="Jane Doe", role_canonical="cro", role_raw="CRO", confidence="high"),
            CurrentIncumbent(name="Founder Person", role_canonical="ceo", role_raw="CEO", confidence="high"),
            CurrentIncumbent(name="Founder Person", role_canonical="founder", role_raw="Founder", confidence="high"),
        ],
        founder_tenure=FounderTenure(inferred_year=2018, source="about_page"),
        name_registrations=[
            NameRegistration(name="Jane Doe", role_descriptor="Acme's CRO", whitelist=True),
            NameRegistration(name="Founder Person", role_descriptor="Acme's CEO", whitelist=False),
        ],
        findings=[
            Finding(text="CRO is in transition; current incumbent in seat ~4 months.",
                    source=None),
        ],
    )


def test_build_aggregates_excludes_names():
    """Aggregates contain zero registered names; only counts and tenures."""
    aggs = _build_aggregates(_full_data())

    s = aggs.model_dump_json()
    assert "Jane Doe" not in s
    assert "Founder Person" not in s


def test_build_aggregates_seat_changes():
    aggs = _build_aggregates(_full_data())
    assert aggs.seat_changes == {"cro": 1}


def test_build_aggregates_recent_changes():
    aggs = _build_aggregates(_full_data())
    assert len(aggs.recent_changes) == 1
    assert aggs.recent_changes[0]["role"] == "cro"


def test_build_aggregates_founder_present_in_ceo_seat():
    aggs = _build_aggregates(_full_data())
    assert aggs.founder_present_in_ceo_seat is True
    assert aggs.founder_tenure_years is not None


def test_build_aggregates_collector_findings_strings():
    aggs = _build_aggregates(_full_data())
    assert aggs.collector_findings == ["CRO is in transition; current incumbent in seat ~4 months."]


def test_synth_skips_when_collector_absent():
    """leadership_stability is None → synthesize returns None."""
    from rrxray.config import Config
    from rrxray.context import SynthesizerContext
    from rrxray.schemas.data import CollectorOutputs

    ctx = SynthesizerContext(
        collector_outputs=CollectorOutputs(),
        anthropic=MagicMock(),
        voice=MagicMock(),
        anonymizer=MagicMock(),
        config=Config(domain="example.com"),
    )
    result = asyncio.run(synthesize(ctx))
    assert result is None


def test_synth_runs_with_full_data():
    """Full data → calls anthropic, returns narrative."""
    from rrxray.config import Config
    from rrxray.context import SynthesizerContext
    from rrxray.schemas._shared import Finding
    from rrxray.schemas.data import CollectorOutputs

    fake_anthropic = MagicMock()
    fake_anthropic.complete_with_cached_system = AsyncMock(return_value=MagicMock(
        parsed=NarrativeResponse(
            narrative_paragraphs=["The CRO change places motion in active transition.", "Founder still in CEO seat for ~8 years."],
            findings=[Finding(text="CRO recently hired.", source=None)],
            gaps=["Tenure of new CRO unknown."],
            discovery_questions=["What does the new CRO see as the priority motion shift?"],
        ),
        model_used="claude-sonnet-4-6",
        cache_hit=False,
    ))

    fake_voice = MagicMock()
    fake_voice.sanitize_llm_output = lambda text, context: text
    fake_voice.process_synthesizer_text = lambda text, context: text

    ctx = SynthesizerContext(
        collector_outputs=CollectorOutputs(leadership_stability=_full_data()),
        anthropic=fake_anthropic,
        voice=fake_voice,
        anonymizer=MagicMock(),
        config=Config(domain="example.com"),
    )
    result = asyncio.run(synthesize(ctx))

    assert result is not None
    assert len(result.narrative_paragraphs) == 2
    assert len(result.findings) == 1
    fake_anthropic.complete_with_cached_system.assert_called_once()


def test_synth_voice_processing_applied():
    """Em-dashes and forbidden words substituted by voice processor."""
    from rrxray.config import Config
    from rrxray.context import SynthesizerContext
    from rrxray.schemas.data import CollectorOutputs

    fake_anthropic = MagicMock()
    fake_anthropic.complete_with_cached_system = AsyncMock(return_value=MagicMock(
        parsed=NarrativeResponse(
            narrative_paragraphs=["Leverage the CRO's momentum — motion is shifting."],
            findings=[],
            gaps=[],
            discovery_questions=[],
        ),
        model_used="claude-sonnet-4-6",
        cache_hit=False,
    ))

    # Real-ish voice processor
    fake_voice = MagicMock()
    fake_voice.sanitize_llm_output = lambda text, context: text.replace("—", ", ").replace("Leverage", "Use")
    fake_voice.process_synthesizer_text = lambda text, context: text

    ctx = SynthesizerContext(
        collector_outputs=CollectorOutputs(leadership_stability=_full_data()),
        anthropic=fake_anthropic,
        voice=fake_voice,
        anonymizer=MagicMock(),
        config=Config(domain="example.com"),
    )
    result = asyncio.run(synthesize(ctx))

    assert "—" not in result.narrative_paragraphs[0]
    assert "Leverage" not in result.narrative_paragraphs[0]
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
/Users/dalezwizinski/Library/Python/3.9/bin/uv run pytest tests/test_observed_stability_trajectory.py -v
```

Expected: ImportError for `rrxray.synthesizers.observed_stability_trajectory`.

- [ ] **Step 4: Create `rrxray/synthesizers/observed_stability_trajectory.py`**

```python
"""Section B synthesizer: observed_stability_trajectory.

Reads from leadership_stability collector. Pre-aggregates the data into a
name-free StabilityAggregates structure before rendering the prompt template.
Names never enter the synthesizer prompt or LLM output.

Future Phase 2 sub-phases (funding_trajectory, customer_concentration) widen
this synthesizer the same way Phase 2.1c widened observed_gtm_motion: add
conditional blocks; the synthesizer body unchanged.
"""
from __future__ import annotations

import logging
from datetime import date
from importlib.resources import files

from jinja2 import Environment
from pydantic import BaseModel, Field

from rrxray.collectors._leadership_stability_catalog import (
    RECENT_THRESHOLD_DAYS, ROLE_DISPLAY,
)
from rrxray.context import SynthesizerContext
from rrxray.schemas._shared import Finding
from rrxray.schemas.data import ObservedStabilityTrajectoryNarrative
from rrxray.schemas.leadership_stability import LeadershipStabilityData


NAME = "observed_stability_trajectory"
log = logging.getLogger(f"rrxray.synthesizers.{NAME}")


class StabilityAggregates(BaseModel):
    """Name-free pre-aggregation passed to the prompt template."""
    seat_changes: dict[str, int]
    recent_changes: list[dict]
    current_incumbents_by_role: dict[str, dict]
    founder_present_in_ceo_seat: bool
    founder_tenure_years: int | None
    seats_with_no_change_18mo: list[str]
    collector_findings: list[str]


class NarrativeResponse(BaseModel):
    """Structured response from the synthesizer."""
    narrative_paragraphs: list[str] = Field(description="2-4 paragraphs committing to a stability/trajectory hypothesis")
    findings: list[Finding] = Field(default=[])
    gaps: list[str] = Field(default=[])
    discovery_questions: list[str] = Field(default=[])


def _load_system_prompt() -> str:
    return files("rrxray.prompts").joinpath("synthesizer_system.md").read_text()


def _build_aggregates(data: LeadershipStabilityData) -> StabilityAggregates:
    """Pre-aggregate LeadershipStabilityData into a name-free structure."""
    today = date.today()

    # Seat-change counts
    seat_changes: dict[str, int] = {}
    for c in data.exec_changes:
        seat_changes[c.role_canonical] = seat_changes.get(c.role_canonical, 0) + 1

    # Recent changes (≤RECENT_THRESHOLD_DAYS)
    recent_changes = []
    for c in data.exec_changes:
        if c.occurred_at is None:
            continue
        days_ago = (today - c.occurred_at).days
        if days_ago <= RECENT_THRESHOLD_DAYS:
            recent_changes.append({
                "role": c.role_canonical,
                "action": c.action.value if hasattr(c.action, "value") else str(c.action),
                "occurred_at_months_ago": max(1, days_ago // 30),
            })

    # Current incumbents — high confidence only; tenure inferred from latest matching change
    incumbents_by_role: dict[str, dict] = {}
    for inc in data.current_incumbents:
        if inc.confidence != "high":
            continue
        # tenure: if there's a recent change in this role, use its months_ago
        tenure_months = None
        latest_change = max(
            (c for c in data.exec_changes
             if c.role_canonical == inc.role_canonical and c.occurred_at is not None),
            key=lambda c: c.occurred_at,
            default=None,
        )
        if latest_change is not None and latest_change.occurred_at is not None:
            tenure_months = max(1, (today - latest_change.occurred_at).days // 30)
        incumbents_by_role[inc.role_canonical] = {
            "tenure_months": tenure_months,
            "confidence": inc.confidence,
        }

    # Founder presence in CEO seat
    founder_names = {i.name for i in data.current_incumbents if i.role_canonical == "founder"}
    ceo_names = {i.name for i in data.current_incumbents if i.role_canonical == "ceo"}
    founder_in_ceo = bool(founder_names & ceo_names)

    founder_tenure_years: int | None = None
    if data.founder_tenure and data.founder_tenure.inferred_year:
        founder_tenure_years = today.year - data.founder_tenure.inferred_year

    # Seats with no change in 18 months — derived from seat_changes vs all known roles
    all_roles = ["ceo", "cro", "vp_sales", "vp_revenue", "cmo", "vp_marketing", "founder"]
    seats_with_no_change = [r for r in all_roles if r not in seat_changes]

    return StabilityAggregates(
        seat_changes=seat_changes,
        recent_changes=recent_changes,
        current_incumbents_by_role=incumbents_by_role,
        founder_present_in_ceo_seat=founder_in_ceo,
        founder_tenure_years=founder_tenure_years,
        seats_with_no_change_18mo=seats_with_no_change,
        collector_findings=[f.text for f in data.findings],
    )


def _render_user_message(domain: str, aggregates: StabilityAggregates) -> str:
    template_text = files("rrxray.prompts").joinpath("observed_stability_trajectory.md").read_text()
    env = Environment(trim_blocks=True, lstrip_blocks=True)
    return env.from_string(template_text).render(
        domain=domain,
        aggregates=aggregates,
    )


async def synthesize(ctx: SynthesizerContext) -> ObservedStabilityTrajectoryNarrative | None:
    leadership = ctx.collector_outputs.leadership_stability
    if leadership is None:
        log.info("leadership_stability collector absent; skipping observed_stability_trajectory synthesis")
        return None

    aggregates = _build_aggregates(leadership)
    system_prompt = _load_system_prompt()
    user_message = _render_user_message(ctx.config.domain, aggregates)

    response = await ctx.anthropic.complete_with_cached_system(
        system_prompt=system_prompt,
        user_message=user_message,
        model=ctx.config.model,
        response_schema=NarrativeResponse,
    )

    def _voice(text: str, ctx_label: str) -> str:
        clean = ctx.voice.sanitize_llm_output(text, context=ctx_label)
        return ctx.voice.process_synthesizer_text(clean, context=ctx_label)

    paragraphs = [_voice(p, f"{NAME} para {i}") for i, p in enumerate(response.parsed.narrative_paragraphs)]
    gaps = [_voice(g, f"{NAME} gap {i}") for i, g in enumerate(response.parsed.gaps)]
    discovery_questions = [_voice(q, f"{NAME} discovery {i}") for i, q in enumerate(response.parsed.discovery_questions)]
    findings = [
        Finding(text=_voice(f.text, f"{NAME} finding {i}"), source=f.source)
        for i, f in enumerate(response.parsed.findings)
    ]

    return ObservedStabilityTrajectoryNarrative(
        narrative_paragraphs=paragraphs,
        findings=findings,
        gaps=gaps,
        discovery_questions=discovery_questions,
        model_used=response.model_used,
        cache_hit=response.cache_hit,
    )
```

- [ ] **Step 5: Run tests + ruff**

```bash
/Users/dalezwizinski/Library/Python/3.9/bin/uv run pytest tests/test_observed_stability_trajectory.py -v
/Users/dalezwizinski/Library/Python/3.9/bin/uv run ruff check rrxray/ tests/
```

Expected: 8 tests pass. Ruff clean.

- [ ] **Step 6: Commit**

```bash
git add rrxray/synthesizers/observed_stability_trajectory.py rrxray/prompts/observed_stability_trajectory.md tests/test_observed_stability_trajectory.py
git commit -m "$(cat <<'EOF'
Add observed_stability_trajectory Section B synthesizer

Reads leadership_stability collector output. Pre-aggregates into a
name-free StabilityAggregates structure (seat counts, recent change
list, current incumbents by role with tenure, founder presence flag,
collector findings) before rendering the prompt template. Names
never enter the synthesizer prompt or LLM output.

Prompt commits the LLM to a single stability-trajectory hypothesis
(stable founder-led / stable professionalized / in active transition /
unstable churning / signal not recovered) rather than enumerating
possibilities. Same voice processing pattern as observed_gtm_motion.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 15: Pipeline registration (COLLECTORS + SYNTHESIZERS)

**Files:**
- Modify: `rrxray/pipeline.py` (append leadership_stability + observed_stability_trajectory)

- [ ] **Step 1: Edit `rrxray/pipeline.py`**

Find the existing imports + COLLECTORS / SYNTHESIZERS lists. Update:

```python
from rrxray.collectors import (
    leadership_stability,
    pricing_packaging,
    revenue_motion,
    tech_stack,
)
from rrxray.synthesizers import observed_gtm_motion, observed_stability_trajectory

COLLECTORS = [
    pricing_packaging,
    tech_stack,
    revenue_motion,
    leadership_stability,
]

SYNTHESIZERS = [
    observed_gtm_motion,
    observed_stability_trajectory,
]
```

- [ ] **Step 2: Add registration test**

Append to `tests/test_pipeline.py`:

```python
def test_collectors_includes_leadership_stability():
    from rrxray import pipeline
    names = [c.NAME for c in pipeline.COLLECTORS]
    assert "leadership_stability" in names


def test_synthesizers_includes_observed_stability_trajectory():
    from rrxray import pipeline
    names = [s.NAME for s in pipeline.SYNTHESIZERS]
    assert "observed_stability_trajectory" in names
```

Also add a test that `data.json` round-trips with full Phase 2.2 output:

```python
def test_data_json_round_trips_with_observed_stability_trajectory():
    from datetime import UTC, datetime
    from rrxray.schemas.data import (
        CollectorOutputs, InputParams, ObservedStabilityTrajectoryNarrative,
        RunMetadata, SynthesizerOutputs, XrayData,
    )

    data = XrayData(
        domain="example.com",
        run_metadata=RunMetadata(
            timestamp=datetime.now(UTC),
            tool_version="0.1",
            modes_built=["internal"],
            model_used="claude-sonnet-4-6",
        ),
        inputs=InputParams(domain="example.com"),
        synthesizers=SynthesizerOutputs(
            observed_stability_trajectory=ObservedStabilityTrajectoryNarrative(
                narrative_paragraphs=["Test paragraph."],
                model_used="claude-sonnet-4-6",
                cache_hit=False,
            ),
        ),
    )
    import json
    restored = XrayData.model_validate(json.loads(data.model_dump_json()))
    assert restored.synthesizers.observed_stability_trajectory.narrative_paragraphs == ["Test paragraph."]
```

- [ ] **Step 3: Run full test suite + ruff (this is the integration moment)**

```bash
/Users/dalezwizinski/Library/Python/3.9/bin/uv run pytest -v 2>&1 | tail -3
/Users/dalezwizinski/Library/Python/3.9/bin/uv run ruff check rrxray/ tests/
```

Expected: ~301 tests passing (251 baseline + ~50 new). Ruff clean.

- [ ] **Step 4: Smoke the dry-run plan**

```bash
/Users/dalezwizinski/Library/Python/3.9/bin/uv run rrxray run --domain example.com --dry-run
```

Expected: dry-run plan output mentions four collectors (pricing_packaging, tech_stack, revenue_motion, leadership_stability) and two synthesizers (observed_gtm_motion, observed_stability_trajectory). Cost estimate updates dynamically.

- [ ] **Step 5: Commit**

```bash
git add rrxray/pipeline.py tests/test_pipeline.py
git commit -m "Register leadership_stability + observed_stability_trajectory in pipeline"
```

---

## Task 16: Quality gate (Dale-led)

**Files:**
- Modify: any prompt/voice file as needed during iteration
- Modify: `roadmap.md` (post-quality-gate, one-line entry)
- Create: `docs/checkpoints/2026-05-09-phase-2.2-leadership-stability-checkpoint.md` (post-merge)

**Bounded by Dale's sign-off, not by time.** The implementer subagent must NOT mark Phase 2.2 complete on its own — it presents output and pauses for Dale's review.

- [ ] **Step 1: Confirm preflight**

```bash
/Users/dalezwizinski/Library/Python/3.9/bin/uv run pytest -v 2>&1 | tail -3
/Users/dalezwizinski/Library/Python/3.9/bin/uv run ruff check rrxray/ tests/
```

Expected: ~301 tests passing. Ruff clean. `.env` has `ANTHROPIC_API_KEY` and `FIRECRAWL_API_KEY` (and `GEMINI_API_KEY` if testing the gemini-flash extractor path).

- [ ] **Step 2: Run live smoke against the four quality-gate domains**

```bash
# Same trio as Phase 2.1c (A/B continuity)
/Users/dalezwizinski/Library/Python/3.9/bin/uv run rrxray run --domain swayable.com
/Users/dalezwizinski/Library/Python/3.9/bin/uv run rrxray run --domain sqaservices.com
/Users/dalezwizinski/Library/Python/3.9/bin/uv run rrxray run --domain linear.app

# Plus one leadership-rich domain — Dale picks at quality-gate time.
# Candidates: a SaaS company with documented recent CRO change (e.g., a public
# vendor whose CRO change was in TechCrunch in past 6-9 months). Dale should
# substitute the actual domain here.
/Users/dalezwizinski/Library/Python/3.9/bin/uv run rrxray run --domain <leadership-rich-domain>
```

Expected: each run completes; report renders Section A (3 collectors) and Section B (1 collector); evidence files written; voice log clean.

- [ ] **Step 3: Run the live smoke a second time using `--extractor=gemini-flash`** (one domain only, to validate the path works end-to-end)

```bash
/Users/dalezwizinski/Library/Python/3.9/bin/uv run rrxray run --domain swayable.com --extractor=gemini-flash
```

Expected: same output shape as Haiku; Gemini Flash extractor returns structured records.

- [ ] **Step 4: Dale-led review of all four reports**

Dale reviews each report's Section B narrative for:

1. **Diagnostic commitment.** Does the synthesizer pick a specific stability hypothesis, or does it enumerate possibilities? Per Phase 2.1b precedent, enumeration is the failure mode to fix.
2. **Voice compliance.** No em dashes; no forbidden words (leverage / synergies / holistic / streamline / impactful); GTM Gap™ on first use if applicable.
3. **Anonymizer correctness.** LinkedIn-only names replaced with role descriptors; press-whitelisted names preserved; no name appears unanonymized in error.
4. **Aggregate-only prompt.** Inspect the synthesizer's user message in evidence; confirm zero names appear.
5. **Findings calibration.** Are the rule-based findings overly aggressive? Too tepid? Adjust thresholds (`RECENT_THRESHOLD_DAYS`, founder tenure cutoff) if needed.

- [ ] **Step 5: Iterate prompt or sanitizer if quality gate flags issues**

Phase 2.1b/c precedent: 1-2 prompt-tuning cycles is normal. Common iterations:

- LLM emits an em dash that the prompt told it not to → already handled by `voice.sanitize_llm_output()`; if a new substitution is needed, extend the table in `rrxray/voice/rr_voice.py` with a brief commit message rationale.
- Synthesizer enumerates possibilities → tighten the prompt's "commit to a single hypothesis" instruction; add a worked example in the prompt.
- Section B narrative talks about specific named individuals → check `_build_aggregates`; should never happen if test_synth_aggregates_exclude_names passes, but the live data may surface an edge case.

After each prompt change, re-run the affected domain only:

```bash
/Users/dalezwizinski/Library/Python/3.9/bin/uv run rrxray run --domain <domain> --no-cache
```

(`--no-cache` forces synthesizer re-run; collector data is reused.)

- [ ] **Step 6: Once Dale signs off, write the checkpoint**

```bash
# Read TEMPLATE first, then create:
cat docs/checkpoints/TEMPLATE.md
```

Write `docs/checkpoints/2026-05-09-phase-2.2-leadership-stability-checkpoint.md` covering:

- Phase status (done; quality gate passed)
- What shipped (collector + synthesizer + GeminiClient + extractor module + CLI flag)
- New / modified files
- Notable commits (chronological)
- Test status (final pytest count + ruff clean)
- Quality gate results table (per domain, per pass/fail)
- Known issues / limitations
- What's queued next (per roadmap: Phase 2.1d content_demand or Phase 2.4 funding_trajectory)
- Process notes (which model handled which task, iterations needed, etc.)
- Pointers to spec, plan, prior checkpoints

Read at least one prior checkpoint (`docs/checkpoints/2026-05-08-phase-2.1c-revenue-motion-checkpoint.md`) before writing for format consistency.

- [ ] **Step 7: Update `roadmap.md` with the Phase 2.2 entry**

Find the Phase 2.2 entry. Add a single line under it:

```
- 2026-05-09: Phase 2.2 shipped — leadership_stability collector + observed_stability_trajectory synthesizer.
  GeminiClient + extractor module added (Haiku default; --extractor=gemini-flash flag).
  ~50 new tests; total ~301 passing; ruff clean.
```

- [ ] **Step 8: Commit checkpoint + roadmap**

```bash
git add docs/checkpoints/2026-05-09-phase-2.2-leadership-stability-checkpoint.md roadmap.md
git commit -m "Phase 2.2 leadership_stability checkpoint + roadmap entry"
```

- [ ] **Step 9: Open PR for Dale review (final merge to main is Dale's call)**

```bash
git push -u origin <branch-name>
gh pr create --title "Phase 2.2: leadership_stability + observed_stability_trajectory" --body "$(cat <<'EOF'
## Summary

- Adds `leadership_stability` collector (first Section B signal): press-release search, LinkedIn current C-suite, founder tenure inference
- Adds `observed_stability_trajectory` synthesizer (Section B; commits to a stability/trajectory hypothesis based on name-free aggregates)
- Adds thin `GeminiClient` (sibling to AnthropicClient; no provider abstraction layer — that stays deferred to Phase 3)
- Adds `extraction` module: HaikuExtractor + GeminiFlashExtractor + factory; `--extractor=gemini-flash` CLI flag (Haiku default)
- Pipeline post-collection anonymizer registration: press names whitelisted, LinkedIn names anonymized to role descriptors
- ~50 new tests; total ~301 passing; ruff clean
- Quality gate signed off by Dale against [4 domains]

## Test plan

- [x] All unit tests pass (~301 total)
- [x] Ruff clean
- [x] Live smoke against Swayable, SQA Services, Linear, plus one leadership-rich domain
- [x] Live smoke with --extractor=gemini-flash on one domain
- [x] Anonymizer behavior verified (whitelisted press names preserved; LinkedIn names replaced)
- [x] Synthesizer commits to a hypothesis on each test domain (no enumeration)
- [x] Voice log clean across all live runs

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Acceptance criteria → task map

| Spec criterion | Verified by tasks |
|---|---|
| 1. Collector registered in `pipeline.COLLECTORS` | T15 (registration), T7 (`test_collector_module_has_NAME`) |
| 2. Synthesizer registered in `pipeline.SYNTHESIZERS` | T15 (`test_synthesizers_includes_observed_stability_trajectory`) |
| 3. GeminiClient + extractors work against mocked SDKs | T1, T2 |
| 4. `--extractor=gemini-flash` picks GeminiFlashExtractor | T6 (CLI test), T2 (`test_make_extractor_picks_gemini_with_flag`) |
| 5. Press releases via 3 per-action queries; deduped by URL | T7 (`test_search_press_releases_*`) |
| 6. LinkedIn current C-suite via 7 per-role queries | T8 (`test_search_linkedin_incumbents_runs_seven_role_queries`) |
| 7. Founder tenure via /about → Wayback fallback | T9 (`test_infer_founder_tenure_*`) |
| 8. Names registered correctly (press whitelist; LinkedIn not) | T10 (`test_build_name_registrations_*`) |
| 9. Pipeline calls anonymizer per `name_registrations` | T12 (`test_pipeline_registers_leadership_stability_name_registrations`) |
| 10. Synthesizer aggregates contain zero registered names | T14 (`test_build_aggregates_excludes_names`), T11 (`test_collect_excludes_names_from_synthesizer_visible_data`) |
| 11. Rule-based findings on the named patterns | T10 (`test_emit_findings_*`) |
| 12. Evidence files written with correct paths | T11 (`test_collect_writes_evidence`) |
| 13. `data.json` round-trips with leadership_stability populated | T5 (`test_data_json_round_trips_with_leadership_stability`), T15 |
| 14. Module Detail Appendix renders Leadership Stability | T13 (`test_leadership_stability_module_detail_renders`) |
| 15. LinkedIn names anonymized; press names preserved | T13 (`test_render_anonymizes_linkedin_names_preserves_press_names`) |
| 16. Live smoke on 4 domains produces Section B narrative | T16 |
| 17. Synthesizer commits to a hypothesis (no enumeration) | T16 (Dale-led review) |
| 18. Quality gate signed off by Dale | T16 |

---

## Model selection per task (per CLAUDE.md model matrix)

| Task | Implementer | Reviewer | Why |
|---|---|---|---|
| T1: GeminiClient | **Opus 4.7** | Haiku 4.5 | Real-logic; new SDK integration; signature drift risk |
| T2: Extractors + factory | **Opus 4.7** | Haiku 4.5 | Real-logic; multi-class duck typing |
| T3: Schemas | Haiku 4.5 | (skip) | Mechanical |
| T4: Catalog | Haiku 4.5 | (skip) | Mechanical |
| T5: data.py | Haiku 4.5 | (skip) | Mechanical |
| T6: Config + CLI | Haiku 4.5 | (skip) | Mechanical |
| T7: Collector skeleton + press search | **Opus 4.7** | Haiku 4.5 | Real-logic; orchestration + extraction |
| T8: LinkedIn search + extract | **Opus 4.7** | Haiku 4.5 | Real-logic; dedup + confidence handling |
| T9: Founder tenure inference | **Opus 4.7** | Haiku 4.5 | Real-logic; F1 + F2 paths + regex parsing |
| T10: Name registrations + findings | **Opus 4.7** | Haiku 4.5 | Real-logic; six-rule findings emitter |
| T11: Evidence + collect orchestration | **Opus 4.7** | Haiku 4.5 | Real-logic; full happy path + total failure |
| T12: Pipeline registration loop | **Opus 4.7** | Haiku 4.5 | Real-logic; pipeline integration is risk-bearing |
| T13: Renderer partial + report | Haiku 4.5 | (skip) | Mechanical (templates + tests) |
| T14: Synthesizer + prompt | **Opus 4.7** | Haiku 4.5 | Real-logic; aggregation + voice; prompt design |
| T15: Pipeline registration | Haiku 4.5 | (skip) | Mechanical (one-line list appends) |
| T16: Quality gate | **Opus 4.7** controller | Dale | Prompt iteration is taste-work |

---

## Risks and known mitigations

- **Press-release Google indexing patchy.** Three per-action queries give us reasonable coverage. Quality gate's leadership-rich domain stress-tests this.
- **LLM extractor hallucinates roles for ambiguous snippets.** `is_relevant: bool` field with explicit prompt instruction "only set is_relevant=True if both name and role are clearly stated."
- **LinkedIn snippet quality varies.** `confidence='low'` filter at synthesizer aggregation; absence framed as "leadership signal not recovered" rather than "no leadership."
- **Founder tenure coarse.** Regex misses prose phrasings; defaults to Wayback fallback; in-narrative framing acknowledges approximate.
- **Gemini Flash structured output reliability.** Extractor catches pydantic validation error and returns None; quality gate surfaces if materially worse than Haiku.
- **`google-genai` is a new dependency.** Approved by Dale at spec review.
- **`gemini-2.0-flash` model name may shift.** If google-genai SDK changes the model identifier, update the default in `gemini_client.py` and `extraction.py`. Document in checkpoint if it changes during this phase.

---

## Out-of-scope reminders

- Wayback /team/about/leadership page diffing across snapshots — Phase 2.2-deep candidate.
- `services/llm.py` provider abstraction — Phase 3.
- CFO / COO / CTO / CPO leadership tracking — narrowed scope per Q2.
- Multi-language press release extraction — best-effort; documented limitation.
- Date-precision better than year on `ExecChange.occurred_at` — accepted limitation; many search snippets don't expose clear dates.

