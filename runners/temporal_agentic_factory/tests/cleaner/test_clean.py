from typing import Any, cast

from temporalio.api.workflowservice.v1 import DeleteWorkflowExecutionRequest
from temporalio.client import Client

from temporal_agentic_factory.cleaner.clean import cleaned, closed_runs_query
from temporal_agentic_factory.cleaner.rules import TypeCleaned
from temporal_agentic_factory.settings.model import CleanRule
from tests.cleaner.listed import FAILED, Listed, at


class FakeService:
    def __init__(self, failing: set[str]) -> None:
        self.failing = failing
        self.deleted: list[tuple[str, str, str]] = []

    async def delete_workflow_execution(self, request: DeleteWorkflowExecutionRequest) -> None:
        execution = request.workflow_execution
        if execution.run_id in self.failing:
            raise RuntimeError("server said no")
        self.deleted.append((request.namespace, execution.workflow_id, execution.run_id))


class FakeClient:
    """Lists whatever runs it holds, whatever the query; records queries and deletes."""

    def __init__(
        self, runs: list[Listed], failing: set[str] | None = None, broken: set[str] | None = None
    ) -> None:
        self.runs = runs
        self.broken = broken or set()
        self.queries: list[str] = []
        self.workflow_service = FakeService(failing or set())

    async def list_workflows(self, query: str) -> Any:
        self.queries.append(query)
        if query in self.broken:
            raise RuntimeError("visibility down")
        for run in self.runs:
            yield run


def _rule(workflow_type: str, keep_completed: int = 0, keep_failed: int = 0) -> CleanRule:
    return CleanRule(
        workflow_type=workflow_type, keep_completed=keep_completed, keep_failed=keep_failed
    )


async def test_deletes_the_old_runs_by_run_id_in_the_namespace() -> None:
    runs = [Listed(f"r{m}", id=f"beads-poll-{m}", close_time=at(m)) for m in (1, 2, 3)]
    client = FakeClient(runs)
    summary = await cleaned(cast(Client, client), "ns", [_rule("beads_poll", keep_completed=1)])
    assert summary.types == [TypeCleaned(workflow_type="beads_poll", completed=2)]
    assert sorted(client.workflow_service.deleted) == [
        ("ns", "beads-poll-1", "r1"),
        ("ns", "beads-poll-2", "r2"),
    ]


async def test_each_rule_queries_only_its_own_type_and_touches_nothing_else() -> None:
    runs = [
        Listed("poll", close_time=at(1)),
        Listed("clean", workflow_type="cleaner", status=FAILED, close_time=at(1)),
        Listed("job", workflow_type="job", close_time=at(1)),
    ]
    client = FakeClient(runs)
    summary = await cleaned(cast(Client, client), "ns", [_rule("beads_poll"), _rule("cleaner")])
    assert client.queries == [closed_runs_query("beads_poll"), closed_runs_query("cleaner")]
    assert "WorkflowType = 'beads_poll'" in client.queries[0]
    assert "ExecutionStatus != 'Running'" in client.queries[0]
    assert sorted(run_id for _, _, run_id in client.workflow_service.deleted) == ["clean", "poll"]
    assert summary.types == [
        TypeCleaned(workflow_type="beads_poll", completed=1),
        TypeCleaned(workflow_type="cleaner", failed=1),
    ]


async def test_a_failing_delete_is_counted_and_the_rest_still_go() -> None:
    runs = [Listed(f"r{m}", close_time=at(m)) for m in (1, 2, 3)]
    runs.append(Listed("f", status=FAILED, close_time=at(1)))
    client = FakeClient(runs, failing={"r2", "f"})
    summary = await cleaned(cast(Client, client), "ns", [_rule("beads_poll")])
    assert summary.types == [
        TypeCleaned(workflow_type="beads_poll", completed=2, failed=0, errors=2)
    ]
    assert sorted(run_id for _, _, run_id in client.workflow_service.deleted) == ["r1", "r3"]


async def test_a_failed_listing_is_one_error_and_the_next_rule_still_runs() -> None:
    runs = [Listed("poll", close_time=at(1))]
    client = FakeClient(runs, broken={closed_runs_query("cleaner")})
    summary = await cleaned(cast(Client, client), "ns", [_rule("cleaner"), _rule("beads_poll")])
    assert summary.types == [
        TypeCleaned(workflow_type="cleaner", errors=1),
        TypeCleaned(workflow_type="beads_poll", completed=1),
    ]
