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
        """Replace every registered, non-whitelisted name with its role descriptor.

        Matching uses ASCII word boundaries (`\\b`); names that appear as substrings
        of unrelated words are NOT replaced (e.g., 'Lee' won't match 'Bradlee').
        Replacement is performed via a lambda to avoid regex backreference
        interpretation (so role descriptors containing '\\1', '\\g<0>', etc. are
        treated as literal text).
        """
        for name in sorted(self.name_to_role.keys(), key=len, reverse=True):
            if name in self.whitelisted_names:
                continue
            role = self.name_to_role[name]
            pattern = r"\b" + re.escape(name) + r"\b"
            text = re.sub(pattern, lambda _m, r=role: r, text)
        return text

    def assert_no_unanonymized(self, text: str) -> None:
        """Raise AnonymityViolationError if any registered, non-whitelisted name
        appears in `text` as a whole word. Defense in depth: callers must invoke
        anonymize() before reaching here; this guard catches code paths that
        bypass that filter.
        """
        for name in self.name_to_role:
            if name in self.whitelisted_names:
                continue
            pattern = r"\b" + re.escape(name) + r"\b"
            if re.search(pattern, text):
                raise AnonymityViolationError(name, text)
