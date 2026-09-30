from typer.testing import CliRunner

from temporal_agent_factory.cli import app


def test_cli_lists_commands() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "runner" in result.output
