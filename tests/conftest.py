"""Pytest configuration for rrxray test suite."""
from pathlib import Path

import pytest


@pytest.fixture
def fixture_cache_dir() -> Path:
    return Path(__file__).parent / "fixtures" / "cache"


@pytest.fixture
def synthetic_dir() -> Path:
    return Path(__file__).parent / "fixtures" / "synthetic"
