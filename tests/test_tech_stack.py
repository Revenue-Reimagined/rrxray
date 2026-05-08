"""tech_stack collector tests."""
import asyncio
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

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


def _now():
    return datetime(2026, 5, 7, 12, 0, tzinfo=UTC)


def test_no_detections_emits_finding():
    detected = []
    findings, _gaps, questions = tech_stack._emit_findings(
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


def test_detect_hubspot_dom_only_returns_low_confidence():
    """When HubSpot script is stripped but DOM markers survive, low-confidence detection fires."""
    html = _load("hubspot_dom_only.html")
    detected = tech_stack._detect(html)
    hubspot = [t for t in detected if t.name == "HubSpot"]
    assert len(hubspot) == 1
    assert hubspot[0].confidence == "low"
    # Signature ID should be one of the DOM-level ones, not the script-URL ones
    assert hubspot[0].signature_id.startswith("hubspot:loose_dom_")


def test_detect_gtm_noscript_iframe():
    """GTM's noscript fallback iframe is a reliable detection target."""
    html = _load("gtm_noscript.html")
    detected = tech_stack._detect(html)
    gtm = [t for t in detected if t.name == "Google Tag Manager"]
    assert len(gtm) == 1
    # Loose detection by ID — the noscript signature is loose-tier
    assert gtm[0].signature_id == "gtm:loose_noscript_iframe"


def test_detect_intercom_dom_only():
    """Intercom DOM mount points trigger low-confidence detection."""
    html = _load("intercom_dom_only.html")
    detected = tech_stack._detect(html)
    intercom = [t for t in detected if t.name == "Intercom"]
    assert len(intercom) == 1
    assert intercom[0].confidence == "low"


def test_strict_url_overrides_dom_loose():
    """When both the script-URL strict signature AND the DOM loose signature match,
    the strict (high-confidence) one wins per the existing dedupe rule."""
    html = """
    <html lang="en-US" data-hubspot-theme="canvas-light">
    <head>
    <script src="https://js.hs-scripts.com/12345.js"></script>
    </head>
    <body>
    <div id="hs-web-interactives-top-push-anchor"></div>
    </body></html>
    """
    detected = tech_stack._detect(html)
    hubspot = [t for t in detected if t.name == "HubSpot"]
    assert len(hubspot) == 1
    assert hubspot[0].confidence == "high"
    assert hubspot[0].signature_id == "hubspot:strict_js"
