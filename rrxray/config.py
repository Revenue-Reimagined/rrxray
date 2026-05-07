"""Config: env + CLI flag merging via pydantic-settings."""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _today_yyyymmdd() -> str:
    return date.today().strftime("%Y%m%d")


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        case_sensitive=False,
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
