"""The `coders` command's one-per-machine guard."""

from typing import Any

from typer.testing import CliRunner

from temporal_agentic_factory.cli import coders as cli
from temporal_agentic_factory.cli.app import app


def test_coders_refuses_to_start_beside_another(monkeypatch: Any) -> None:
    monkeypatch.setattr(cli, "other_coders_pids", lambda: [4242])

    def never(identity: str) -> None:
        raise AssertionError("must not serve")

    monkeypatch.setattr(cli, "serve_coders", never)

    result = CliRunner().invoke(app, ["coders"])

    assert result.exit_code == 1
    assert (
        "af: error: another `factory coders` process is already running (pid 4242);"
        " stop it first: just coders-stop"
    ) in result.output
