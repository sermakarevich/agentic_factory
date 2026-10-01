from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from temporalio.api.workflowservice.v1 import DeleteWorkflowExecutionRequest
from temporalio.client import Client, WorkflowExecutionStatus

from temporal_agentic_factory.watchers.beads.trim import CLOSED_RUNS, trimmed

START = datetime(2026, 10, 1, tzinfo=UTC)


@dataclass
class Run:
    """The fields of a listed execution that trimming reads."""

    id: str
    run_id: str
    workflow_type: str
    close_time: datetime | None
    start_time: datetime | None = START
    status: WorkflowExecutionStatus = WorkflowExecutionStatus.CONTINUED_AS_NEW


class FakeService:
    def __init__(self, failing: set[str]) -> None:
        self.failing = failing
        self.deleted: list[str] = []

    async def delete_workflow_execution(self, request: DeleteWorkflowExecutionRequest) -> None:
        run_id = request.workflow_execution.run_id
        if run_id in self.failing:
            raise RuntimeError("server said no")
        self.deleted.append(run_id)


class FakeClient:
    """Lists whatever runs it holds, whatever the query; records deletes."""

    def __init__(self, runs: list[Run], failing: set[str] | None = None, broken: bool = False):
        self.runs = runs
        self.broken = broken
        self.queries: list[str] = []
        self.workflow_service = FakeService(failing or set())

    async def list_workflows(self, query: str) -> Any:
        self.queries.append(query)
        if self.broken:
            raise RuntimeError("visibility down")
        for run in self.runs:
            yield run


def _at(minutes: int) -> datetime:
    return START + timedelta(minutes=minutes)


async def test_keeps_the_newest_runs_and_deletes_the_older_ones() -> None:
    runs = [Run("beads-watcher", f"r{m}", "beads_watcher", _at(m)) for m in (3, 1, 5, 2, 4)]
    client = FakeClient(runs)
    assert await trimmed(cast(Client, client), "default", keep=3) == 2
    assert sorted(client.workflow_service.deleted) == ["r1", "r2"]


async def test_old_poll_runs_go_too_and_a_run_without_close_time_sorts_by_its_start() -> None:
    runs = [
        Run("beads-watcher", "new", "beads_watcher", _at(10)),
        Run("beads-poll-1", "poll", "beads_poll", _at(1)),
        Run("beads-watcher", "unclosed", "beads_watcher", None, start_time=_at(0)),
    ]
    client = FakeClient(runs)
    await trimmed(cast(Client, client), "default", keep=1)
    assert sorted(client.workflow_service.deleted) == ["poll", "unclosed"]


async def test_never_touches_other_types_or_the_running_watcher() -> None:
    runs = [
        Run("job-1", "job", "job", _at(0)),
        Run("distill-1", "distill", "distill", _at(0)),
        Run("beads-watcher", "live", "beads_watcher", None, status=WorkflowExecutionStatus.RUNNING),
        Run("beads-watcher", "old", "beads_watcher", _at(1)),
    ]
    client = FakeClient(runs)
    await trimmed(cast(Client, client), "default", keep=0)
    assert client.workflow_service.deleted == ["old"]
    assert "WorkflowType = 'beads_watcher'" in client.queries[0]
    assert "WorkflowType = 'beads_poll'" in client.queries[0]
    assert "ExecutionStatus != 'Running'" in client.queries[0]
    assert client.queries == [CLOSED_RUNS]


async def test_a_failed_delete_is_skipped_and_the_rest_still_go() -> None:
    runs = [Run("beads-watcher", f"r{m}", "beads_watcher", _at(m)) for m in (1, 2, 3)]
    client = FakeClient(runs, failing={"r2"})
    assert await trimmed(cast(Client, client), "default", keep=0) == 2
    assert sorted(client.workflow_service.deleted) == ["r1", "r3"]


async def test_a_failed_listing_deletes_nothing_and_raises_nothing() -> None:
    client = FakeClient([Run("beads-watcher", "r", "beads_watcher", _at(1))], broken=True)
    assert await trimmed(cast(Client, client), "default", keep=0) == 0
    assert client.workflow_service.deleted == []
