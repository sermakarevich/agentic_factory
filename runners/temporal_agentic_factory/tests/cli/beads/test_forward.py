"""`af beads bd ...` and unknown `af beads` commands, forwarded to a fake `bd`."""

from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from temporal_agentic_factory.cli.app import app
from temporal_agentic_factory.cli.beads import forward
from temporal_agentic_factory.settings.load import settings
from temporal_agentic_factory.watchers.beads.shell import BeadsError


class FakeForward:
    """Stands in for `forward_bd`: records each call, answers an exit code."""

    def __init__(self, code: int = 0) -> None:
        self.code = code
        self.calls: list[tuple[list[str], Path]] = []

    def __call__(self, args: list[str], cwd: Path) -> int:
        self.calls.append((args, cwd))
        return self.code


def _forwarded(monkeypatch: Any, home: Path, fake: FakeForward) -> FakeForward:
    monkeypatch.setattr(settings.beads, "home", str(home))
    monkeypatch.setattr(forward, "forward_bd", fake)
    return fake


def _initialised(tmp_path: Path) -> Path:
    (tmp_path / ".beads").mkdir(parents=True)
    return tmp_path


def _invoke(*args: str) -> Any:
    return CliRunner().invoke(app, ["beads", *args])


@pytest.mark.parametrize(
    "args",
    [
        ["dep", "add", "af-2", "af-1"],
        ["status"],
        ["list", "--status", "open", "-n3"],
        ["update", "af-1", "--help"],
        ["comment", "af-1", "--", "--not-a-flag"],
    ],
)
def test_bd_forwards_its_arguments_verbatim(
    monkeypatch: Any, tmp_path: Path, args: list[str]
) -> None:
    fake = _forwarded(monkeypatch, _initialised(tmp_path), FakeForward())
    result = _invoke("bd", *args)
    assert result.exit_code == 0, result.output
    assert fake.calls == [(args, tmp_path)]


def test_bd_passes_the_exit_code_through(monkeypatch: Any, tmp_path: Path) -> None:
    _forwarded(monkeypatch, _initialised(tmp_path), FakeForward(code=3))
    assert _invoke("bd", "show", "af-404").exit_code == 3


def test_an_unknown_command_is_forwarded(monkeypatch: Any, tmp_path: Path) -> None:
    fake = _forwarded(monkeypatch, _initialised(tmp_path), FakeForward(code=2))
    result = _invoke("dep", "tree", "af-1", "--json")
    assert result.exit_code == 2
    assert fake.calls == [(["dep", "tree", "af-1", "--json"], tmp_path)]


def test_afs_own_commands_are_not_forwarded(monkeypatch: Any, tmp_path: Path) -> None:
    fake = _forwarded(monkeypatch, _initialised(tmp_path), FakeForward())
    monkeypatch.setattr("temporal_agentic_factory.cli.beads.watcher._status_json", _status_json)
    result = _invoke("status")
    assert result.stdout == "{}\n"
    assert fake.calls == []


def test_bd_refuses_a_missing_database(monkeypatch: Any, tmp_path: Path) -> None:
    fake = _forwarded(monkeypatch, tmp_path / "none", FakeForward())
    result = _invoke("bd", "list")
    assert result.exit_code == 1
    assert "af beads init" in result.output
    assert fake.calls == []


def test_bd_that_cannot_start_is_one_clean_line(monkeypatch: Any, tmp_path: Path) -> None:
    def missing(args: list[str], cwd: Path) -> int:
        raise BeadsError("bd executable not found")

    monkeypatch.setattr(settings.beads, "home", str(_initialised(tmp_path)))
    monkeypatch.setattr(forward, "forward_bd", missing)
    result = _invoke("bd", "list")
    assert result.exit_code == 1
    assert result.output.startswith("af: error: bd executable not found")


async def _status_json() -> str:
    return "{}"
