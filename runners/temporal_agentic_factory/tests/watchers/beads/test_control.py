from datetime import timedelta
from typing import cast

from temporalio.client import (
    Client,
    ScheduleActionStartWorkflow,
    ScheduleOverlapPolicy,
    WorkflowExecutionStatus,
    WorkflowFailureError,
)
from temporalio.exceptions import ApplicationError

from temporal_agentic_factory.watchers.beads.control import (
    OLD_WATCHER_ID,
    STATIC_SUMMARY,
    end_old_watcher,
    poll_schedule_status,
    start_poll_schedule,
)
from temporal_agentic_factory.watchers.beads.models import PollSummary
from temporal_agentic_factory.watchers.beads.workflow import PollConfig
from tests.fake_schedules import FakeClient, Run

SCHEDULE_ID = "beads-poll"
CONFIG = PollConfig(tick_timeout_sec=300)


async def _started(client: FakeClient) -> bool:
    return await start_poll_schedule(cast(Client, client), SCHEDULE_ID, "queue", 30, CONFIG)


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
    assert client.created == [SCHEDULE_ID, SCHEDULE_ID]


async def test_the_old_watcher_is_terminated_when_it_runs_and_absent_is_fine() -> None:
    client = FakeClient(runs={(OLD_WATCHER_ID, ""): Run(WorkflowExecutionStatus.RUNNING)})
    assert await end_old_watcher(cast(Client, client)) is True
    assert client.terminated == [OLD_WATCHER_ID]
    assert await end_old_watcher(cast(Client, FakeClient())) is False


async def test_status_shows_the_last_ticks_counts_or_why_it_failed() -> None:
    client = FakeClient()
    await _started(client)
    summary = PollSummary(spawned=["af-1"], closed=["af-2"])
    client.started = [("beads-poll-1", "r1")]
    client.runs[("beads-poll-1", "r1")] = Run(WorkflowExecutionStatus.COMPLETED, summary)
    found = await poll_schedule_status(cast(Client, client), SCHEDULE_ID)
    assert found.last_run is not None
    assert found.last_run.result.startswith("spawned 1 closed 1 blocked 0")
    error = WorkflowFailureError(cause=ApplicationError("bd is down"))
    client.runs[("beads-poll-1", "r1")] = Run(WorkflowExecutionStatus.FAILED, error)
    failed = await poll_schedule_status(cast(Client, client), SCHEDULE_ID)
    assert failed.last_run is not None and failed.last_run.result == "tick failed: bd is down"
