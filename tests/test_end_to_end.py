"""End-to-end smoke: full pipeline run with cache-as-fixture (replay-only).

Bootstrap procedure (run once, requires API keys + network):

    export ANTHROPIC_API_KEY=...
    export FIRECRAWL_API_KEY=...
    RRXRAY_FIXTURE_BOOTSTRAP=1 uv run pytest tests/test_end_to_end.py -v -s

This populates `tests/fixtures/cache/{firecrawl,anthropic,wayback}/`. After bootstrap,
commit the cache files. Subsequent runs (the default) use replay-only mode and are
fully offline.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path

import pytest

from rrxray.config import Config
from rrxray.pipeline import run_pipeline
from rrxray.schemas.data import XrayData

SMOKE_DOMAIN = "stripe.com"  # public B2B SaaS with stable pricing page


def _bootstrap_mode() -> bool:
    return os.environ.get("RRXRAY_FIXTURE_BOOTSTRAP") == "1"


@pytest.mark.skipif(
    not _bootstrap_mode()
    and not list(
        (Path(__file__).parent / "fixtures" / "cache" / "firecrawl").glob("*.json")
    ),
    reason="Fixtures not bootstrapped; set RRXRAY_FIXTURE_BOOTSTRAP=1 to populate.",
)
def test_full_pipeline_against_smoke_domain(tmp_path):
    fixture_cache = Path(__file__).parent / "fixtures" / "cache"
    fixture_cache.mkdir(parents=True, exist_ok=True)
    (fixture_cache / "firecrawl").mkdir(exist_ok=True)
    (fixture_cache / "anthropic").mkdir(exist_ok=True)
    (fixture_cache / "wayback").mkdir(exist_ok=True)

    config = Config(
        domain=SMOKE_DOMAIN,
        output_dir=tmp_path / "out",
        cache_dir=fixture_cache,
        use_cache=True,
    )

    # In bootstrap mode, the cache layer runs `live` and writes new fixtures.
    # In replay mode, missing cache entries raise CacheMissError.
    # The Config currently passes use_cache=True which maps to "live" mode in pipeline.build_*.
    # For replay-only, we need to override pipeline to use replay-only when not bootstrapping.
    if not _bootstrap_mode():
        import rrxray.services.cache as cache_module

        original_init = cache_module.DiskCache.__init__

        def patched_init(self, dir, mode="live"):
            if Path(dir).is_relative_to(fixture_cache):
                mode = "replay-only"
            original_init(self, dir, mode=mode)

        cache_module.DiskCache.__init__ = patched_init
        try:
            data, rendered = asyncio.run(run_pipeline(config))
        finally:
            cache_module.DiskCache.__init__ = original_init
    else:
        data, rendered = asyncio.run(run_pipeline(config))

    # AC #1: produces data.json + report
    assert isinstance(data, XrayData)
    assert data.domain == SMOKE_DOMAIN

    # AC #2: data.json validates
    serialized = data.model_dump_json()
    XrayData.model_validate(json.loads(serialized))

    # AC #5: full skeleton present
    for header in [
        "## 1. Executive Summary",
        "## 2. Section A: Observed GTM Motion",
        "## 3. Section B: Stability and Trajectory Signals",
        "## 4. Section C: External Voice vs. Internal Voice",
        "## 5. Module Detail Appendix",
        "## 6. Discovery Questions",
        "## 7. Sources & Methodology",
    ]:
        assert header in rendered, f"missing header: {header}"

    # AC #3: every finding has source URL + timestamp
    for source in data.sources:
        assert source.url
        assert source.timestamp

    # AC #4: voice post-processor ran (no em dashes or forbidden words in output)
    forbidden = ["leverage", "synergies", "holistic", "streamline", "impactful"]
    for word in forbidden:
        # case-insensitive: word must not appear as a standalone term in the rendered body
        # (we allow it inside the Voice Adjustments table where it documents substitutions)
        body = rendered.split("### Voice Adjustments")[0]
        assert not re.search(
            rf"\b{word}\w*\b", body, re.IGNORECASE
        ), f"forbidden word {word!r} appeared in rendered body"
    assert "—" not in rendered.split("### Voice Adjustments")[0]
