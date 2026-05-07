# rrxray Phase 2.1a tech_stack Collector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the `tech_stack` collector end-to-end as the first non-pricing collector. Detects analytics, marketing, and CRM tooling on a domain's homepage via two-tier (strict + loose) regex signatures across 9 GTM categories. No synthesizer change in this cycle.

**Architecture:** Module-pattern collector matching the Phase 1 `pricing_packaging` shape. Catalog of ~40 signatures lives in a sibling Python module; the collector imports it, compiles patterns once at import time, and runs them against scraped HTML. Rule-based findings/gaps/discovery_questions (no LLM in collector path). New schema, new field on `CollectorOutputs`, new Jinja partial for the Module Detail Appendix, and one-line append to `pipeline.COLLECTORS`.

**Tech Stack:** Python 3.12+, pydantic v2, jinja2 (existing), pytest + pytest-asyncio (existing), ruff (existing). No new dependencies.

**Spec reference:** [docs/superpowers/specs/2026-05-07-rrxray-phase-2.1a-tech-stack-design.md](../specs/2026-05-07-rrxray-phase-2.1a-tech-stack-design.md)

---

## File Structure

`[T#]` indicates the task that creates or modifies each file.

```
rrxray/
  collectors/
    pricing_packaging.py                              [pre-existing, untouched]
    tech_stack.py                                     [T4-T6: collector entry point]
    _tech_stack_catalog.py                            [T3: signature catalog]
  schemas/
    pricing_packaging.py                              [pre-existing, untouched]
    tech_stack.py                                     [T1: TechStackData, DetectedTool, Category]
    data.py                                           [T2: add tech_stack field on CollectorOutputs]
  pipeline.py                                         [T8: append tech_stack to COLLECTORS]
templates/
  _pricing_detail.md.jinja                            [pre-existing, untouched]
  _tech_stack_detail.md.jinja                         [T7: new partial]
  report_internal.md.jinja                            [T7: include the new partial in Module Detail]
tests/
  test_tech_stack.py                                  [T4-T6: collector tests]
  test_tech_stack_catalog.py                          [T3: catalog tests]
  fixtures/synthetic/tech_stack/                      [T4-T6: synthetic HTML fixtures]
    .gitkeep                                          [T3]
    hubspot_strict.html                               [T4]
    hubspot_loose.html                                [T4]
    multi_tool.html                                   [T4]
    empty.html                                        [T4]
    chat_without_map.html                             [T5]
```

---

## Task overview

8 tasks. Each follows TDD discipline (test first, fail, implement, pass, commit). Total roughly 2-3 hours of subagent execution at full review depth.

- **T1: TechStackData + DetectedTool schemas** (pure pydantic; foundation for everything else)
- **T2: Add `tech_stack` field to CollectorOutputs** (one field + forward ref + model_rebuild)
- **T3: Tool catalog** (`_tech_stack_catalog.py` with 30+ signatures + catalog integrity tests)
- **T4: Detection logic** (`_compile_signatures`, `_detect` with strict-overrides-loose semantics)
- **T5: Rule-based findings emission** (`_emit_findings` for various detection patterns)
- **T6: Evidence writing + `collect()` orchestration** (FirecrawlError handling + source citations + evidence files)
- **T7: Renderer template + integration** (new partial + main template change + render tests)
- **T8: Pipeline registration + smoke test** (append to COLLECTORS, end-to-end pipeline test)

---

## Task 1: TechStackData + DetectedTool schemas

**Files:**
- Create: `rrxray/schemas/tech_stack.py`
- Create: `tests/test_tech_stack_schemas.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_tech_stack_schemas.py`:

```python
"""TechStackData / DetectedTool schema round-trip + validation."""
import json

import pytest
from pydantic import ValidationError

from rrxray.schemas.tech_stack import Category, DetectedTool, TechStackData


def test_detected_tool_minimal():
    t = DetectedTool(
        name="HubSpot",
        category="marketing_automation",
        confidence="high",
        signature_id="hubspot:strict_js",
        matched_text="https://js.hs-scripts.com/12345.js",
    )
    assert t.name == "HubSpot"
    assert t.confidence == "high"


def test_detected_tool_rejects_invalid_category():
    with pytest.raises(ValidationError):
        DetectedTool(
            name="x",
            category="not_a_category",  # type: ignore[arg-type]
            confidence="high",
            signature_id="x",
            matched_text="x",
        )


def test_detected_tool_rejects_invalid_confidence():
    with pytest.raises(ValidationError):
        DetectedTool(
            name="x",
            category="analytics",
            confidence="medium",  # type: ignore[arg-type]
            signature_id="x",
            matched_text="x",
        )


def test_tech_stack_data_defaults_empty():
    d = TechStackData()
    assert d.detected_tools == []
    assert d.categories_observed == []
    assert d.categories_absent == []
    assert d.findings == []
    assert d.gaps == []
    assert d.discovery_questions == []
    assert d.sources == []


def test_tech_stack_data_round_trips_through_json():
    d = TechStackData(
        detected_tools=[
            DetectedTool(
                name="HubSpot", category="marketing_automation", confidence="high",
                signature_id="hubspot:strict_js", matched_text="js.hs-scripts.com/123.js",
            ),
        ],
        categories_observed=["marketing_automation"],
        categories_absent=["analytics", "tag_manager"],
        gaps=["No analytics detected"],
    )
    serialized = d.model_dump_json()
    restored = TechStackData.model_validate(json.loads(serialized))
    assert len(restored.detected_tools) == 1
    assert restored.detected_tools[0].name == "HubSpot"
    assert restored.categories_observed == ["marketing_automation"]


def test_category_literal_includes_all_nine():
    """Category Literal must include all 9 GTM categories named in the spec."""
    expected = {
        "analytics", "tag_manager", "marketing_automation", "chat",
        "product_analytics", "crm", "cdp", "ab_testing", "attribution",
    }
    # Pydantic stores the Literal args; cross-check via a probe
    for cat in expected:
        DetectedTool(
            name="probe", category=cat, confidence="high",  # type: ignore[arg-type]
            signature_id="x", matched_text="x",
        )
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_tech_stack_schemas.py -v
```

Expected: ERRORS (`ModuleNotFoundError: No module named 'rrxray.schemas.tech_stack'`)

- [ ] **Step 3: Implement `rrxray/schemas/tech_stack.py`**

```python
"""Schemas specific to the tech_stack collector."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from rrxray.schemas._shared import Finding, SourceCitation

Category = Literal[
    "analytics",
    "tag_manager",
    "marketing_automation",
    "chat",
    "product_analytics",
    "crm",
    "cdp",
    "ab_testing",
    "attribution",
]


class DetectedTool(BaseModel):
    name: str
    category: Category
    confidence: Literal["high", "low"]
    signature_id: str
    matched_text: str


class TechStackData(BaseModel):
    detected_tools: list[DetectedTool] = []
    categories_observed: list[Category] = []
    categories_absent: list[Category] = []
    findings: list[Finding] = []
    gaps: list[str] = []
    discovery_questions: list[str] = []
    sources: list[SourceCitation] = []
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_tech_stack_schemas.py -v
```

Expected: 6 tests pass.

- [ ] **Step 5: Run ruff**

```bash
uv run ruff check rrxray/ tests/
```

Expected: All checks passed.

- [ ] **Step 6: Commit**

```bash
git add rrxray/schemas/tech_stack.py tests/test_tech_stack_schemas.py
git commit -m "Add TechStackData and DetectedTool schemas"
```

