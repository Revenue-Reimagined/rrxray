"""CLI: typer subcommands; only --mode internal allowed in Phase 1."""
from typer.testing import CliRunner

from rrxray.cli import app

runner = CliRunner()


def test_cli_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "rrxray" in result.stdout.lower() or "Usage" in result.stdout


def test_run_subcommand_help():
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    assert "--domain" in result.stdout


def test_render_subcommand_help():
    result = runner.invoke(app, ["render", "--help"])
    assert result.exit_code == 0
    assert "--data" in result.stdout


def test_collect_subcommand_help():
    result = runner.invoke(app, ["collect", "--help"])
    assert result.exit_code == 0


def test_synthesize_subcommand_help():
    result = runner.invoke(app, ["synthesize", "--help"])
    assert result.exit_code == 0


def test_run_rejects_non_internal_mode():
    result = runner.invoke(app, ["run", "--domain", "example.com", "--mode", "hook"])
    assert result.exit_code != 0
    assert "not available" in result.stdout or "not available" in result.stderr or \
           "internal" in result.stdout or "internal" in result.stderr


def test_run_dry_run_does_not_call_apis(monkeypatch, tmp_path):
    """--dry-run prints a plan and exits without calling pipeline."""
    called = []
    monkeypatch.setattr("rrxray.cli._execute_run", lambda config: called.append(1))
    result = runner.invoke(app, [
        "run", "--domain", "example.com", "--dry-run",
    ])
    assert result.exit_code == 0
    assert "Plan" in result.stdout or "plan" in result.stdout
    assert called == []
