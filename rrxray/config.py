"""Config: env + CLI flag merging via pydantic-settings."""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.sources import EnvSettingsSource


def _today_yyyymmdd() -> str:
    return date.today().strftime("%Y%m%d")


class _NonEmptyEnvSettingsSource(EnvSettingsSource):
    """Filter empty-string env vars so they fall through to .env file values."""

    def _load_env_vars(self):  # type: ignore[override]
        env_vars = super()._load_env_vars()
        return {k: v for k, v in env_vars.items() if v not in (None, "")}


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        case_sensitive=False,
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        return (
            init_settings,
            _NonEmptyEnvSettingsSource(settings_cls),
            dotenv_settings,
            file_secret_settings,
        )

    # API keys (loaded from bare env names)
    anthropic_api_key: SecretStr | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    firecrawl_api_key: SecretStr | None = Field(default=None, alias="FIRECRAWL_API_KEY")
    gamma_api_key: SecretStr | None = Field(default=None, alias="GAMMA_API_KEY")

    # Required runtime
    domain: str

    # Optional runtime
    company_name: str | None = None
    competitors: list[str] = []
    output_dir: Path | None = None
    skip_modules: list[str] = []
    mode: Literal["internal"] = "internal"
    use_cache: bool = True
    dry_run: bool = False
    model: str = "claude-sonnet-4-6"

    # Cache
    cache_dir: Path = Path.home() / ".rrxray" / "cache"
    cache_ttl_hours: int = 24

    # Concurrency
    firecrawl_max_concurrent: int = 5

    @field_validator("mode")
    @classmethod
    def _mode_valid(cls, v: str) -> str:
        if v != "internal":
            raise ValueError(
                f"Mode {v!r} not available in Phase 1; only 'internal' is implemented."
            )
        return v

    def resolved_output_dir(self) -> Path:
        if self.output_dir is not None:
            return self.output_dir
        slug = self.domain.replace(".", "-")
        return Path.cwd() / f"xray-{slug}-{_today_yyyymmdd()}"

    @property
    def evidence_dir(self) -> Path:
        return self.resolved_output_dir() / "evidence"
