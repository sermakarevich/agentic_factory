from datetime import timedelta
from typing import cast

import pytest
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

from temporal_agentic_factory.watchers.beads.control import (
    ABSENT,
    OLD_WATCHER_ID,
    STATIC_SUMMARY,
    delete_schedule,
    end_old_watcher,
    schedule_status,
    start_schedule,
)
from temporal_agentic_factory.watchers.beads.models import PollSummary
from temporal_agentic_factory.watchers.beads.workflow import PollConfig
from tests.watchers.beads.fake_schedules import NEXT_RUN, FakeClient, Run

SCHEDULE_ID = "beads-poll"
CONFIG = PollConfig(tick_timeout_sec=300, trim_timeout_sec=300)


async def _started(client: FakeClient) -> bool:
    return await start_schedule(cast(Client, client), SCHEDULE_ID, "queue", 30, CONFIG)


async def test_start_creates_a_30_s_schedule_that_skips_overlapping_ticks() -> None:
    client = FakeClient()
    assert await _started(client) is False
    schedule = client.schedules[SCHEDULE_ID]
    assert [spec.every for spec in schedule.spec.intervals] == [timedelta(seconds=30)]
    assert schedule.policy.overlap == ScheduleOverlapPolicy.SKIP
    action = schedule.action
    assert isinstance(action, ScheduleActionStartWorkflow)
    assert (action.workflow, action.id, action.task_queue) == ("beads_poll", SCHEDULE_ID, "queue")
    assert action.static_summary == STATIC_SUMMARY
    assert list(action.args) == [CONFIG]


async def test_start_again_replaces_the_schedule() -> None:
    client = FakeClient()
    await _started(client)
    assert await _started(client) is True
    assert client.deleted == [SCHEDULE_ID]
    assert client.created == [SCHEDULE_ID, SCHEDULE_ID]


async def test_the_old_watcher_is_terminated_when_it_runs_and_absent_is_fine() -> None:
    client = FakeClient(runs={(OLD_WATCHER_ID, ""): Run(WorkflowExecutionStatus.RUNNING)})
    assert await end_old_watcher(cast(Client, client)) is True
    assert client.terminated == [OLD_WATCHER_ID]
    assert await end_old_watcher(cast(Client, FakeClient())) is False


async def test_stop_deletes_the_schedule_and_a_missing_one_is_nothing_to_delete() -> None:
    client = FakeClient()
    await _started(client)
    assert await delete_schedule(cast(Client, client).get_schedule_handle(SCHEDULE_ID)) is True
    assert await delete_schedule(cast(Client, client).get_schedule_handle(SCHEDULE_ID)) is False


async def test_delete_schedule_raises_failures_other_than_not_found() -> None:
    class Broken:
        async def delete(self) -> None:
            raise RPCError("schedule not found, they say", RPCStatusCode.UNAVAILABLE, b"")

    with pytest.raises(RPCError):
        await delete_schedule(cast(ScheduleHandle, Broken()))


async def test_status_of_a_missing_schedule() -> None:
    found = await schedule_status(cast(Client, FakeClient()), SCHEDULE_ID)
    assert (found.exists, found.last_run) == (False, None)


async def test_status_shows_interval_next_run_and_the_last_runs_summary() -> None:
    client = FakeClient()
    await _started(client)
    summary = PollSummary(spawned=["af-1"], closed=["af-2"])
    client.started = [("beads-poll-1", "r1")]
    client.runs[("beads-poll-1", "r1")] = Run(WorkflowExecutionStatus.COMPLETED, summary)
    found = await schedule_status(cast(Client, client), SCHEDULE_ID)
    assert (found.exists, found.paused, found.interval_sec) == (True, False, 30)
    assert found.next_run == NEXT_RUN
    assert found.last_run is not None
    assert (found.last_run.workflow_id, found.last_run.status) == ("beads-poll-1", "COMPLETED")
    assert found.last_run.result.startswith("spawned 1 closed 1 blocked 0")


async def test_status_says_why_the_last_run_failed_and_tolerates_a_deleted_one() -> None:
    client = FakeClient()
    await _started(client)
    error = WorkflowFailureError(cause=ApplicationError("bd is down"))
    client.runs[("beads-poll-1", "r1")] = Run(WorkflowExecutionStatus.FAILED, error)
    client.started = [("beads-poll-1", "r1")]
    failed = await schedule_status(cast(Client, client), SCHEDULE_ID)
    assert failed.last_run is not None and failed.last_run.result == "tick failed: bd is down"
    client.started = [("beads-poll-0", "gone")]
    gone = await schedule_status(cast(Client, client), SCHEDULE_ID)
    assert gone.last_run is not None
    assert (gone.last_run.status, gone.last_run.result) == (ABSENT, "")
