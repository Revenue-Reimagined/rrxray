"""Anonymizer: name registry + role-descriptor replacement + press-release whitelist."""
from __future__ import annotations

import re


class AnonymityViolationError(Exception):
    def __init__(self, name: str, text: str):
        self.name = name
        self.text = text
        super().__init__(
            f"Registered individual {name!r} appeared in output unanonymized: {text[:200]!r}"
        )


class Anonymizer:
    def __init__(self) -> None:
        self.name_to_role: dict[str, str] = {}
        self.whitelisted_names: set[str] = set()

    def register_individual(self, name: str, role_descriptor: str) -> None:
        self.name_to_role[name] = role_descriptor

    def whitelist_from_press(self, name: str) -> None:
        self.whitelisted_names.add(name)

    def anonymize(self, text: str) -> str:
        # Longest names first so multi-word names are matched as a unit.
        for name in sorted(self.name_to_role.keys(), key=len, reverse=True):
            if name in self.whitelisted_names:
                continue
            text = re.sub(re.escape(name), self.name_to_role[name], text)
        return text

    def assert_no_unanonymized(self, text: str) -> None:
        for name in self.name_to_role:
            if name in self.whitelisted_names:
                continue
            if name in text:
                raise AnonymityViolationError(name, text)
