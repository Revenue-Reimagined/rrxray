"""Tiered voice post-processor: substitute for collector text, raise for synthesizer text."""
from __future__ import annotations

import re
from typing import Literal

from rrxray.schemas.data import VoiceEvent

SUBSTITUTIONS = {
    "leverage": "use",
    "leveraging": "using",
    "leveraged": "used",
    "leverages": "uses",
    "synergies": "overlap",
    "synergy": "overlap",
    "holistic": "end-to-end",
    "streamline": "simplify",
    "streamlined": "simplified",
    "streamlining": "simplifying",
    "streamlines": "simplifies",
    "impactful": "meaningful",
}

# Longest first so "leveraging" matches before "leverage"
_FORBIDDEN_RE = re.compile(
    r"\b(" + "|".join(sorted(SUBSTITUTIONS.keys(), key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)
_EM_DASH_RE = re.compile(r"\s*—\s*")
_GTM_GAP_RE = re.compile(r"\bGTM Gap\b(?!™)")


class VoiceViolationError(Exception):
    def __init__(self, rule: str, original: str, context: str):
        self.rule = rule
        self.original = original
        self.context = context
        super().__init__(f"Voice violation [{rule}] in {context}: {original!r}")


def _match_case(replacement: str, original: str) -> str:
    if original.isupper():
        return replacement.upper()
    if original[0].isupper():
        return replacement[0].upper() + replacement[1:]
    return replacement


class VoicePostProcessor:
    def __init__(self) -> None:
        self._log: list[VoiceEvent] = []

    def process_collector_text(self, text: str, context: str) -> str:
        return self._apply(text, context, on_violation="substitute")

    def process_synthesizer_text(self, text: str, context: str) -> str:
        return self._apply(text, context, on_violation="raise")

    def peek_log(self) -> list[VoiceEvent]:
        return list(self._log)

    def flush_log(self) -> list[VoiceEvent]:
        events = self._log
        self._log = []
        return events

    def _apply(self, text: str, context: str, on_violation: Literal["substitute", "raise"]) -> str:
        # Em dash check
        for m in list(_EM_DASH_RE.finditer(text)):
            original = m.group(0)
            if on_violation == "raise":
                self._log.append(VoiceEvent(
                    rule="em_dash", original=original, replacement=None,
                    context=context, action="raise",
                ))
                raise VoiceViolationError("em_dash", original, context)

        text = _EM_DASH_RE.sub(lambda m: self._em_dash_replacement(m, text, context), text)

        # Forbidden word check
        for m in list(_FORBIDDEN_RE.finditer(text)):
            word = m.group(0)
            if on_violation == "raise":
                self._log.append(VoiceEvent(
                    rule="forbidden_word", original=word, replacement=None,
                    context=context, action="raise",
                ))
                raise VoiceViolationError("forbidden_word", word, context)

        text = _FORBIDDEN_RE.sub(
            lambda m: self._forbidden_replacement(m, context), text,
        )

        # Trademark check (always substitute, never raise)
        text = _GTM_GAP_RE.sub(lambda m: self._trademark_replacement(m, context), text, count=1)

        return text

    def _em_dash_replacement(self, m: re.Match[str], full_text: str, context: str) -> str:
        end = m.end()
        next_char = full_text[end] if end < len(full_text) else ""
        replacement_punct = ":" if next_char.isupper() else ";"
        replacement = f"{replacement_punct} "
        self._log.append(VoiceEvent(
            rule="em_dash", original=m.group(0), replacement=replacement,
            context=context, action="substitute",
        ))
        return replacement

    def _forbidden_replacement(self, m: re.Match[str], context: str) -> str:
        original = m.group(0)
        repl = SUBSTITUTIONS[original.lower()]
        cased = _match_case(repl, original)
        self._log.append(VoiceEvent(
            rule="forbidden_word", original=original, replacement=cased,
            context=context, action="substitute",
        ))
        return cased

    def _trademark_replacement(self, m: re.Match[str], context: str) -> str:
        original = m.group(0)
        replacement = "GTM Gap™"
        self._log.append(VoiceEvent(
            rule="trademark", original=original, replacement=replacement,
            context=context, action="substitute",
        ))
        return replacement
