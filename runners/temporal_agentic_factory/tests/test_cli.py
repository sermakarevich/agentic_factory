from typer.testing import CliRunner

from temporal_agentic_factory.cli import app


def test_cli_lists_commands() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "runner" in result.output


def test_cli_offers_distill() -> None:
    result = CliRunner().invoke(app, ["distill", "--help"])
    assert result.exit_code == 0
    assert "--topic" in result.output and "--research-target" in result.output
    assert "--target-dir" in result.output


def test_cli_run_takes_a_job_name() -> None:
    result = CliRunner().invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    assert "--name" in result.output