---

## Task 2: Add `tech_stack` field to CollectorOutputs

**Files:**
- Modify: `rrxray/schemas/data.py` (add field + forward-ref import + model_rebuild)
- Modify: `tests/test_schemas.py` (verify CollectorOutputs accepts the new field)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_schemas.py`:

```python
def test_collector_outputs_has_tech_stack_field():
    """CollectorOutputs must accept a tech_stack field."""
    from rrxray.schemas.data import CollectorOutputs
    from rrxray.schemas.tech_stack import TechStackData

    co = CollectorOutputs(tech_stack=TechStackData())
    assert co.tech_stack is not None
    assert isinstance(co.tech_stack, TechStackData)


def test_collector_outputs_tech_stack_defaults_none():
    from rrxray.schemas.data import CollectorOutputs

    co = CollectorOutputs()
    assert co.tech_stack is None


def test_collector_outputs_tech_stack_round_trips():
    import json
    from rrxray.schemas.data import CollectorOutputs
    from rrxray.schemas.tech_stack import DetectedTool, TechStackData

    co = CollectorOutputs(tech_stack=TechStackData(
        detected_tools=[DetectedTool(
            name="HubSpot", category="marketing_automation", confidence="high",
            signature_id="hubspot:strict_js", matched_text="x",
        )],
    ))
    serialized = co.model_dump_json()
    restored = CollectorOutputs.model_validate(json.loads(serialized))
    assert restored.tech_stack is not None
    assert restored.tech_stack.detected_tools[0].name == "HubSpot"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_schemas.py -v -k tech_stack
```

Expected: 3 tests fail (CollectorOutputs has no `tech_stack` attribute).

- [ ] **Step 3: Modify `rrxray/schemas/data.py`**

Locate the `CollectorOutputs` class. Add the `tech_stack` field as a forward reference, mirroring the existing `pricing_packaging` pattern:

```python
class CollectorOutputs(BaseModel):
    """One field per collector. None = not run or failed gracefully."""
    model_config = ConfigDict(validate_assignment=True)
    pricing_packaging: "PricingPackagingData | None" = None  # forward ref
    tech_stack: "TechStackData | None" = None  # forward ref
```

Then at the very bottom of the file, after the existing `from rrxray.schemas.pricing_packaging import PricingPackagingData` import and the existing `CollectorOutputs.model_rebuild()` call, add the import for `TechStackData` and re-run `model_rebuild()`:

```python
# Resolve forward references
from rrxray.schemas.pricing_packaging import PricingPackagingData  # noqa: E402
from rrxray.schemas.tech_stack import TechStackData  # noqa: E402

CollectorOutputs.model_rebuild()
```

(If the file already does the rebuild after the pricing_packaging import alone, replace it with the version above so both forward refs resolve in the single rebuild call.)

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_schemas.py -v
uv run pytest -v 2>&1 | tail -5
```

Expected: All schema tests pass; full suite stays green (130+ tests).

- [ ] **Step 5: Run ruff**

```bash
uv run ruff check rrxray/ tests/
```

Expected: All checks passed.

- [ ] **Step 6: Commit**

```bash
git add rrxray/schemas/data.py tests/test_schemas.py
git commit -m "Add tech_stack field to CollectorOutputs"
```

---

## Task 3: Tool catalog

**Files:**
- Create: `rrxray/collectors/_tech_stack_catalog.py`
- Create: `tests/test_tech_stack_catalog.py`
- Create: `tests/fixtures/synthetic/tech_stack/.gitkeep`

- [ ] **Step 1: Write the failing test**

Create `tests/test_tech_stack_catalog.py`:

```python
"""Catalog integrity tests: every signature is well-formed and compiles."""
import re

from rrxray.collectors._tech_stack_catalog import CATEGORIES, SIGNATURES


def test_catalog_has_at_least_30_signatures():
    """Spec mandate: ~40 signatures spanning all categories. Allow some leeway."""
    assert len(SIGNATURES) >= 30


def test_categories_constant_has_nine_entries():
    expected = {
        "analytics", "tag_manager", "marketing_automation", "chat",
        "product_analytics", "crm", "cdp", "ab_testing", "attribution",
    }
    assert set(CATEGORIES) == expected
    assert len(CATEGORIES) == 9


def test_every_signature_has_required_keys():
    required = {"tool", "category", "id", "pattern", "confidence"}
    for sig in SIGNATURES:
        missing = required - set(sig.keys())
        assert not missing, f"signature {sig.get('id')!r} missing keys: {missing}"


def test_every_category_in_signatures_is_valid():
    valid = set(CATEGORIES)
    for sig in SIGNATURES:
        assert sig["category"] in valid, (
            f"signature {sig['id']!r} has invalid category {sig['category']!r}"
        )


def test_every_confidence_is_high_or_low():
    for sig in SIGNATURES:
        assert sig["confidence"] in ("high", "low"), (
            f"signature {sig['id']!r} has invalid confidence {sig['confidence']!r}"
        )


def test_signature_ids_are_unique():
    ids = [sig["id"] for sig in SIGNATURES]
    assert len(ids) == len(set(ids)), (
        f"duplicate signature ids: {[i for i in ids if ids.count(i) > 1]}"
    )


def test_every_pattern_compiles():
    for sig in SIGNATURES:
        try:
            re.compile(sig["pattern"], re.IGNORECASE)
        except re.error as e:
            raise AssertionError(
                f"signature {sig['id']!r} has invalid pattern {sig['pattern']!r}: {e}"
            ) from e


def test_catalog_covers_all_nine_categories():
    """Every category should have at least one signature so absence-detection works."""
    covered = {sig["category"] for sig in SIGNATURES}
    missing = set(CATEGORIES) - covered
    assert not missing, f"categories with no signatures: {missing}"


def test_catalog_includes_specs_named_tools():
    """Spec named: Segment, GTM, HubSpot, Marketo, Intercom, Drift, Pendo, Salesforce W2L."""
    tool_names = {sig["tool"] for sig in SIGNATURES}
    expected = {
        "Segment", "Google Tag Manager", "HubSpot", "Marketo",
        "Intercom", "Drift", "Pendo", "Salesforce Web-to-Lead",
    }
    missing = expected - tool_names
    assert not missing, f"spec-named tools missing from catalog: {missing}"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_tech_stack_catalog.py -v
```

Expected: ERRORS (`ModuleNotFoundError: No module named 'rrxray.collectors._tech_stack_catalog'`).

- [ ] **Step 3: Implement `rrxray/collectors/_tech_stack_catalog.py`**

