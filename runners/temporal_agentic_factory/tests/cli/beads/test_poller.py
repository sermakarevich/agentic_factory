from pathlib import Path
from typing import Any, cast

import pytest
from temporalio.client import ScheduleHandle
from temporalio.service import RPCError, RPCStatusCode
from typer.testing import CliRunner

from temporal_agentic_factory.cli.app import app
from temporal_agentic_factory.cli.beads import opened
from temporal_agentic_factory.cli.beads.poller import delete_schedule
from temporal_agentic_factory.settings.load import settings
from tests.fake_bd import FakeBd


class FakeHandle:
    """A schedule handle whose delete fails with the given error, or succeeds."""

    def __init__(self, error: RPCError | None) -> None:
        self.error = error
        self.deleted = False

    async def delete(self) -> None:
        if self.error is not None:
            raise self.error
        self.deleted = True


def _bd(monkeypatch: Any, home: Path, bd: FakeBd) -> FakeBd:
    """The cli's database at `home`, answered by `bd`."""
    monkeypatch.setattr(settings.beads, "home", str(home))
    monkeypatch.setattr(opened, "run_bd", bd)
    return bd


async def test_delete_schedule_deletes_an_existing_one() -> None:
    handle = FakeHandle(None)
    await delete_schedule(cast(ScheduleHandle, handle))
    assert handle.deleted


async def test_delete_schedule_treats_not_found_as_nothing_to_delete() -> None:
    error = RPCError("workflow execution already completed", RPCStatusCode.NOT_FOUND, b"")
    await delete_schedule(cast(ScheduleHandle, FakeHandle(error)))


async def test_delete_schedule_raises_other_failures() -> None:
    error = RPCError("schedule not found, they say", RPCStatusCode.UNAVAILABLE, b"")
    with pytest.raises(RPCError):
        await delete_schedule(cast(ScheduleHandle, FakeHandle(error)))


def test_ready_prints_the_beads_the_next_tick_would_pull(monkeypatch: Any, tmp_path: Path) -> None:
    (tmp_path / ".beads").mkdir()
    rows = [{"id": "af-1", "title": "T", "metadata": {"af_provider": "opencode"}}]
    bd = _bd(monkeypatch, tmp_path, FakeBd({"ready": rows}))
    result = CliRunner().invoke(app, ["beads", "ready"])
    assert result.exit_code == 0, result.output
    assert '"provider": "opencode"' in result.output
    assert bd.calls[0][0][-2:] == [str(settings.beads_poller.batch_limit), "--json"]


@pytest.mark.parametrize("command", [["ready"], ["poll", "--once"], ["schedule"]])
def test_poller_commands_refuse_a_missing_database(
    monkeypatch: Any, tmp_path: Path, command: list[str]
) -> None:
    bd = _bd(monkeypatch, tmp_path / "none", FakeBd())
    result = CliRunner().invoke(app, ["beads", *command])
    assert result.exit_code == 1
    assert "af beads init" in result.output
    assert bd.calls == []
