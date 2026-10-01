from datetime import UTC, datetime
from typing import Any

import pytest
from typer.testing import CliRunner

from temporal_agentic_factory.cleaner.rules import CleanSummary, TypeCleaned
from temporal_agentic_factory.cleaner.workflow import CleanConfig
from temporal_agentic_factory.cli import cleaner
from temporal_agentic_factory.cli.app import app
from temporal_agentic_factory.schedules import LastRun, ScheduleStatus
from temporal_agentic_factory.settings.load import settings
from temporal_agentic_factory.settings.model import CleanRule


class FakeServer:
    """Stands in for the cleaner's calls on Temporal; records what the cli asked."""

    def __init__(self) -> None:
        self.exists = False
        self.started: list[tuple[str, str, int, CleanConfig]] = []
        self.deleted = 0
        self.cleans: list[tuple[str, list[CleanRule]]] = []

    async def connect(self) -> "FakeServer":
        return self

    def get_schedule_handle(self, schedule_id: str) -> "FakeServer":
        return self

    async def start_cleaner_schedule(
        self, client: object, schedule_id: str, task_queue: str, interval: int, config: CleanConfig
    ) -> bool:
        replaced, self.exists = self.exists, True
        self.started.append((schedule_id, task_queue, interval, config))
        return replaced

    async def delete_schedule(self, handle: object) -> bool:
        deleted, self.exists = self.exists, False
        self.deleted += deleted
        return deleted

    async def cleaner_schedule_status(self, client: object, schedule_id: str) -> ScheduleStatus:
        return ScheduleStatus(
            schedule_id=schedule_id,
            exists=True,
            interval_sec=60,
            next_run=datetime(2026, 10, 1, 12, 1, tzinfo=UTC),
            last_run=LastRun(
                workflow_id="cleaner-2026-10-01T12:00:00Z",
                run_id="r1",
                status="COMPLETED",
                result="beads_poll: completed 2 failed 0 errors 0",
            ),
        )

    async def cleaned(self, client: object, namespace: str, rules: list[CleanRule]) -> CleanSummary:
        self.cleans.append((namespace, rules))
        return CleanSummary(types=[TypeCleaned(workflow_type="beads_poll", completed=3)])


@pytest.fixture
def server(monkeypatch: Any) -> FakeServer:
    fake = FakeServer()
    for name in ("start_cleaner_schedule", "delete_schedule", "cleaner_schedule_status", "cleaned"):
        monkeypatch.setattr(cleaner, name, getattr(fake, name))
    monkeypatch.setattr(cleaner, "connect", fake.connect)
    return fake


def test_start_creates_the_schedule_with_the_configured_rules(server: FakeServer) -> None:
    result = CliRunner().invoke(app, ["cleaner", "start"])
    assert result.exit_code == 0, result.output
    cfg = settings.cleaner
    assert f"created: {cfg.schedule_id}" in result.output
    assert result.output.strip().endswith(cfg.schedule_id)
    schedule_id, task_queue, interval, config = server.started[0]
    assert (schedule_id, task_queue, interval) == (
        cfg.schedule_id,
        settings.temporal.task_queue,
        cfg.interval_sec,
    )
    assert config == CleanConfig(rules=cfg.rules, timeout_sec=cfg.timeout_sec)
    assert {rule.workflow_type for rule in config.rules} == {"beads_poll", "cleaner"}


def test_restart_deletes_then_creates(server: FakeServer) -> None:
    CliRunner().invoke(app, ["cleaner", "start"])
    result = CliRunner().invoke(app, ["cleaner", "restart"])
    assert result.exit_code == 0, result.output
    assert server.deleted == 1
    assert len(server.started) == 2
    assert f"replaced: {settings.cleaner.schedule_id}" not in result.output


def test_stop_without_a_schedule_is_fine(server: FakeServer) -> None:
    result = CliRunner().invoke(app, ["cleaner", "stop"])
    assert result.exit_code == 0, result.output
    assert f"no schedule: {settings.cleaner.schedule_id}" in result.output


def test_status_prints_the_next_run_and_what_the_last_clean_deleted(server: FakeServer) -> None:
    result = CliRunner().invoke(app, ["cleaner", "status"])
    assert result.exit_code == 0, result.output
    assert '"interval_sec": 60' in result.output
    assert '"next_run": "2026-10-01T12:01:00Z"' in result.output
    assert "beads_poll: completed 2 failed 0 errors 0" in result.output


def test_run_cleans_once_with_the_configured_rules_and_prints_the_summary(
    server: FakeServer,
) -> None:
    result = CliRunner().invoke(app, ["cleaner", "run"])
    assert result.exit_code == 0, result.output
    assert server.cleans == [(settings.temporal.namespace, settings.cleaner.rules)]
    assert '"workflow_type": "beads_poll"' in result.output
    assert '"completed": 3' in result.output


def test_the_group_offers_its_commands() -> None:
    result = CliRunner().invoke(app, ["cleaner", "--help"])
    assert result.exit_code == 0
    for command in ("start", "stop", "restart", "status", "run"):
        assert command in result.output