```python
"""Tool-detection signatures for the tech_stack collector.

Each entry is a dict with:
- tool: display name (e.g., "HubSpot")
- category: one of CATEGORIES below
- id: stable identifier for audit (e.g., "hubspot:strict_js")
- pattern: Python regex; matched case-insensitively against scraped HTML
- confidence: "high" (specific signature, near-zero false-positive rate) or "low"
              (loose heuristic that may catch installations missed by strict patterns)

Adding a tool: append a dict to SIGNATURES. Tests will catch regex errors,
duplicate ids, and invalid categories at import-time.
"""
from __future__ import annotations

CATEGORIES: list[str] = [
    "analytics",
    "tag_manager",
    "marketing_automation",
    "chat",
    "product_analytics",
    "crm",
    "cdp",
    "ab_testing",
    "attribution",
]


SIGNATURES: list[dict[str, str]] = [
    # ---- analytics ----
    {"tool": "Google Analytics 4", "category": "analytics", "id": "ga4:strict_gtag",
     "pattern": r"\bgtag\s*\(\s*['\"]config['\"]\s*,\s*['\"]G-[A-Z0-9]+['\"]",
     "confidence": "high"},
    {"tool": "Google Analytics 4", "category": "analytics", "id": "ga4:loose_id",
     "pattern": r"\bG-[A-Z0-9]{6,12}\b", "confidence": "low"},
    {"tool": "Mixpanel", "category": "analytics", "id": "mixpanel:strict_lib",
     "pattern": r"cdn\.mxpnl\.com/libs/mixpanel-[0-9.]+\.min\.js", "confidence": "high"},
    {"tool": "Amplitude", "category": "analytics", "id": "amplitude:strict_lib",
     "pattern": r"cdn\.amplitude\.com/(?:libs/)?amplitude(?:-analytics)?[-./0-9a-z]*\.js",
     "confidence": "high"},
    {"tool": "Plausible", "category": "analytics", "id": "plausible:strict_script",
     "pattern": r"plausible\.io/js/(?:plausible|script)\.[a-z0-9.-]+\.js", "confidence": "high"},
    {"tool": "Fathom", "category": "analytics", "id": "fathom:strict_script",
     "pattern": r"cdn\.usefathom\.com/script\.js", "confidence": "high"},

    # ---- tag_manager ----
    {"tool": "Google Tag Manager", "category": "tag_manager", "id": "gtm:strict_dataLayer",
     "pattern": r"googletagmanager\.com/gtm\.js\?id=GTM-[A-Z0-9]+", "confidence": "high"},
    {"tool": "Google Tag Manager", "category": "tag_manager", "id": "gtm:loose_id",
     "pattern": r"\bGTM-[A-Z0-9]{6,8}\b", "confidence": "low"},
    {"tool": "Tealium", "category": "tag_manager", "id": "tealium:strict_lib",
     "pattern": r"tags\.tiqcdn\.com/utag/[a-z0-9_-]+/[a-z0-9_-]+/[a-z0-9_-]+/utag\.js",
     "confidence": "high"},

    # ---- marketing_automation ----
    {"tool": "HubSpot", "category": "marketing_automation", "id": "hubspot:strict_js",
     "pattern": r"js\.hs-scripts\.com/\d+\.js", "confidence": "high"},
    {"tool": "HubSpot", "category": "marketing_automation", "id": "hubspot:loose_form",
     "pattern": r"hsforms\.net|hsforms\.com|hubspot\.com/forms", "confidence": "low"},
    {"tool": "Marketo", "category": "marketing_automation", "id": "marketo:strict_munchkin",
     "pattern": r"munchkin\.marketo\.net/munchkin\.js", "confidence": "high"},
    {"tool": "Marketo", "category": "marketing_automation", "id": "marketo:loose_form",
     "pattern": r"\bMktoForms2\b", "confidence": "low"},
    {"tool": "Pardot", "category": "marketing_automation", "id": "pardot:strict_pi",
     "pattern": r"pi\.pardot\.com/pd\.js|go\.pardot\.com", "confidence": "high"},
    {"tool": "ActiveCampaign", "category": "marketing_automation", "id": "activecampaign:strict",
     "pattern": r"trackcmp\.net/visit\?actid=", "confidence": "high"},

    # ---- chat ----
    {"tool": "Intercom", "category": "chat", "id": "intercom:strict_widget",
     "pattern": r"widget\.intercom\.io/widget/[a-z0-9]+", "confidence": "high"},
    {"tool": "Intercom", "category": "chat", "id": "intercom:loose_settings",
     "pattern": r"\bintercomSettings\b", "confidence": "low"},
    {"tool": "Drift", "category": "chat", "id": "drift:strict_js",
     "pattern": r"js\.driftt?\.com/include/[A-Za-z0-9_]+/[a-z0-9]+\.js", "confidence": "high"},
    {"tool": "Drift", "category": "chat", "id": "drift:loose_global",
     "pattern": r"\bwindow\.drift\b|drift\.load\(", "confidence": "low"},
    {"tool": "Zendesk Chat", "category": "chat", "id": "zendesk_chat:strict_widget",
     "pattern": r"static\.zdassets\.com/ekr/snippet\.js", "confidence": "high"},
    {"tool": "Crisp", "category": "chat", "id": "crisp:strict_lib",
     "pattern": r"client\.crisp\.chat/l\.js", "confidence": "high"},

    # ---- product_analytics ----
    {"tool": "Pendo", "category": "product_analytics", "id": "pendo:strict_agent",
     "pattern": r"cdn\.pendo\.io/agent/static/[a-f0-9-]+/pendo\.js", "confidence": "high"},
    {"tool": "Pendo", "category": "product_analytics", "id": "pendo:loose_init",
     "pattern": r"\bpendo\.initialize\(", "confidence": "low"},
    {"tool": "Heap", "category": "product_analytics", "id": "heap:strict_lib",
     "pattern": r"cdn\.heapanalytics\.com/js/heap-\d+\.js", "confidence": "high"},
    {"tool": "FullStory", "category": "product_analytics", "id": "fullstory:strict_lib",
     "pattern": r"edge\.fullstory\.com/s/fs\.js", "confidence": "high"},
    {"tool": "LogRocket", "category": "product_analytics", "id": "logrocket:strict_lib",
     "pattern": r"cdn\.lr-(?:in|ingest)\.com/LogRocket\.min\.js|cdn\.logrocket\.io",
     "confidence": "high"},

    # ---- crm ----
    {"tool": "Salesforce Web-to-Lead", "category": "crm", "id": "sfdc:strict_w2l",
     "pattern": r"webto\.salesforce\.com/servlet/servlet\.WebToLead",
     "confidence": "high"},
    {"tool": "HubSpot CRM", "category": "crm", "id": "hubspot_crm:loose_meetings",
     "pattern": r"meetings\.hubspot\.com|app\.hubspot\.com/meetings", "confidence": "low"},

    # ---- cdp ----
    {"tool": "Segment", "category": "cdp", "id": "segment:strict_analytics",
     "pattern": r"cdn\.segment\.com/analytics\.js/v1/[A-Za-z0-9]+/analytics\.min\.js",
     "confidence": "high"},
    {"tool": "Segment", "category": "cdp", "id": "segment:loose_global",
     "pattern": r"\banalytics\.load\(\s*['\"][A-Za-z0-9]+['\"]", "confidence": "low"},
    {"tool": "Rudderstack", "category": "cdp", "id": "rudderstack:strict_lib",
     "pattern": r"cdn\.rudderlabs\.com/v1\.\d+/rudder-analytics\.min\.js",
     "confidence": "high"},

    # ---- ab_testing ----
    {"tool": "Optimizely", "category": "ab_testing", "id": "optimizely:strict_lib",
     "pattern": r"cdn\.optimizely\.com/js/\d+\.js", "confidence": "high"},
    {"tool": "VWO", "category": "ab_testing", "id": "vwo:strict_lib",
     "pattern": r"dev\.visualwebsiteoptimizer\.com/lib/\d+\.js", "confidence": "high"},
    {"tool": "LaunchDarkly", "category": "ab_testing", "id": "launchdarkly:strict_lib",
     "pattern": r"app\.launchdarkly\.com/snippet/ldclient", "confidence": "high"},

    # ---- attribution ----
    {"tool": "Demandbase", "category": "attribution", "id": "demandbase:strict_lib",
     "pattern": r"tag\.demandbase\.com/[A-Za-z0-9_]+\.min\.js", "confidence": "high"},
    {"tool": "6sense", "category": "attribution", "id": "sixsense:strict_lib",
     "pattern": r"j\.6sc\.co/[A-Za-z0-9_]+\.js", "confidence": "high"},
    {"tool": "Bizible", "category": "attribution", "id": "bizible:strict_lib",
     "pattern": r"cdn\.bizible\.com/scripts/bizible\.js", "confidence": "high"},
    {"tool": "Clearbit Reveal", "category": "attribution", "id": "clearbit:strict_reveal",
     "pattern": r"x\.clearbitjs\.com/v\d+/clearbit\.js", "confidence": "high"},
]
```

