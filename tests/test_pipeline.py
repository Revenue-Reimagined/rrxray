"""Pipeline-level tests for post-collection helpers."""
from __future__ import annotations


def test_pipeline_registers_leadership_stability_name_registrations(tmp_path):
    """Pipeline post-collection: anonymizer.register_individual called per name_registration;
    whitelist_from_press called for whitelisted entries.
    """
    from rrxray.schemas.leadership_stability import (
        LeadershipStabilityData,
        NameRegistration,
    )
    from rrxray.voice.anonymizer import Anonymizer

    anonymizer = Anonymizer()
    data = LeadershipStabilityData(
        name_registrations=[
            NameRegistration(name="Jane Doe", role_descriptor="Acme's CRO", whitelist=True),
            NameRegistration(name="Bob Smith", role_descriptor="Acme's CMO", whitelist=False),
        ],
    )

    from rrxray.pipeline import _register_collector_names

    _register_collector_names(anonymizer, data.name_registrations)

    # Both registered
    assert "Jane Doe" in anonymizer.name_to_role
    assert "Bob Smith" in anonymizer.name_to_role
    # Only Jane is whitelisted (press)
    assert "Jane Doe" in anonymizer.whitelisted_names
    assert "Bob Smith" not in anonymizer.whitelisted_names


def test_collectors_includes_leadership_stability():
    from rrxray import pipeline

    names = [c.NAME for c in pipeline.COLLECTORS]
    assert "leadership_stability" in names


def test_synthesizers_includes_observed_stability_trajectory():
    from rrxray import pipeline

    names = [s.NAME for s in pipeline.SYNTHESIZERS]
    assert "observed_stability_trajectory" in names


def test_data_json_round_trips_with_observed_stability_trajectory():
    from datetime import UTC, datetime

    from rrxray.schemas.data import (
        InputParams,
        ObservedStabilityTrajectoryNarrative,
        RunMetadata,
        SynthesizerOutputs,
        XrayData,
    )

    data = XrayData(
        domain="example.com",
        run_metadata=RunMetadata(
            timestamp=datetime.now(UTC),
            tool_version="0.1",
            modes_built=["internal"],
            model_used="claude-sonnet-4-6",
        ),
        inputs=InputParams(domain="example.com"),
        synthesizers=SynthesizerOutputs(
            observed_stability_trajectory=ObservedStabilityTrajectoryNarrative(
                narrative_paragraphs=["Test paragraph."],
                model_used="claude-sonnet-4-6",
                cache_hit=False,
            ),
        ),
    )
    import json

    restored = XrayData.model_validate(json.loads(data.model_dump_json()))
    assert restored.synthesizers.observed_stability_trajectory.narrative_paragraphs == [
        "Test paragraph."
    ]
