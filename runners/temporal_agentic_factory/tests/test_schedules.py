from datetime import timedelta
from typing import cast

import pytest
from pydantic import BaseModel
from temporalio import workflow
from temporalio.client import (
    Client,
    ScheduleActionStartWorkflow,
    ScheduleHandle,
    ScheduleOverlapPolicy,
    WorkflowExecutionStatus,
    WorkflowFailureError,
)
from temporalio.exceptions import ApplicationError
from temporalio.service import RPCError, RPCStatusCode

from temporal_agentic_factory.schedules import (
    ABSENT,
    Every,
    ResultReader,
    delete_schedule,
    interval_schedule,
    schedule_status,
    start_schedule,
)
from tests.fake_schedules import NEXT_RUN, FakeClient, Run

SCHEDULE_ID = "every"
EVERY = Every(SCHEDULE_ID, "queue", 45, "a tick")


class Counted(BaseModel):
    count: int


@workflow.defn(name="counter")
class CounterWorkflow:
    @workflow.run
    async def run(self, start: Counted) -> Counted:
        return start


READER = ResultReader(Counted, lambda counted: f"counted {counted.count}", "count failed")


async def _started(client: FakeClient) -> bool:
    schedule = interval_schedule(CounterWorkflow.run, Counted(count=1), EVERY)
    return await start_schedule(cast(Client, client), SCHEDULE_ID, schedule)


async def test_an_interval_schedule_fires_the_workflow_with_its_input_and_skips_overlaps() -> None:
    client = FakeClient()
    assert await _started(client) is False
    schedule = client.schedules[SCHEDULE_ID]
    assert [spec.every for spec in schedule.spec.intervals] == [timedelta(seconds=45)]
    assert schedule.policy.overlap == ScheduleOverlapPolicy.SKIP
    action = schedule.action
    assert isinstance(action, ScheduleActionStartWorkflow)
    assert (action.workflow, action.id, action.task_queue) == ("counter", SCHEDULE_ID, "queue")
    assert action.static_summary == "a tick"
    assert list(action.args) == [Counted(count=1)]


async def test_start_again_replaces_the_schedule() -> None:
    client = FakeClient()
    await _started(client)
    assert await _started(client) is True
    assert client.deleted == [SCHEDULE_ID]
    assert client.created == [SCHEDULE_ID, SCHEDULE_ID]


async def test_delete_removes_the_schedule_and_a_missing_one_is_nothing_to_delete() -> None:
    client = FakeClient()
    await _started(client)
    assert await delete_schedule(cast(Client, client).get_schedule_handle(SCHEDULE_ID)) is True
    assert await delete_schedule(cast(Client, client).get_schedule_handle(SCHEDULE_ID)) is False


async def test_delete_raises_failures_other_than_not_found() -> None:
    class Broken:
        async def delete(self) -> None:
            raise RPCError("schedule not found, they say", RPCStatusCode.UNAVAILABLE, b"")

    with pytest.raises(RPCError):
        await delete_schedule(cast(ScheduleHandle, Broken()))


async def test_status_of_a_missing_schedule() -> None:
    found = await schedule_status(cast(Client, FakeClient()), SCHEDULE_ID, READER)
    assert (found.exists, found.last_run) == (False, None)


async def test_status_shows_interval_next_run_and_the_last_runs_line() -> None:
    client = FakeClient()
    await _started(client)
    client.started = [("every-1", "r1")]
    client.runs[("every-1", "r1")] = Run(WorkflowExecutionStatus.COMPLETED, Counted(count=7))
    found = await schedule_status(cast(Client, client), SCHEDULE_ID, READER)
    assert (found.exists, found.paused, found.interval_sec) == (True, False, 45)
    assert found.next_run == NEXT_RUN
    assert found.last_run is not None
    assert (found.last_run.workflow_id, found.last_run.status) == ("every-1", "COMPLETED")
    assert found.last_run.result == "counted 7"


async def test_status_says_why_the_last_run_failed_and_tolerates_a_deleted_one() -> None:
    client = FakeClient()
    await _started(client)
    error = WorkflowFailureError(cause=ApplicationError("server is down"))
    client.runs[("every-1", "r1")] = Run(WorkflowExecutionStatus.FAILED, error)
    client.started = [("every-1", "r1")]
    failed = await schedule_status(cast(Client, client), SCHEDULE_ID, READER)
    assert failed.last_run is not None and failed.last_run.result == "count failed: server is down"
    client.started = [("every-0", "gone")]
    gone = await schedule_status(cast(Client, client), SCHEDULE_ID, READER)
    assert gone.last_run is not None
    assert (gone.last_run.status, gone.last_run.result) == (ABSENT, "")
