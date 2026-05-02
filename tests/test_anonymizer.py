"""Anonymizer: name registry + role-descriptor replacement + press-release whitelist."""
import pytest

from rrxray.voice.anonymizer import AnonymityViolationError, Anonymizer


def test_unwhitelisted_name_replaced_with_role_descriptor():
    a = Anonymizer()
    a.register_individual("Sarah Chen", "the current VP of Sales")
    out = a.anonymize("Sarah Chen leads sales.")
    assert "Sarah Chen" not in out
    assert out == "the current VP of Sales leads sales."


def test_whitelisted_name_preserved():
    a = Anonymizer()
    a.register_individual("Sarah Chen", "the current VP of Sales")
    a.whitelist_from_press("Sarah Chen")
    out = a.anonymize("Sarah Chen leads sales.")
    assert out == "Sarah Chen leads sales."


def test_longest_name_wins_in_overlap():
    a = Anonymizer()
    a.register_individual("Sarah", "the analyst")
    a.register_individual("Sarah Chen", "the current VP of Sales")
    out = a.anonymize("Sarah Chen leads sales.")
    assert out == "the current VP of Sales leads sales."


def test_multiple_names_replaced():
    a = Anonymizer()
    a.register_individual("Sarah Chen", "the VP of Sales")
    a.register_individual("Mike Lee", "the CTO")
    out = a.anonymize("Sarah Chen and Mike Lee met.")
    assert "Sarah Chen" not in out
    assert "Mike Lee" not in out
    assert out == "the VP of Sales and the CTO met."


def test_unregistered_name_passes_through():
    a = Anonymizer()
    out = a.anonymize("John Doe leads sales.")
    assert out == "John Doe leads sales."


def test_assert_no_unanonymized_raises_on_registered_name():
    a = Anonymizer()
    a.register_individual("Sarah Chen", "the VP")
    with pytest.raises(AnonymityViolationError) as exc:
        a.assert_no_unanonymized("Sarah Chen leads sales.")
    assert "Sarah Chen" in str(exc.value)


def test_assert_no_unanonymized_passes_on_whitelisted():
    a = Anonymizer()
    a.register_individual("Sarah Chen", "the VP")
    a.whitelist_from_press("Sarah Chen")
    a.assert_no_unanonymized("Sarah Chen leads sales.")


def test_assert_no_unanonymized_passes_on_clean_text():
    a = Anonymizer()
    a.register_individual("Sarah Chen", "the VP")
    a.assert_no_unanonymized("the VP leads sales.")
