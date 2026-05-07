"""Config: env + CLI flag merging via pydantic-settings."""
import pytest
from pydantic import ValidationError


def test_config_loads_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test")
    from rrxray.config import Config

    c = Config(domain="example.com")
    assert c.anthropic_api_key.get_secret_value() == "sk-ant-test"
    assert c.firecrawl_api_key.get_secret_value() == "fc-test"


def test_config_defaults():
    from rrxray.config import Config
    c = Config(domain="example.com")
    assert c.mode == "internal"
    assert c.use_cache is True
    assert c.dry_run is False
    assert c.model == "claude-sonnet-4-6"
    assert c.firecrawl_max_concurrent == 5


def test_output_dir_default_uses_domain_slug_and_date(monkeypatch):
    monkeypatch.setattr("rrxray.config._today_yyyymmdd", lambda: "20260501")
    from rrxray.config import Config
    c = Config(domain="example.com")
    out = c.resolved_output_dir()
    assert "example-com" in str(out)
    assert "20260501" in str(out)


def test_evidence_dir_under_output_dir(tmp_path):
    from rrxray.config import Config
    c = Config(domain="example.com", output_dir=tmp_path / "out")
    assert c.resolved_output_dir() == tmp_path / "out"
    assert c.evidence_dir == tmp_path / "out" / "evidence"


def test_invalid_mode_rejected():
    from rrxray.config import Config
    with pytest.raises(ValidationError):
        Config(domain="example.com", mode="hook")  # Phase 3 mode; not yet valid
