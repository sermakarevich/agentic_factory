from typing import cast

from temporalio.client import Client, WorkflowExecutionCount

from temporal_agentic_factory.capacity import free_slots, running_coder_jobs


class FakeClient:
    """Answers every visibility count with a fixed number; keeps the queries."""

    def __init__(self, running: int) -> None:
        self.running = running
        self.queries: list[str] = []

    async def count_workflows(self, query: str) -> WorkflowExecutionCount:
        self.queries.append(query)
        return WorkflowExecutionCount(count=self.running, groups=[])


def _client(fake: FakeClient) -> Client:
    return cast(Client, fake)


async def test_free_slots_is_the_cap_minus_running() -> None:
    assert await free_slots(_client(FakeClient(running=1)), 4, "q") == 3


async def test_free_slots_never_below_zero() -> None:
    assert await free_slots(_client(FakeClient(running=9)), 4, "q") == 0


async def test_no_cap_is_none_and_counts_nothing() -> None:
    fake = FakeClient(running=9)
    assert await free_slots(_client(fake), 0, "q") is None
    assert fake.queries == []


async def test_counts_only_coder_workflows_on_the_queue() -> None:
    fake = FakeClient(running=2)
    assert await running_coder_jobs(_client(fake), "factory") == 2
    query = fake.queries[0]
    assert "WorkflowType IN ('job', 'job_with_structured_output')" in query
    assert "'distill'" not in query and "'research'" not in query
    assert "TaskQueue = 'factory'" in query and "ExecutionStatus = 'Running'" in query