That's 38 entries spanning all 9 categories, including all 8 spec-named tools. Catalog tests will validate at import time.

- [ ] **Step 4: Create the synthetic-fixtures directory marker**

```bash
mkdir -p tests/fixtures/synthetic/tech_stack
touch tests/fixtures/synthetic/tech_stack/.gitkeep
```

- [ ] **Step 5: Run test to verify it passes**

```bash
uv run pytest tests/test_tech_stack_catalog.py -v
```

Expected: 9 tests pass.

- [ ] **Step 6: Run ruff**

```bash
uv run ruff check rrxray/ tests/
```

Expected: All checks passed.

- [ ] **Step 7: Commit**

```bash
git add rrxray/collectors/_tech_stack_catalog.py tests/test_tech_stack_catalog.py tests/fixtures/synthetic/tech_stack/.gitkeep
git commit -m "Add tech_stack signature catalog (38 tools, 9 categories)"
```

---

## Task 4: Detection logic

**Files:**
- Create: `rrxray/collectors/tech_stack.py` (initial version with `_compile_signatures` + `_detect`)
- Create: `tests/test_tech_stack.py` (detection tests + fixture HTML files)
- Create: `tests/fixtures/synthetic/tech_stack/hubspot_strict.html`
- Create: `tests/fixtures/synthetic/tech_stack/hubspot_loose.html`
- Create: `tests/fixtures/synthetic/tech_stack/multi_tool.html`
- Create: `tests/fixtures/synthetic/tech_stack/empty.html`

- [ ] **Step 1: Create the synthetic HTML fixtures**

Create `tests/fixtures/synthetic/tech_stack/hubspot_strict.html`:

```html
<!doctype html>
<html><head>
<script src="https://js.hs-scripts.com/12345.js"></script>
</head><body><h1>Test</h1></body></html>
```

Create `tests/fixtures/synthetic/tech_stack/hubspot_loose.html`:

```html
<!doctype html>
<html><head></head>
<body>
<form action="https://forms.hsforms.net/12345/abcde">
  <input name="email">
</form>
</body></html>
```

Create `tests/fixtures/synthetic/tech_stack/multi_tool.html`:

```html
<!doctype html>
<html><head>
<script src="https://js.hs-scripts.com/9999.js"></script>
<script src="https://cdn.pendo.io/agent/static/abc123-def456/pendo.js"></script>
<script src="https://widget.intercom.io/widget/abc12345"></script>
<script async src="https://www.googletagmanager.com/gtm.js?id=GTM-ABC1234"></script>
<script>
  gtag('config', 'G-XYZ12345');
</script>
</head><body><h1>Multi-tool</h1></body></html>
```

Create `tests/fixtures/synthetic/tech_stack/empty.html`:

```html
<!doctype html>
<html><head><title>Plain</title></head><body><p>No tags here.</p></body></html>
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_tech_stack.py`:

```python
"""tech_stack collector tests."""
from pathlib import Path

import pytest

from rrxray.collectors import tech_stack


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "synthetic" / "tech_stack"


def _load(name: str) -> str:
    return (FIXTURE_DIR / name).read_text()


def test_detect_hubspot_strict_returns_high_confidence():
    html = _load("hubspot_strict.html")
    detected = tech_stack._detect(html)
    assert len(detected) == 1
    assert detected[0].name == "HubSpot"
    assert detected[0].confidence == "high"
    assert detected[0].category == "marketing_automation"
    assert detected[0].signature_id == "hubspot:strict_js"
    assert "hs-scripts.com" in detected[0].matched_text


def test_detect_hubspot_loose_returns_low_confidence():
    html = _load("hubspot_loose.html")
    detected = tech_stack._detect(html)
    assert len(detected) == 1
    assert detected[0].name == "HubSpot"
    assert detected[0].confidence == "low"


def test_strict_overrides_loose_for_same_tool():
    """When both strict and loose signatures match for one tool, keep the high-confidence one."""
    html = """
    <html><head>
    <script src="https://js.hs-scripts.com/12345.js"></script>
    <form action="https://forms.hsforms.net/12345/abcde">
    </form>
    </head></html>
    """
    detected = tech_stack._detect(html)
    hubspot_detections = [t for t in detected if t.name == "HubSpot"]
    assert len(hubspot_detections) == 1
    assert hubspot_detections[0].confidence == "high"


def test_detect_multi_tool_html():
    html = _load("multi_tool.html")
    detected = tech_stack._detect(html)
    names = {t.name for t in detected}
    assert "HubSpot" in names
    assert "Pendo" in names
    assert "Intercom" in names
    assert "Google Tag Manager" in names
    assert "Google Analytics 4" in names


def test_detect_empty_html_returns_no_detections():
    html = _load("empty.html")
    detected = tech_stack._detect(html)
    assert detected == []


def test_detect_results_sorted_by_category_then_name():
    html = _load("multi_tool.html")
    detected = tech_stack._detect(html)
    sort_keys = [(t.category, t.name) for t in detected]
    assert sort_keys == sorted(sort_keys)


def test_matched_text_truncated_to_100_chars():
    """Long matches must be truncated for evidence."""
    very_long_match = (
        "https://js.hs-scripts.com/12345" + "0" * 200 + ".js"
    )
    html = f"<script src='{very_long_match}'></script>"
    detected = tech_stack._detect(html)
    if detected:
        assert len(detected[0].matched_text) <= 100
```

- [ ] **Step 3: Run test to verify it fails**

```bash
uv run pytest tests/test_tech_stack.py -v
```

Expected: ERRORS (`ImportError` or `AttributeError: module 'rrxray.collectors.tech_stack' has no attribute '_detect'`).

- [ ] **Step 4: Implement `rrxray/collectors/tech_stack.py` (detection layer only)**

```python
"""tech_stack collector: detects analytics/martech/CRM tools by HTML signature matching."""
from __future__ import annotations

import logging
import re

from rrxray.collectors._tech_stack_catalog import CATEGORIES, SIGNATURES
from rrxray.schemas.tech_stack import DetectedTool

NAME = "tech_stack"
log = logging.getLogger(f"rrxray.collectors.{NAME}")


def _compile_signatures() -> list[dict[str, object]]:
    """Pre-compile every signature regex once at module load time."""
    compiled: list[dict[str, object]] = []
    for sig in SIGNATURES:
        compiled.append({
            **sig,
            "compiled": re.compile(sig["pattern"], re.IGNORECASE),
        })
    return compiled


_COMPILED = _compile_signatures()


def _detect(html: str) -> list[DetectedTool]:
    """Run every compiled signature against the HTML.

    Returns one DetectedTool per tool name; if both strict and loose signatures
    match for the same tool, the higher-confidence detection wins.

    Results are sorted by (category, name) for deterministic output across runs.
    """
    matches: dict[str, DetectedTool] = {}
    for sig in _COMPILED:
        m = sig["compiled"].search(html)  # type: ignore[union-attr]
        if not m:
            continue

        existing = matches.get(sig["tool"])  # type: ignore[arg-type]
        new_conf = sig["confidence"]

        # Keep the higher-confidence detection per tool name
        if existing and existing.confidence == "high" and new_conf == "low":
            continue

        matches[sig["tool"]] = DetectedTool(  # type: ignore[arg-type]
            name=sig["tool"],  # type: ignore[arg-type]
            category=sig["category"],  # type: ignore[arg-type]
            confidence=new_conf,  # type: ignore[arg-type]
            signature_id=sig["id"],  # type: ignore[arg-type]
            matched_text=m.group(0)[:100],
        )
    return sorted(matches.values(), key=lambda t: (t.category, t.name))
```

