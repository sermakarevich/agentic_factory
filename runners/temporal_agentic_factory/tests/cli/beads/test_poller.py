from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from temporal_agentic_factory.cli.app import app
from temporal_agentic_factory.cli.beads import opened
from temporal_agentic_factory.settings.load import settings
from tests.fake_bd import FakeBd


def _bd(monkeypatch: Any, home: Path, bd: FakeBd) -> FakeBd:
    """The cli's database at `home`, answered by `bd`."""
    monkeypatch.setattr(settings.beads, "home", str(home))
    monkeypatch.setattr(opened, "run_bd", bd)
    return bd


def test_ready_prints_the_beads_the_next_tick_would_pull(monkeypatch: Any, tmp_path: Path) -> None:
    (tmp_path / ".beads").mkdir()
    rows = [{"id": "af-1", "title": "T", "metadata": {"af_job": {"provider": "opencode"}}}]
    bd = _bd(monkeypatch, tmp_path, FakeBd({"ready": rows}))
    result = CliRunner().invoke(app, ["beads", "ready"])
    assert result.exit_code == 0, result.output
    assert '"provider": "opencode"' in result.output
    assert bd.calls[0][0][-2:] == [str(settings.beads_watcher.batch_limit), "--json"]


def test_poll_without_once_points_at_the_watcher(monkeypatch: Any, tmp_path: Path) -> None:
    (tmp_path / ".beads").mkdir()
    bd = _bd(monkeypatch, tmp_path, FakeBd())
    result = CliRunner().invoke(app, ["beads", "poll"])
    assert result.exit_code == 1
    assert "af beads start" in result.output
    assert bd.calls == []


@pytest.mark.parametrize("command", [["ready"], ["poll", "--once"], ["start"], ["restart"]])
def test_poller_commands_refuse_a_missing_database(
    monkeypatch: Any, tmp_path: Path, command: list[str]
) -> None:
    monkeypatch.setattr("temporal_agentic_factory.cli.beads.watcher._stopped", _stopped)
    bd = _bd(monkeypatch, tmp_path / "none", FakeBd())
    result = CliRunner().invoke(app, ["beads", *command])
    assert result.exit_code == 1
    assert "af beads init" in result.output
    assert bd.calls == []


async def _stopped() -> bool:
    return True
