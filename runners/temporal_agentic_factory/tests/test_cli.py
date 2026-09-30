from typer.testing import CliRunner

from temporal_agentic_factory.cli import app


def test_cli_lists_commands() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "runner" in result.output


def test_cli_offers_summarise() -> None:
    result = CliRunner().invoke(app, ["summarise", "--help"])
    assert result.exit_code == 0
    assert "--topic" in result.output and "--research-target" in result.output
