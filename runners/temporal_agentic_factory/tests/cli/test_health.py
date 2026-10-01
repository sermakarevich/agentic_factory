from typing import Any

import pytest
from typer.testing import CliRunner

from temporal_agentic_factory.cli import workflows
from temporal_agentic_factory.cli.app import app
from temporal_agentic_factory.watchers.beads.control import ScheduleStatus


def _health(exists: bool, paused: bool) -> Any:
    async def info() -> dict[str, Any]:
        found = ScheduleStatus(schedule_id="beads-poll", exists=exists, paused=paused)
        return {"address": "a", "beads_schedule": workflows.schedule_field(found)}

    return info


@pytest.mark.parametrize(("exists", "paused"), [(False, False), (True, True)])
def test_health_warns_when_the_schedule_is_missing_or_paused(
    monkeypatch: Any, exists: bool, paused: bool
) -> None:
    monkeypatch.setattr(workflows, "_health_info", _health(exists, paused))
    result = CliRunner().invoke(app, ["health"])
    assert result.exit_code == 0, result.output
    assert f"af: warning: {workflows.SCHEDULE_DOWN}" in result.output


def test_health_is_quiet_when_the_schedule_fires(monkeypatch: Any) -> None:
    monkeypatch.setattr(workflows, "_health_info", _health(exists=True, paused=False))
    result = CliRunner().invoke(app, ["health"])
    assert result.exit_code == 0, result.output
    assert '"exists": true' in result.output
    assert "warning" not in result.output
