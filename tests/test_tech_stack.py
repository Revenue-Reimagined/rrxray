"""tech_stack collector tests."""
from pathlib import Path

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