- [ ] **Step 5: Run test to verify it passes**

```bash
uv run pytest tests/test_tech_stack.py -v
```

Expected: 7 tests pass.

- [ ] **Step 6: Run ruff**

```bash
uv run ruff check rrxray/ tests/
```

Expected: All checks passed.

- [ ] **Step 7: Commit**

```bash
git add rrxray/collectors/tech_stack.py tests/test_tech_stack.py tests/fixtures/synthetic/tech_stack/*.html
git commit -m "Add tech_stack detection logic (compiles signatures, dedupes by confidence)"
```

---

## Task 5: Rule-based findings emission

**Files:**
- Modify: `rrxray/collectors/tech_stack.py` (add `_emit_findings`)
- Modify: `tests/test_tech_stack.py` (append findings tests)
- Create: `tests/fixtures/synthetic/tech_stack/chat_without_map.html`

- [ ] **Step 1: Create the additional fixture**

Create `tests/fixtures/synthetic/tech_stack/chat_without_map.html`:

```html
<!doctype html>
<html><head>
<script src="https://widget.intercom.io/widget/abc12345"></script>
</head><body><p>Chat only, no marketing automation.</p></body></html>
```

- [ ] **Step 2: Append failing tests to `tests/test_tech_stack.py`**

```python
from datetime import UTC, datetime


def _now():
    return datetime(2026, 5, 7, 12, 0, tzinfo=UTC)


def test_no_detections_emits_finding():
    detected = []
    findings, gaps, questions = tech_stack._emit_findings(
        detected, "example.com", "https://example.com", _now(),
    )
    assert len(findings) == 1
    assert "no analytics" in findings[0].text.lower() or "no tags" in findings[0].text.lower()
    assert questions  # at least one discovery question


def test_marketing_automation_without_crm_emits_finding():
    from rrxray.schemas.tech_stack import DetectedTool

    detected = [DetectedTool(
        name="HubSpot", category="marketing_automation", confidence="high",
        signature_id="hubspot:strict_js", matched_text="x",
    )]
    findings, _gaps, _q = tech_stack._emit_findings(
        detected, "example.com", "https://example.com", _now(),
    )
    finding_texts = " ".join(f.text.lower() for f in findings)
    assert "marketing automation" in finding_texts
    assert "crm" in finding_texts


def test_chat_without_marketing_automation_emits_gap():
    from rrxray.schemas.tech_stack import DetectedTool

    detected = [DetectedTool(
        name="Intercom", category="chat", confidence="high",
        signature_id="intercom:strict_widget", matched_text="x",
    )]
    _findings, gaps, _q = tech_stack._emit_findings(
        detected, "example.com", "https://example.com", _now(),
    )
    gap_text = " ".join(gaps).lower()
    assert "chat" in gap_text
    assert "nurture" in gap_text or "marketing automation" in gap_text


def test_product_analytics_emits_discovery_question():
    from rrxray.schemas.tech_stack import DetectedTool

    detected = [DetectedTool(
        name="Pendo", category="product_analytics", confidence="high",
        signature_id="pendo:strict_agent", matched_text="x",
    )]
    _findings, _gaps, questions = tech_stack._emit_findings(
        detected, "example.com", "https://example.com", _now(),
    )
    q_text = " ".join(questions).lower()
    assert "activation" in q_text or "time-to-value" in q_text or "product" in q_text


def test_no_analytics_or_tag_manager_emits_gap():
    """When neither analytics nor tag_manager is detected, emit a gap."""
    from rrxray.schemas.tech_stack import DetectedTool

    detected = [DetectedTool(
        name="HubSpot", category="marketing_automation", confidence="high",
        signature_id="hubspot:strict_js", matched_text="x",
    )]
    _findings, gaps, _q = tech_stack._emit_findings(
        detected, "example.com", "https://example.com", _now(),
    )
    gap_text = " ".join(gaps).lower()
    assert "analytics" in gap_text or "tag manager" in gap_text
```

- [ ] **Step 3: Run test to verify it fails**

```bash
uv run pytest tests/test_tech_stack.py -v
```

Expected: 5 new tests fail (`AttributeError: module 'rrxray.collectors.tech_stack' has no attribute '_emit_findings'`).

- [ ] **Step 4: Implement `_emit_findings` in `rrxray/collectors/tech_stack.py`**

Append to the end of the file:

```python
from datetime import datetime  # noqa: E402

from rrxray.schemas._shared import Finding, SourceCitation  # noqa: E402


def _emit_findings(
    detected: list[DetectedTool],
    domain: str,
    scrape_url: str,
    now: datetime,
) -> tuple[list[Finding], list[str], list[str]]:
    """Rule-based findings/gaps/questions. No LLM."""
    findings: list[Finding] = []
    gaps: list[str] = []
    questions: list[str] = []

    if not detected:
        findings.append(Finding(
            text="No analytics, marketing, or CRM tags detected on the homepage.",
            source=SourceCitation(url=scrape_url, timestamp=now),
        ))
        questions.append(
            "We did not detect any common marketing or analytics tooling on your homepage. "
            "Is that a deliberate posture (e.g., privacy-led), or are tags loaded server-side "
            "or via a tag manager we did not match?"
        )
        return findings, gaps, questions

    categories = {t.category for t in detected}
    absent = [c for c in CATEGORIES if c not in categories]

    has_marketing = "marketing_automation" in categories
    has_crm = "crm" in categories
    has_product_analytics = "product_analytics" in categories
    has_chat = "chat" in categories

    if has_marketing and not has_crm:
        findings.append(Finding(
            text=(
                "Marketing automation present; no CRM signature detected on the homepage. "
                "CRM may be detected via other surfaces."
            ),
            source=SourceCitation(url=scrape_url, timestamp=now),
        ))

    if has_product_analytics:
        questions.append(
            "Product analytics tooling indicates an in-product activation focus. "
            "What are your activation and time-to-value benchmarks today?"
        )

    if has_chat and not has_marketing:
        gaps.append(
            "Live chat tooling is present but no marketing automation was detected. "
            "Inbound conversations may not be feeding a nurture sequence."
        )

    if "analytics" in absent and "tag_manager" in absent:
        gaps.append(
            "Neither web analytics nor a tag manager was detected. "
            "Site engagement data may be sparse."
        )
    if "marketing_automation" in absent and detected:
        gaps.append(
            "No marketing automation tooling was detected; "
            "lead nurture may rely on manual outreach."
        )
    if "product_analytics" in absent and detected:
        gaps.append(
            "No product analytics was detected; activation and feature adoption "
            "signals are likely informal."
        )

    return findings, gaps, questions
```

- [ ] **Step 5: Run test to verify it passes**

