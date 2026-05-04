"""Verify the synthesizer system prompt contains the universal rules."""
from importlib.resources import files


def test_synthesizer_system_prompt_present():
    text = files("rrxray.prompts").joinpath("synthesizer_system.md").read_text()
    assert "Verbatim Quarantine" in text
    assert "Individual Anonymity" in text
    assert "Brand Voice" in text
    assert "GTM Gap" in text
    assert "rr-brand-voice" in text  # pointer back to source-of-truth


def test_synthesizer_system_prompt_forbidden_words_listed():
    text = files("rrxray.prompts").joinpath("synthesizer_system.md").read_text()
    for word in ["leverage", "synergies", "holistic", "streamline", "impactful"]:
        assert word in text.lower()


def test_observed_gtm_motion_pricing_template_exists():
    text = files("rrxray.prompts").joinpath("observed_gtm_motion_pricing.md").read_text()
    assert "{{" in text  # Jinja template
    assert "pricing" in text.lower()
