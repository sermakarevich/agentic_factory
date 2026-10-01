from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from temporal_agentic_factory.cli.app import app
from temporal_agentic_factory.cli.beads import watcher
from temporal_agentic_factory.schedules import LastRun, ScheduleStatus
from temporal_agentic_factory.settings.load import settings
from temporal_agentic_factory.watchers.beads.workflow import PollConfig


class FakeServer:
    """Stands in for the schedule's calls on Temporal; records what the cli asked."""

    def __init__(self, old_watcher: bool) -> None:
        self.old_watcher = old_watcher
        self.exists = False
        self.started: list[tuple[str, int, PollConfig]] = []
        self.deleted = 0

    async def connect(self) -> "FakeServer":
        return self

    def get_schedule_handle(self, schedule_id: str) -> "FakeServer":
        return self

    async def register(self, client: object, namespace: str) -> list[str]:
        return []

    async def start_poll_schedule(
        self, client: object, schedule_id: str, task_queue: str, interval: int, config: PollConfig
    ) -> bool:
        replaced, self.exists = self.exists, True
        self.started.append((schedule_id, interval, config))
        return replaced

    async def end_old_watcher(self, client: object) -> bool:
        ended, self.old_watcher = self.old_watcher, False
        return ended

    async def delete_schedule(self, handle: object) -> bool:
        deleted, self.exists = self.exists, False
        self.deleted += deleted
        return deleted

    async def poll_schedule_status(self, client: object, schedule_id: str) -> ScheduleStatus:
        return ScheduleStatus(
            schedule_id=schedule_id,
            exists=True,
            interval_sec=30,
            next_run=datetime(2026, 10, 1, 12, 0, 30, tzinfo=UTC),
            last_run=LastRun(
                workflow_id="beads-poll-2026-10-01T12:00:00Z",
                run_id="r1",
                status="COMPLETED",
                result="spawned 1 closed 0 blocked 0 released 0 skipped 0 errors 0",
            ),
        )


@pytest.fixture
def server(monkeypatch: Any, tmp_path: Path) -> FakeServer:
    (tmp_path / ".beads").mkdir()
    monkeypatch.setattr(settings.beads, "home", str(tmp_path))
    fake = FakeServer(old_watcher=True)
    for name in (
        "start_poll_schedule",
        "end_old_watcher",
        "delete_schedule",
        "poll_schedule_status",
    ):
        monkeypatch.setattr(watcher, name, getattr(fake, name))
    monkeypatch.setattr(watcher, "connect", fake.connect)
    monkeypatch.setattr(watcher.search_attributes, "register", fake.register)
    return fake


def test_start_creates_the_schedule_ends_the_old_watcher_and_prints_the_id(
    server: FakeServer,
) -> None:
    result = CliRunner().invoke(app, ["beads", "start"])
    assert result.exit_code == 0, result.output
    cfg = settings.beads_poller
    assert f"created: {cfg.schedule_id}" in result.output
    assert "terminated the old watcher beads-watcher" in result.output
    assert result.output.strip().endswith(cfg.schedule_id)
    schedule_id, interval, config = server.started[0]
    assert (schedule_id, interval) == (cfg.schedule_id, cfg.interval_sec)
    assert config.tick_timeout_sec == cfg.tick_timeout_sec


def test_start_twice_replaces_the_schedule(server: FakeServer) -> None:
    CliRunner().invoke(app, ["beads", "start"])
    again = CliRunner().invoke(app, ["beads", "start"])
    assert again.exit_code == 0, again.output
    assert f"replaced: {settings.beads_poller.schedule_id}" in again.output
    assert "old watcher" not in again.output


def test_restart_deletes_then_creates(server: FakeServer) -> None:
    CliRunner().invoke(app, ["beads", "start"])
    result = CliRunner().invoke(app, ["beads", "restart"])
    assert result.exit_code == 0, result.output
    assert server.deleted == 1
    assert len(server.started) == 2


def test_stop_without_a_schedule_is_fine(server: FakeServer) -> None:
    result = CliRunner().invoke(app, ["beads", "stop"])
    assert result.exit_code == 0, result.output
    assert f"no schedule: {settings.beads_poller.schedule_id}" in result.output


def test_status_prints_the_next_run_and_the_last_runs_summary(server: FakeServer) -> None:
    result = CliRunner().invoke(app, ["beads", "status"])
    assert result.exit_code == 0, result.output
    assert '"exists": true' in result.output
    assert '"interval_sec": 30' in result.output
    assert '"next_run": "2026-10-01T12:00:30Z"' in result.output
    assert '"status": "COMPLETED"' in result.output
    assert "spawned 1 closed 0" in result.output


def test_the_group_offers_the_schedule_commands() -> None:
    result = CliRunner().invoke(app, ["beads", "--help"])
    assert result.exit_code == 0
    for command in ("start", "stop", "restart", "status", "poll", "ready"):
        assert command in result.output