```bash
uv run pytest tests/test_tech_stack.py -v
```

Expected: All 12 tests pass (7 from T4 + 5 new).

- [ ] **Step 6: Run ruff**

```bash
uv run ruff check rrxray/ tests/
```

Expected: All checks passed.

- [ ] **Step 7: Commit**

```bash
git add rrxray/collectors/tech_stack.py tests/test_tech_stack.py tests/fixtures/synthetic/tech_stack/chat_without_map.html
git commit -m "Add tech_stack rule-based findings emission"
```

---

## Task 6: Evidence writing + collect() orchestration

**Files:**
- Modify: `rrxray/collectors/tech_stack.py` (add `_write_evidence`, `collect`, top-of-file imports)
- Modify: `tests/test_tech_stack.py` (append integration tests)

- [ ] **Step 1: Append failing tests**

Append to `tests/test_tech_stack.py`:

```python
import asyncio
from unittest.mock import AsyncMock, MagicMock


def _make_ctx(tmp_path, scrape_response=None, scrape_error=None):
    """Build a CollectorContext with a mocked Firecrawl client."""
    from rrxray.context import CollectorContext

    fc = MagicMock()

    if scrape_error is not None:
        async def fake_scrape(url, only_main_content=True):
            raise scrape_error
        fc.scrape_url = AsyncMock(side_effect=fake_scrape)
    else:
        response = scrape_response or {
            "url": "https://example.com",
            "html": "",
            "markdown": "",
            "metadata": {},
        }
        fc.scrape_url = AsyncMock(return_value=MagicMock(**response))

    wb = MagicMock()
    config = MagicMock()
    return CollectorContext(
        domain="example.com",
        company_name=None,
        firecrawl=fc,
        wayback=wb,
        evidence_dir=tmp_path / "evidence",
        config=config,
    )


def test_collector_name_constant():
    assert tech_stack.NAME == "tech_stack"


def test_collect_writes_evidence_files(tmp_path):
    html = _load("multi_tool.html")
    ctx = _make_ctx(tmp_path, scrape_response={
        "url": "https://example.com",
        "html": html,
        "markdown": "",
        "metadata": {"sourceURL": "https://example.com"},
    })
    asyncio.run(tech_stack.collect(ctx))
    evidence = tmp_path / "evidence" / "tech_stack"
    assert (evidence / "homepage.html").exists()
    assert (evidence / "detections.json").exists()
    saved_html = (evidence / "homepage.html").read_text()
    assert saved_html == html


def test_collect_only_main_content_false(tmp_path):
    """Collector must request full HTML (not main-content-only) so <head> tags are visible."""
    ctx = _make_ctx(tmp_path, scrape_response={
        "url": "https://example.com",
        "html": "<html></html>",
        "markdown": "",
        "metadata": {"sourceURL": "https://example.com"},
    })
    asyncio.run(tech_stack.collect(ctx))
    _args, kwargs = ctx.firecrawl.scrape_url.call_args
    assert kwargs.get("only_main_content") is False


def test_collect_returns_techstackdata(tmp_path):
    from rrxray.schemas.tech_stack import TechStackData

    html = _load("multi_tool.html")
    ctx = _make_ctx(tmp_path, scrape_response={
        "url": "https://example.com",
        "html": html,
        "markdown": "",
        "metadata": {"sourceURL": "https://example.com"},
    })
    result = asyncio.run(tech_stack.collect(ctx))
    assert isinstance(result, TechStackData)
    assert len(result.detected_tools) >= 4
    names = {t.name for t in result.detected_tools}
    assert "HubSpot" in names


def test_collect_populates_categories_observed_and_absent(tmp_path):
    html = _load("multi_tool.html")
    ctx = _make_ctx(tmp_path, scrape_response={
        "url": "https://example.com",
        "html": html,
        "markdown": "",
        "metadata": {"sourceURL": "https://example.com"},
    })
    result = asyncio.run(tech_stack.collect(ctx))
    assert "marketing_automation" in result.categories_observed
    assert "product_analytics" in result.categories_observed
    assert "marketing_automation" not in result.categories_absent
    assert len(result.categories_observed) + len(result.categories_absent) == 9


def test_source_citation_path_relative_to_evidence_dir(tmp_path):
    """SourceCitation.evidence_path must NOT start with 'evidence/' to avoid template double-prefix."""
    html = _load("multi_tool.html")
    ctx = _make_ctx(tmp_path, scrape_response={
        "url": "https://example.com",
        "html": html,
        "markdown": "",
        "metadata": {"sourceURL": "https://example.com"},
    })
    result = asyncio.run(tech_stack.collect(ctx))
    for source in result.sources:
        if source.evidence_path:
            assert not source.evidence_path.startswith("evidence/")
            assert source.evidence_path.startswith("tech_stack/")


def test_collect_handles_firecrawl_error_gracefully(tmp_path):
    """A FirecrawlError must produce a graceful TechStackData with a single fetch-failure finding."""
    from rrxray.services.firecrawl_client import FirecrawlError

    ctx = _make_ctx(tmp_path, scrape_error=FirecrawlError("boom"))
    result = asyncio.run(tech_stack.collect(ctx))
    assert result.detected_tools == []
    assert len(result.findings) == 1
    assert "homepage" in result.findings[0].text.lower()


def test_collect_no_detections_returns_findings_about_emptiness(tmp_path):
    html = _load("empty.html")
    ctx = _make_ctx(tmp_path, scrape_response={
        "url": "https://example.com",
        "html": html,
        "markdown": "",
        "metadata": {"sourceURL": "https://example.com"},
    })
    result = asyncio.run(tech_stack.collect(ctx))
    assert result.detected_tools == []
    assert len(result.findings) == 1
    assert "no analytics" in result.findings[0].text.lower() or "no tags" in result.findings[0].text.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_tech_stack.py -v
```

Expected: 8 new tests fail (collect / NAME do not yet exist on the module).

- [ ] **Step 3: Implement evidence writing and `collect()` in `rrxray/collectors/tech_stack.py`**

Append to the end of the file:

```python
import json  # noqa: E402
from datetime import UTC  # noqa: E402
from pathlib import Path  # noqa: E402

from rrxray.context import CollectorContext  # noqa: E402
from rrxray.schemas.tech_stack import TechStackData  # noqa: E402
from rrxray.services.firecrawl_client import FirecrawlError  # noqa: E402


def _write_evidence(
    evidence_dir: Path,
    html: str,
    detected: list[DetectedTool],
) -> None:
    """Write the raw scraped HTML and the parsed detection set to the evidence dir."""
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / "homepage.html").write_text(html, encoding="utf-8")
    (evidence_dir / "detections.json").write_text(
        json.dumps([t.model_dump() for t in detected], indent=2),
        encoding="utf-8",
    )


async def collect(ctx: CollectorContext) -> TechStackData:
    """Scrape the homepage; run all signatures; emit DetectedTool list and findings."""
    now = datetime.now(UTC)
    homepage_url = f"https://{ctx.domain}"

    try:
        page = await ctx.firecrawl.scrape_url(homepage_url, only_main_content=False)
    except FirecrawlError as e:
        log.warning("homepage scrape failed for %s: %s", homepage_url, e)
        return TechStackData(
            findings=[Finding(
                text=f"Could not fetch homepage at {homepage_url} for tech stack detection: {e}",
                source=SourceCitation(url=homepage_url, timestamp=now),
            )],
        )

    html = page.html or ""
    detected = _detect(html)
    categories_observed = sorted({t.category for t in detected})
    categories_absent = [c for c in CATEGORIES if c not in categories_observed]

    findings, gaps, questions = _emit_findings(detected, ctx.domain, homepage_url, now)

    _write_evidence(ctx.evidence_dir / NAME, html, detected)

    sources = [SourceCitation(
        url=homepage_url,
        timestamp=now,
        evidence_path=str(
            (ctx.evidence_dir / NAME / "homepage.html").relative_to(ctx.evidence_dir)
        ),
    )]

    return TechStackData(
        detected_tools=detected,
        categories_observed=categories_observed,
        categories_absent=categories_absent,
        findings=findings,
        gaps=gaps,
        discovery_questions=questions,
        sources=sources,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_tech_stack.py -v
```

