from typing import Any

import pytest
from typer.testing import CliRunner

from temporal_agentic_factory.cli import workflows
from temporal_agentic_factory.cli.app import app
from temporal_agentic_factory.schedules import ScheduleStatus


def _health(beads: ScheduleStatus, cleaner: ScheduleStatus) -> Any:
    async def info() -> dict[str, Any]:
        return {
            "address": "a",
            "beads_schedule": workflows.schedule_field(beads, workflows.SCHEDULE_DOWN),
            "cleaner_schedule": workflows.schedule_field(cleaner, workflows.CLEANER_DOWN),
        }

    return info


def _found(schedule_id: str, exists: bool = True, paused: bool = False) -> ScheduleStatus:
    return ScheduleStatus(schedule_id=schedule_id, exists=exists, paused=paused)


@pytest.mark.parametrize(("exists", "paused"), [(False, False), (True, True)])
def test_health_warns_when_the_beads_schedule_is_missing_or_paused(
    monkeypatch: Any, exists: bool, paused: bool
) -> None:
    beads = _found("beads-poll", exists, paused)
    monkeypatch.setattr(workflows, "_health_info", _health(beads, _found("cleaner")))
    result = CliRunner().invoke(app, ["health"])
    assert result.exit_code == 0, result.output
    assert f"af: warning: {workflows.SCHEDULE_DOWN}" in result.output
    assert workflows.CLEANER_DOWN not in result.output


@pytest.mark.parametrize(("exists", "paused"), [(False, False), (True, True)])
def test_health_warns_when_the_cleaner_schedule_is_missing_or_paused(
    monkeypatch: Any, exists: bool, paused: bool
) -> None:
    cleaner = _found("cleaner", exists, paused)
    monkeypatch.setattr(workflows, "_health_info", _health(_found("beads-poll"), cleaner))
    result = CliRunner().invoke(app, ["health"])
    assert result.exit_code == 0, result.output
    assert f"af: warning: {workflows.CLEANER_DOWN}" in result.output
    assert workflows.SCHEDULE_DOWN not in result.output


def test_health_is_quiet_when_both_schedules_fire(monkeypatch: Any) -> None:
    monkeypatch.setattr(workflows, "_health_info", _health(_found("beads-poll"), _found("cleaner")))
    result = CliRunner().invoke(app, ["health"])
    assert result.exit_code == 0, result.output
    assert '"cleaner_schedule"' in result.output
    assert '"exists": true' in result.output
    assert "warning" not in result.output
