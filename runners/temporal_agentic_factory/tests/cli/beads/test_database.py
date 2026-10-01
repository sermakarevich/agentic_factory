"""`af beads init/list/show/close` over a fake `bd` in a temp home."""

from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from temporal_agentic_factory.cli.app import app
from temporal_agentic_factory.cli.beads import opened
from temporal_agentic_factory.settings.load import settings
from temporal_agentic_factory.watchers.beads.client import INIT
from tests.fake_bd import FakeBd


def _bd(monkeypatch: Any, home: Path, bd: FakeBd) -> FakeBd:
    """The cli's database at `home`, answered by `bd`."""
    monkeypatch.setattr(settings.beads, "home", str(home))
    monkeypatch.setattr(opened, "run_bd", bd)
    return bd


def _initialised(tmp_path: Path) -> Path:
    (tmp_path / ".beads").mkdir(parents=True)
    return tmp_path


def _invoke(*args: str) -> Any:
    return CliRunner().invoke(app, ["beads", *args])


def test_init_creates_the_home_and_prints_it(monkeypatch: Any, tmp_path: Path) -> None:
    home = tmp_path / "deep" / "beads"
    bd = _bd(monkeypatch, home, FakeBd())
    result = _invoke("init")
    assert result.exit_code == 0, result.output
    assert home.is_dir()
    assert bd.calls == [(INIT, home, settings.beads.command_timeout_sec)]
    assert str(home) in result.stdout


def test_init_twice_changes_nothing(monkeypatch: Any, tmp_path: Path) -> None:
    bd = _bd(monkeypatch, _initialised(tmp_path), FakeBd())
    result = _invoke("init")
    assert result.exit_code == 0
    assert "already initialised" in result.output
    assert bd.calls == []


def test_home_with_tilde_is_expanded(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    bd = _bd(monkeypatch, Path("~/beads"), FakeBd())
    assert _invoke("init").exit_code == 0
    assert bd.calls[0][1] == tmp_path / "beads"


FILTERED = ["list", "--status", "open", "--limit", "3"]


@pytest.mark.parametrize(
    ("command", "argv"),
    [
        (["list"], ["list"]),
        (FILTERED, FILTERED),
        (["list", "--json"], ["list", "--json"]),
        (["show", "af-1"], ["show", "af-1"]),
        (["show", "af-1", "--json"], ["show", "af-1", "--json"]),
        (["close", "af-1"], ["close", "af-1"]),
        (["close", "af-1", "--reason", "done"], ["close", "af-1", "--reason", "done"]),
    ],
)
def test_pass_throughs_print_bds_output(
    monkeypatch: Any, tmp_path: Path, command: list[str], argv: list[str]
) -> None:
    bd = _bd(monkeypatch, _initialised(tmp_path), FakeBd({argv[0]: "bd says hi\n"}))
    result = _invoke(*command)
    assert result.exit_code == 0, result.output
    assert result.stdout == "bd says hi\n"
    assert bd.calls == [(argv, tmp_path, settings.beads.command_timeout_sec)]


def test_a_failed_bd_call_is_one_clean_line(monkeypatch: Any, tmp_path: Path) -> None:
    _bd(monkeypatch, _initialised(tmp_path), FakeBd(failing={"show"}))
    result = _invoke("show", "af-404")
    assert result.exit_code == 1
    assert result.output.startswith("af: error: bd show af-404")


@pytest.mark.parametrize(
    "command",
    [
        ["list"],
        ["show", "af-1"],
        ["close", "af-1"],
    ],
)
def test_commands_refuse_a_missing_database(
    monkeypatch: Any, tmp_path: Path, command: list[str]
) -> None:
    bd = _bd(monkeypatch, tmp_path / "none", FakeBd())
    result = _invoke(*command)
    assert result.exit_code == 1
    assert "af beads init" in result.output
    assert bd.calls == []