Expected: 20 tests pass (12 from T4-T5 + 8 new).

- [ ] **Step 5: Run ruff**

```bash
uv run ruff check rrxray/ tests/
```

Expected: All checks passed. If any imports are flagged for ordering, run `uv run ruff check --fix rrxray/ tests/` and verify tests still pass.

- [ ] **Step 6: Commit**

```bash
git add rrxray/collectors/tech_stack.py tests/test_tech_stack.py
git commit -m "Wire tech_stack collect() with evidence writing + graceful error handling"
```

---

## Task 7: Renderer template + integration

**Files:**
- Create: `templates/_tech_stack_detail.md.jinja`
- Modify: `templates/report_internal.md.jinja` (include the new partial in Module Detail Appendix)
- Modify: `tests/test_render_internal.py` (append render tests)

- [ ] **Step 1: Append failing tests to `tests/test_render_internal.py`**

```python
def test_tech_stack_module_detail_renders_with_detections():
    """When tech_stack has detected_tools, the Tech Stack subsection renders the table."""
    from rrxray.schemas.tech_stack import DetectedTool, TechStackData

    tech = TechStackData(
        detected_tools=[
            DetectedTool(
                name="HubSpot", category="marketing_automation", confidence="high",
                signature_id="hubspot:strict_js", matched_text="js.hs-scripts.com/x.js",
            ),
            DetectedTool(
                name="Pendo", category="product_analytics", confidence="high",
                signature_id="pendo:strict_agent", matched_text="cdn.pendo.io",
            ),
        ],
        categories_observed=["marketing_automation", "product_analytics"],
        categories_absent=["analytics", "tag_manager", "chat", "crm", "cdp", "ab_testing", "attribution"],
    )
    data = make_data()
    data.collectors.tech_stack = tech
    out = render_internal(data, Anonymizer(), VoicePostProcessor())
    assert "### Tech Stack" in out
    assert "HubSpot" in out
    assert "Pendo" in out
    assert "marketing_automation" in out


def test_tech_stack_module_detail_omits_when_no_collector():
    """When tech_stack collector did not run, the Tech Stack subsection is absent."""
    data = make_data()
    out = render_internal(data, Anonymizer(), VoicePostProcessor())
    assert "### Tech Stack" not in out


def test_tech_stack_module_detail_renders_categories_lists():
    """categories_observed and categories_absent show up in render."""
    from rrxray.schemas.tech_stack import DetectedTool, TechStackData

    tech = TechStackData(
        detected_tools=[DetectedTool(
            name="HubSpot", category="marketing_automation", confidence="high",
            signature_id="hubspot:strict_js", matched_text="x",
        )],
        categories_observed=["marketing_automation"],
        categories_absent=["analytics", "crm"],
    )
    data = make_data()
    data.collectors.tech_stack = tech
    out = render_internal(data, Anonymizer(), VoicePostProcessor())
    assert "marketing_automation" in out
    assert "analytics" in out  # in absent list
    assert "crm" in out  # in absent list


def test_tech_stack_renders_findings_with_voice_collector_filter():
    """Findings text passes through voice_collector filter."""
    from rrxray.schemas._shared import Finding, SourceCitation
    from rrxray.schemas.tech_stack import DetectedTool, TechStackData

    tech = TechStackData(
        detected_tools=[DetectedTool(
            name="HubSpot", category="marketing_automation", confidence="high",
            signature_id="hubspot:strict_js", matched_text="x",
        )],
        findings=[Finding(
            text="We leverage marketing automation for nurture.",  # forbidden word
            source=SourceCitation(
                url="https://example.com",
                timestamp=datetime(2026, 5, 7, 12, 0, tzinfo=timezone.utc),
            ),
        )],
    )
    data = make_data()
    data.collectors.tech_stack = tech
    out = render_internal(data, Anonymizer(), VoicePostProcessor())
    # Voice substitution: "leverage" becomes "use" in the body before Voice Adjustments
    body = out.split("### Voice Adjustments")[0]
    assert "leverage" not in body
    assert "use marketing automation" in body or "use" in body
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_render_internal.py -v -k tech_stack
```

Expected: 4 new tests fail (template doesn't include Tech Stack section yet).

- [ ] **Step 3: Create `templates/_tech_stack_detail.md.jinja`**

```jinja
{% set t = data.collectors.tech_stack %}
{% if t.detected_tools %}
**Detected tooling ({{ t.detected_tools | length }}):**

| Category | Tool | Confidence | Signature |
|---|---|---|---|
{% for tool in t.detected_tools %}
| {{ tool.category }} | {{ tool.name }} | {{ tool.confidence }} | `{{ tool.signature_id }}` |
{% endfor %}

**Categories observed:** {{ t.categories_observed | join(", ") }}
**Categories not detected:** {{ t.categories_absent | join(", ") }}
{% else %}
No analytics, marketing, or CRM tooling detected on the homepage.
{% endif %}

{% if t.findings %}
**Findings:**

{% for f in t.findings %}
- {{ f.text | voice_collector }} *(source: [{{ f.source.url }}]({{ f.source.url }}))*
{% endfor %}
{% endif %}

{% if t.gaps %}
**Gaps:**
{% for g in t.gaps %}
→ {{ g | voice_collector }}
{% endfor %}
{% endif %}

{% if t.discovery_questions %}
**Discovery questions:**
{% for q in t.discovery_questions %}
- {{ q }}
{% endfor %}
{% endif %}
```

- [ ] **Step 4: Modify `templates/report_internal.md.jinja` to include the partial**

Find the Module Detail Appendix section (where the pricing partial is included). It currently looks like:

```jinja
{% if data.collectors.pricing_packaging %}
### Pricing & Packaging

{% include "_pricing_detail.md.jinja" %}
{% endif %}
```

Add the new tech_stack include immediately AFTER the pricing block, BEFORE the closing of the Module Detail Appendix section:

```jinja
{% if data.collectors.tech_stack %}
### Tech Stack

{% include "_tech_stack_detail.md.jinja" %}
{% endif %}
```

The full Module Detail Appendix section should now include both pricing and tech_stack conditional blocks, in that order.

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/test_render_internal.py -v
```

Expected: All render tests pass (existing + 4 new).

- [ ] **Step 6: Run ruff**

```bash
uv run ruff check rrxray/ tests/
```

Expected: All checks passed.

- [ ] **Step 7: Commit**

```bash
git add templates/_tech_stack_detail.md.jinja templates/report_internal.md.jinja tests/test_render_internal.py
git commit -m "Add tech_stack Module Detail partial and render tests"
```

---

## Task 8: Pipeline registration + smoke

**Files:**
- Modify: `rrxray/pipeline.py` (append `tech_stack` to `COLLECTORS`)
- Modify: `tests/test_pipeline_graceful_degradation.py` (append integration test)

- [ ] **Step 1: Append failing test to `tests/test_pipeline_graceful_degradation.py`**

```python
def test_tech_stack_collector_registered_in_pipeline():
    """tech_stack module must be in COLLECTORS so the orchestrator runs it."""
    from rrxray import pipeline
    from rrxray.collectors import tech_stack

    assert tech_stack in pipeline.COLLECTORS


def test_pipeline_includes_tech_stack_in_data_json(tmp_path, monkeypatch):
    """End-to-end: a tech_stack stub returns TechStackData; pipeline puts it on CollectorOutputs."""
    from rrxray.schemas.tech_stack import DetectedTool, TechStackData
    from rrxray import pipeline

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
        )

    fake_tech_stack.collect = tech_collect

    fake_synth = MagicMock()
    fake_synth.NAME = "observed_gtm_motion"
    fake_synth.synthesize = AsyncMock(return_value=None)

    monkeypatch.setattr(pipeline, "COLLECTORS", [fake_pricing, fake_tech_stack])
    monkeypatch.setattr(pipeline, "SYNTHESIZERS", [fake_synth])
    monkeypatch.setattr(pipeline, "build_collector_context", lambda c: MagicMock())
    monkeypatch.setattr(
        pipeline, "build_synthesizer_context",
        lambda c, o, v, a: MagicMock(collector_outputs=o, voice=v, anonymizer=a, config=c),
    )

    data, markdown = asyncio.run(pipeline.run_pipeline(config))
    assert data.collectors.tech_stack is not None
    assert data.collectors.tech_stack.detected_tools[0].name == "HubSpot"
    assert "### Tech Stack" in markdown
    assert "HubSpot" in markdown
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_pipeline_graceful_degradation.py -v -k tech_stack
```

Expected: 2 tests fail (`tech_stack` not in `COLLECTORS`).

- [ ] **Step 3: Modify `rrxray/pipeline.py`**

Locate the existing import and the `COLLECTORS` list. They look like:

```python
from rrxray.collectors import pricing_packaging
from rrxray.synthesizers import observed_gtm_motion_pricing

