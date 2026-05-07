"""Mode interface: defines what data fields are eligible per mode.

Phase 1: only `internal` is implemented. Phase 3 fills in `hook`, `leave-behind`, `qbr`.
"""
from __future__ import annotations

from enum import StrEnum


class Mode(StrEnum):
    INTERNAL = "internal"
    HOOK = "hook"             # Phase 3
    LEAVE_BEHIND = "leave-behind"  # Phase 3
    QBR = "qbr"               # Phase 3
    ALL = "all"               # Phase 3
