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