COLLECTORS = [pricing_packaging]
SYNTHESIZERS = [observed_gtm_motion_pricing]
```

Update both to include `tech_stack`:

```python
from rrxray.collectors import pricing_packaging, tech_stack
from rrxray.synthesizers import observed_gtm_motion_pricing

COLLECTORS = [pricing_packaging, tech_stack]
SYNTHESIZERS = [observed_gtm_motion_pricing]
```

That's the only change in this file.

- [ ] **Step 4: Run the full test suite**

```bash
uv run pytest -v 2>&1 | tail -10
```

Expected: All tests pass (~140+ tests; new count is roughly 30 more than Phase 1's 122).

- [ ] **Step 5: Run ruff**

```bash
uv run ruff check rrxray/ tests/
```

Expected: All checks passed.

- [ ] **Step 6: Manual smoke test (no commit needed for this step)**

Verify the pipeline runs end-to-end against a real domain:

```bash
unset ANTHROPIC_API_KEY  # if your shell has an empty one shadowing .env
unset FIRECRAWL_API_KEY
uv run rrxray run --domain swayable.com 2>&1 | tail -10
```

Open the rendered report:

```bash
cat /Users/dalezwizinski/Documents/Apps/rrxray/xray-swayable-com-*/report.internal.md
```

Expected: a `### Tech Stack` subsection appears in the Module Detail Appendix with at least one detected tool. The Section A narrative still reads pricing-only (synthesizer wasn't upgraded in this cycle, by design).

- [ ] **Step 7: Commit**

```bash
git add rrxray/pipeline.py tests/test_pipeline_graceful_degradation.py
git commit -m "Register tech_stack in pipeline COLLECTORS list"
```

---

## Self-Review

Run after the plan is complete to catch placeholders, contradictions, and gaps before execution begins.

### Spec coverage check

| Spec section | Plan task |
|---|---|
| File layout | T1-T8 (every task creates the right files) |
| Catalog (`_tech_stack_catalog.py`) with ~40 entries | T3 |
| `Category` Literal of 9 categories | T1 |
| `DetectedTool` schema with confidence + signature_id + matched_text | T1 |
| `TechStackData` schema with detected_tools + categories + findings | T1 |
| `tech_stack` field on `CollectorOutputs` | T2 |
| `_compile_signatures` at module load | T4 |
| `_detect` with strict-overrides-loose semantics | T4 |
| `_emit_findings` rule-based logic | T5 |
| `_write_evidence` writing homepage.html + detections.json | T6 |
| `collect()` orchestrator with FirecrawlError handling | T6 |
| `only_main_content=False` for the homepage scrape | T6 |
| Source citation paths relative to evidence_dir (Phase 1 fix preserved) | T6 |
| Renderer partial `_tech_stack_detail.md.jinja` | T7 |
| Module Detail Appendix include in main template | T7 |
| Voice and anonymizer filters apply to tech_stack output | T7 (voice via partial) |
| `pipeline.COLLECTORS` includes `tech_stack` | T8 |
| Synthetic HTML fixtures (~5 files) | T4-T5 |

### Acceptance criteria coverage

| AC | Plan task |
|---|---|
| #1 Collector exists and is registered | T1, T8 |
| #2 Catalog has ≥30 entries spanning all 9 categories | T3 |
| #3 Every regex compiles | T3 |
| #4 Strict overrides loose | T4 |
| #5 Empty HTML emits graceful finding | T5, T6 |
| #6 FirecrawlError handled gracefully | T6 |
| #7 Evidence files + correct relative paths | T6 |
| #8 data.json round-trips with tech_stack populated | T2 |
| #9 Module Detail Appendix renders Tech Stack subsection | T7 |
| #10 Live run smoke (manual) | T8 step 6 |

### Type / signature consistency check

- `DetectedTool` fields (name, category, confidence, signature_id, matched_text): defined T1, used T4-T7
- `TechStackData` fields: defined T1, used T6-T7
- `Category` Literal: defined T1, used T1, T4, T6
- `_detect(html: str) -> list[DetectedTool]`: defined T4, used T6
- `_emit_findings(detected, domain, scrape_url, now) -> tuple[list[Finding], list[str], list[str]]`: defined T5, used T6
- `_write_evidence(evidence_dir: Path, html: str, detected: list[DetectedTool]) -> None`: defined T6
- `collect(ctx: CollectorContext) -> TechStackData`: defined T6, used T8
- `NAME = "tech_stack"`: defined T4, used T6, T8
- `CATEGORIES` list: defined T3, used T1 (via Literal), T6
- `SIGNATURES` list: defined T3, used T4

### Placeholder scan

Searched for: TBD, TODO, "implement later", "fill in", "add appropriate", "similar to". None found in the plan body.

---

## Execution Handoff

Plan complete and saved to [docs/superpowers/plans/2026-05-07-rrxray-phase-2.1a-tech-stack.md](docs/superpowers/plans/2026-05-07-rrxray-phase-2.1a-tech-stack.md). Two execution options:

**1. Subagent-Driven (recommended)** — same approach as Phase 1. Fresh subagent per task, two-stage review (spec compliance + code quality) between tasks. Best for this plan because the 8 tasks are well-isolated and TDD discipline catches drift early.

**2. Inline Execution** — `superpowers:executing-plans` with batch execution and review checkpoints. Best if you want to see each diff in real time.

Which approach?
