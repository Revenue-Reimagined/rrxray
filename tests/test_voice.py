"""Voice post-processor: tiered substitute/raise behavior."""
import pytest

from rrxray.voice.rr_voice import VoicePostProcessor, VoiceViolationError


def test_em_dash_substituted_in_collector_text():
    v = VoicePostProcessor()
    out = v.process_collector_text("This is fine — really fine.", "test")
    assert "—" not in out
    assert "fine; really" in out or "fine: really" in out


def test_em_dash_raises_in_synthesizer_text():
    v = VoicePostProcessor()
    with pytest.raises(VoiceViolationError):
        v.process_synthesizer_text("This is fine — really fine.", "test")


def test_forbidden_word_substituted_in_collector_text():
    v = VoicePostProcessor()
    cases = {
        "We leverage data": "We use data",
        "Leveraging the API": "Using the API",
        "Synergies between teams": "Overlap between teams",
        "Holistic approach": "End-to-end approach",
        "Streamline operations": "Simplify operations",
        "Streamlined process": "Simplified process",
        "Impactful results": "Meaningful results",
    }
    for inp, expected in cases.items():
        out = v.process_collector_text(inp, "test")
        assert out == expected, f"{inp!r} -> {out!r}, expected {expected!r}"


def test_forbidden_word_raises_in_synthesizer_text():
    v = VoicePostProcessor()
    with pytest.raises(VoiceViolationError):
        v.process_synthesizer_text("We leverage data", "test")


def test_trademark_inserted_on_first_gtm_gap_mention():
    v = VoicePostProcessor()
    out = v.process_collector_text("The GTM Gap is wide.", "test")
    assert "GTM Gap™" in out


def test_trademark_not_doubled_when_already_present():
    v = VoicePostProcessor()
    out = v.process_collector_text("The GTM Gap™ is wide.", "test")
    assert out.count("™") == 1


def test_log_records_substitutions():
    v = VoicePostProcessor()
    v.process_collector_text("We leverage holistic synergies.", "Section A para 0")
    events = v.peek_log()
    assert len(events) >= 3
    rules = {e.rule for e in events}
    assert "forbidden_word" in rules


def test_peek_log_does_not_clear():
    v = VoicePostProcessor()
    v.process_collector_text("We leverage data.", "ctx")
    assert len(v.peek_log()) == 1
    assert len(v.peek_log()) == 1


def test_flush_log_clears():
    v = VoicePostProcessor()
    v.process_collector_text("We leverage data.", "ctx")
    events = v.flush_log()
    assert len(events) == 1
    assert v.flush_log() == []


def test_synthesizer_violation_recorded_before_raise():
    v = VoicePostProcessor()
    with pytest.raises(VoiceViolationError):
        v.process_synthesizer_text("We leverage data.", "synth ctx")
    events = v.peek_log()
    assert any(e.action == "raise" for e in events)


def test_clean_text_passes_unchanged():
    v = VoicePostProcessor()
    text = "The current revenue leader has been in seat 11 months."
    assert v.process_collector_text(text, "ctx") == text
    assert v.process_synthesizer_text(text, "ctx") == text


def test_capitalization_preserved_in_substitution():
    v = VoicePostProcessor()
    assert v.process_collector_text("Leverage this", "ctx") == "Use this"
    assert v.process_collector_text("LEVERAGE this", "ctx") == "USE this"


def test_em_dash_substitution_picks_colon_before_capital():
    v = VoicePostProcessor()
    out = v.process_collector_text("Two parts — First and second.", "ctx")
    assert ": First" in out
    out2 = v.process_collector_text("two parts — first and second", "ctx")
    assert "; first" in out2
