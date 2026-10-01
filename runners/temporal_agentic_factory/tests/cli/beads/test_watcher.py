from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from temporal_agentic_factory.cli.app import app
from temporal_agentic_factory.cli.beads import watcher
from temporal_agentic_factory.settings.load import settings
from temporal_agentic_factory.watchers.beads.control import WatcherStatus
from temporal_agentic_factory.watchers.beads.workflow import WatcherConfig


class FakeServer:
    """Stands in for the watcher's calls on Temporal; records what the cli asked."""

    def __init__(self, legacy: bool, running: bool) -> None:
        self.legacy = legacy
        self.running = running
        self.started: list[tuple[str, WatcherConfig]] = []
        self.stopped: list[str] = []

    async def connect(self) -> object:
        return self

    async def deleted_legacy_schedule(self, client: object) -> bool:
        deleted, self.legacy = self.legacy, False
        return deleted

    async def register(self, client: object, namespace: str) -> list[str]:
        return []

    async def start_watcher(
        self, client: object, workflow_id: str, task_queue: str, config: WatcherConfig
    ) -> bool:
        if self.running:
            return False
        self.running = True
        self.started.append((workflow_id, config))
        return True

    async def stop_watcher(self, client: object, workflow_id: str, wait_sec: int) -> bool:
        self.running = False
        self.stopped.append(workflow_id)
        return True

    async def watcher_status(
        self, client: object, workflow_id: str, query_timeout_sec: int
    ) -> WatcherStatus:
        return WatcherStatus(
            workflow_id=workflow_id,
            running=self.running,
            status="RUNNING" if self.running else "ABSENT",
        )


@pytest.fixture
def server(monkeypatch: Any, tmp_path: Path) -> FakeServer:
    (tmp_path / ".beads").mkdir()
    monkeypatch.setattr(settings.beads, "home", str(tmp_path))
    fake = FakeServer(legacy=True, running=False)
    for name in ("connect", "deleted_legacy_schedule", "start_watcher", "stop_watcher"):
        monkeypatch.setattr(watcher, name, getattr(fake, name))
    monkeypatch.setattr(watcher, "watcher_status", fake.watcher_status)
    monkeypatch.setattr(watcher.search_attributes, "register", fake.register)
    return fake


def test_start_deletes_the_legacy_schedule_and_prints_the_watcher_id(server: FakeServer) -> None:
    result = CliRunner().invoke(app, ["beads", "start"])
    assert result.exit_code == 0, result.output
    assert "deleted the legacy schedule beads-poll" in result.output
    assert f"started: {settings.beads_watcher.workflow_id}" in result.output
    assert result.output.strip().endswith(settings.beads_watcher.workflow_id)
    workflow_id, config = server.started[0]
    assert workflow_id == settings.beads_watcher.workflow_id
    assert config.checks_per_run == settings.beads_watcher.checks_per_run


def test_start_twice_leaves_the_running_watcher_alone(server: FakeServer) -> None:
    CliRunner().invoke(app, ["beads", "start"])
    again = CliRunner().invoke(app, ["beads", "start"])
    assert again.exit_code == 0, again.output
    assert "already running" in again.output
    assert "legacy" not in again.output
    assert len(server.started) == 1


def test_restart_stops_then_starts(server: FakeServer) -> None:
    CliRunner().invoke(app, ["beads", "start"])
    result = CliRunner().invoke(app, ["beads", "restart"])
    assert result.exit_code == 0, result.output
    assert server.stopped == [settings.beads_watcher.workflow_id]
    assert len(server.started) == 2


def test_stop_that_does_not_end_in_time_fails(server: FakeServer, monkeypatch: Any) -> None:
    async def still_running(client: object, workflow_id: str, wait_sec: int) -> bool:
        return False

    monkeypatch.setattr(watcher, "stop_watcher", still_running)
    result = CliRunner().invoke(app, ["beads", "stop"])
    assert result.exit_code == 1
    assert "af terminate" in result.output


def test_status_prints_whether_it_runs(server: FakeServer) -> None:
    result = CliRunner().invoke(app, ["beads", "status"])
    assert result.exit_code == 0, result.output
    assert '"running": false' in result.output


def test_the_group_offers_the_watcher_commands_and_no_schedule() -> None:
    result = CliRunner().invoke(app, ["beads", "--help"])
    assert result.exit_code == 0
    for command in ("start", "stop", "restart", "status", "poll", "ready"):
        assert command in result.output
    assert "schedule" not in result.output
