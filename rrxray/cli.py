"""rrxray CLI: typer app with run, collect, synthesize, render subcommands."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer
from pydantic import ValidationError

from rrxray.config import Config

app = typer.Typer(name="rrxray", help="Revenue Reimagined GTM X-Ray™: externally-sourced GTM diagnostic")


def _build_config(**kwargs) -> Config:
    """Build Config, exiting cleanly on validation errors."""
    cleaned = {k: v for k, v in kwargs.items() if v is not None}
    try:
        return Config(**cleaned)
    except ValidationError as e:
        typer.echo(f"Configuration error: {e}", err=True)
        raise typer.Exit(code=1) from e


def _print_dry_run_plan(config: Config) -> None:
    from rrxray import pipeline

    collector_names = [c.NAME for c in pipeline.COLLECTORS]
    synth_names = [s.NAME for s in pipeline.SYNTHESIZERS]
    has_revenue_motion = "revenue_motion" in collector_names

    # Approximate call counts. Each collector scrapes 1-2 surfaces; pricing
    # also pulls up to 3 Wayback snapshots; revenue_motion adds 2 LinkedIn
    # search calls (jobs + employee count). Conditional ATS scrape (~1) not
    # counted — present on roughly half of careers pages.
    scrape_per_collector = 2
    wayback_calls = 3
    firecrawl_scrapes = len(collector_names) * scrape_per_collector + wayback_calls
    firecrawl_searches = 2 if has_revenue_motion else 0

    # Cost model: Firecrawl ~$0.005/call, Anthropic ~$0.027/synthesizer (uncached).
    fc_cost = (firecrawl_scrapes + firecrawl_searches) * 0.005
    ant_cost = len(synth_names) * 0.027
    total = fc_cost + ant_cost

    typer.echo("Plan:")
    typer.echo(f"  Domain: {config.domain}")
    typer.echo(f"  Collectors: {', '.join(collector_names)}")
    typer.echo(f"  Synthesizers: {', '.join(synth_names)}")
    typer.echo(f"  Mode: {config.mode}")
    typer.echo("")
    typer.echo("Estimated calls:")
    typer.echo(
        f"  Firecrawl scrape_url: ~{firecrawl_scrapes} "
        f"({len(collector_names)} collectors x ~{scrape_per_collector} + {wayback_calls} Wayback)"
    )
    if firecrawl_searches:
        typer.echo(
            f"  Firecrawl search: ~{firecrawl_searches} "
            f"(LinkedIn jobs + employee count for revenue_motion)"
        )
    typer.echo(
        f"  Anthropic complete: {len(synth_names)} "
        f"({config.model}, ~5K input + ~800 output each)"
    )
    typer.echo("")
    typer.echo("Estimated cost:")
    typer.echo(f"  Firecrawl: ~${fc_cost:.3f}")
    typer.echo(f"  Anthropic: ~${ant_cost:.3f} uncached")
    typer.echo(f"  Total: ~${total:.2f}")
    typer.echo("")
    typer.echo(f"Cache: {'enabled' if config.use_cache else 'disabled'} ({config.cache_dir})")
    typer.echo(f"Output: {config.resolved_output_dir()}")


def _execute_run(config: Config) -> None:
    """Run the full pipeline and write outputs to disk."""
    from rrxray.pipeline import run_pipeline

    config.resolved_output_dir().mkdir(parents=True, exist_ok=True)
    config.evidence_dir.mkdir(parents=True, exist_ok=True)

    data, rendered = asyncio.run(run_pipeline(config))

    out_dir = config.resolved_output_dir()
    (out_dir / "data.json").write_text(data.model_dump_json(indent=2))
    (out_dir / f"report.{config.mode}.md").write_text(rendered)

    typer.echo(f"Wrote {out_dir / 'data.json'}")
    typer.echo(f"Wrote {out_dir / f'report.{config.mode}.md'}")


@app.command()
def run(
    domain: str = typer.Option(..., "--domain"),
    company_name: str | None = typer.Option(None, "--company-name"),
    output_dir: Path | None = typer.Option(None, "--output-dir"),
    skip_modules: str = typer.Option("", "--skip-modules"),
    mode: str = typer.Option("internal", "--mode"),
    use_cache: bool = typer.Option(True, "--use-cache/--no-cache"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    model: str = typer.Option("claude-sonnet-4-6", "--model"),
    extractor: str = typer.Option(
        "haiku",
        "--extractor",
        help="LLM model used for press-release / LinkedIn extraction in leadership_stability. "
             "Choices: haiku (default), gemini-flash. gemini-flash requires GEMINI_API_KEY.",
    ),
):
    """Full pipeline: collect -> synthesize -> render."""
    config = _build_config(
        domain=domain, company_name=company_name, output_dir=output_dir,
        skip_modules=[s.strip() for s in skip_modules.split(",") if s.strip()],
        mode=mode, use_cache=use_cache, dry_run=dry_run, model=model,
        extractor_model=extractor,
    )
    if config.dry_run:
        _print_dry_run_plan(config)
        return
    _execute_run(config)


@app.command()
def collect(
    domain: str = typer.Option(..., "--domain"),
    output_dir: Path | None = typer.Option(None, "--output-dir"),
    use_cache: bool = typer.Option(True, "--use-cache/--no-cache"),
):
    """Collectors only: writes data.json with synthesizers section empty."""
    typer.echo("collect subcommand: stubbed in Phase 1; use 'run' for the full pipeline.", err=True)
    raise typer.Exit(code=0)


@app.command()
def synthesize(
    data: Path = typer.Option(..., "--data"),
    model: str = typer.Option("claude-sonnet-4-6", "--model"),
):
    """Synthesizers only: reads data.json, fills synthesizers section, writes back."""
    typer.echo("synthesize subcommand: stubbed in Phase 1; use 'run' for the full pipeline.", err=True)
    raise typer.Exit(code=0)


@app.command()
def render(
    data: Path = typer.Option(..., "--data"),
    mode: str = typer.Option("internal", "--mode"),
    output_dir: Path | None = typer.Option(None, "--output-dir"),
):
    """Renderers only: reads data.json, writes report.{mode}.md."""
    if mode != "internal":
        typer.echo(f"Mode {mode!r} not available in Phase 1; only 'internal' is implemented.", err=True)
        raise typer.Exit(code=1)
    from rrxray.rendering.markdown import render_internal
    from rrxray.schemas.data import XrayData
    from rrxray.voice.anonymizer import Anonymizer
    from rrxray.voice.rr_voice import VoicePostProcessor

    payload = json.loads(data.read_text())
    xray_data = XrayData.model_validate(payload)

    voice = VoicePostProcessor()
    anonymizer = Anonymizer()
    rendered = render_internal(xray_data, anonymizer, voice)

    out_path = (output_dir or data.parent) / f"report.{mode}.md"
    out_path.write_text(rendered)
    typer.echo(f"Wrote {out_path}")


if __name__ == "__main__":
    app()
