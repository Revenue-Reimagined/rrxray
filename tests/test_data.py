"""Tests for rrxray.schemas.data module."""
import json
from datetime import UTC, datetime

from rrxray.schemas.data import CollectorOutputs, InputParams, RunMetadata, XrayData
from rrxray.schemas.leadership_stability import FounderTenure, LeadershipStabilityData


def test_data_json_round_trips_with_leadership_stability():
    """XrayData round-trips with leadership_stability collector output populated."""
    data = XrayData(
        domain="example.com",
        run_metadata=RunMetadata(
            timestamp=datetime.now(UTC),
            tool_version="0.1",
            modes_built=["internal"],
            model_used="claude-sonnet-4-6",
        ),
        inputs=InputParams(domain="example.com"),
        collectors=CollectorOutputs(
            leadership_stability=LeadershipStabilityData(
                founder_tenure=FounderTenure(inferred_year=2018, source="about_page"),
            ),
        ),
    )
    serialized = data.model_dump_json()
    restored = XrayData.model_validate(json.loads(serialized))
    assert restored.collectors.leadership_stability.founder_tenure.inferred_year == 2018
