"""CollectorContext + SynthesizerContext are frozen dataclasses with the right shape."""


def test_collector_context_is_frozen():
    from rrxray.context import CollectorContext

    fields = {f.name for f in CollectorContext.__dataclass_fields__.values()}
    assert fields == {
        "domain",
        "company_name",
        "firecrawl",
        "wayback",
        "evidence_dir",
        "config",
        "extractor",
        "leadership_enrichment",  # NEW Phase 2.2-deep
    }


def test_synthesizer_context_is_frozen():
    from rrxray.context import SynthesizerContext

    fields = {f.name for f in SynthesizerContext.__dataclass_fields__.values()}
    assert fields == {"collector_outputs", "anthropic", "voice", "anonymizer", "config"}


def test_collector_context_immutable():
    """Frozen dataclasses raise on attribute assignment."""
    from rrxray.context import CollectorContext

    assert CollectorContext.__dataclass_params__.frozen is True
