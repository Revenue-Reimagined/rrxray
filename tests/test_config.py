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


def test_empty_env_var_falls_through_to_dotenv(monkeypatch, tmp_path):
    """An empty ANTHROPIC_API_KEY in os.environ should NOT shadow the .env file value."""
    env_file = tmp_path / ".env"
    env_file.write_text("ANTHROPIC_API_KEY=sk-ant-from-dotenv-file\n")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.chdir(tmp_path)

    from rrxray.config import Config
    c = Config(domain="example.com")
    assert c.anthropic_api_key is not None
    assert c.anthropic_api_key.get_secret_value() == "sk-ant-from-dotenv-file"


def test_empty_env_var_with_no_dotenv_leaves_key_unset(monkeypatch, tmp_path):
    """No .env, empty env var → field is None (not empty SecretStr)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.chdir(tmp_path)

    from rrxray.config import Config
    c = Config(domain="example.com")
    # Either None or absent; what matters is that empty SecretStr does not slip through
    if c.anthropic_api_key is not None:
        assert c.anthropic_api_key.get_secret_value() != ""


def test_extractor_model_default_haiku():
    from rrxray.config import Config
    c = Config(domain="example.com")
    assert c.extractor_model == "haiku"


def test_extractor_model_can_be_gemini_flash():
    from rrxray.config import Config
    c = Config(domain="example.com", extractor_model="gemini-flash")
    assert c.extractor_model == "gemini-flash"


def test_extractor_model_rejects_invalid():
    import pytest
    from pydantic import ValidationError

    from rrxray.config import Config
    with pytest.raises(ValidationError):
        Config(domain="example.com", extractor_model="claude-opus")


def test_pdl_api_key_loaded_from_env(monkeypatch):
    monkeypatch.setenv("PDL_API_KEY", "test-pdl-key")
    from rrxray.config import Config
    c = Config(domain="example.com")
    assert c.pdl_api_key is not None
    assert c.pdl_api_key.get_secret_value() == "test-pdl-key"


def test_pdl_cost_cap_dollars_default_five():
    from rrxray.config import Config
    c = Config(domain="example.com")
    assert c.pdl_cost_cap_dollars == 5.0


def test_pdl_cost_cap_dollars_overridable():
    from rrxray.config import Config
    c = Config(domain="example.com", pdl_cost_cap_dollars=10.0)
    assert c.pdl_cost_cap_dollars == 10.0


def test_no_pdl_default_false():
    from rrxray.config import Config
    c = Config(domain="example.com")
    assert c.no_pdl is False


def test_no_pdl_overridable():
    from rrxray.config import Config
    c = Config(domain="example.com", no_pdl=True)
    assert c.no_pdl is True
