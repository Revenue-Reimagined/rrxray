"""Internal mode: full report; passthrough.

Phase 3 modes (hook, leave-behind, qbr) implement eligibility filters and reframing
logic by subclassing or replacing this passthrough.
"""
from __future__ import annotations

from rrxray.schemas.data import XrayData


def filter_for_internal(data: XrayData) -> XrayData:
    """Internal mode is full passthrough; returns data unchanged."""
    return data
