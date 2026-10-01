from typing import Any

from typer.testing import CliRunner

from temporal_agentic_factory.cli import workflows
from temporal_agentic_factory.cli.app import app
from temporal_agentic_factory.watchers.beads.control import WatcherStatus


def _health(running: bool) -> Any:
    async def info() -> dict[str, Any]:
        found = WatcherStatus(workflow_id="beads-watcher", running=running, status="ABSENT")
        return {"address": "a", "beads_watcher": workflows.watcher_field(found)}

    return info


def test_health_warns_when_the_watcher_does_not_run(monkeypatch: Any) -> None:
    monkeypatch.setattr(workflows, "_health_info", _health(running=False))
    result = CliRunner().invoke(app, ["health"])
    assert result.exit_code == 0, result.output
    assert '"running": false' in result.output
    assert f"af: warning: {workflows.WATCHER_DOWN}" in result.output


def test_health_is_quiet_when_the_watcher_runs(monkeypatch: Any) -> None:
    monkeypatch.setattr(workflows, "_health_info", _health(running=True))
    result = CliRunner().invoke(app, ["health"])
    assert result.exit_code == 0, result.output
    assert "warning" not in result.output
