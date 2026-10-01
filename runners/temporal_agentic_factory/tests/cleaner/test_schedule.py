from datetime import timedelta
from typing import cast

from temporalio.client import (
    Client,
    ScheduleActionStartWorkflow,
    ScheduleOverlapPolicy,
    WorkflowExecutionStatus,
)

from temporal_agentic_factory.cleaner.rules import CleanSummary, TypeCleaned
from temporal_agentic_factory.cleaner.schedule import (
    STATIC_SUMMARY,
    cleaner_schedule_status,
    start_cleaner_schedule,
)
from temporal_agentic_factory.cleaner.workflow import CleanConfig
from temporal_agentic_factory.settings.model import CleanRule
from tests.fake_schedules import FakeClient, Run

SCHEDULE_ID = "cleaner"
CONFIG = CleanConfig(
    rules=[
        CleanRule(workflow_type="beads_poll", keep_completed=1, keep_failed=3),
        CleanRule(workflow_type="cleaner", keep_completed=1, keep_failed=3),
    ],
    timeout_sec=300,
)


async def _started(client: FakeClient) -> bool:
    return await start_cleaner_schedule(cast(Client, client), SCHEDULE_ID, "queue", 60, CONFIG)


async def test_start_creates_a_60_s_schedule_with_the_rules_in_its_input() -> None:
    client = FakeClient()
    assert await _started(client) is False
    schedule = client.schedules[SCHEDULE_ID]
    assert [spec.every for spec in schedule.spec.intervals] == [timedelta(seconds=60)]
    assert schedule.policy.overlap == ScheduleOverlapPolicy.SKIP
    action = schedule.action
    assert isinstance(action, ScheduleActionStartWorkflow)
    assert (action.workflow, action.id, action.task_queue) == ("cleaner", SCHEDULE_ID, "queue")
    assert action.static_summary == STATIC_SUMMARY
    assert list(action.args) == [CONFIG]


async def test_start_again_replaces_the_schedule() -> None:
    client = FakeClient()
    await _started(client)
    assert await _started(client) is True
    assert client.deleted == [SCHEDULE_ID]
    assert client.created == [SCHEDULE_ID, SCHEDULE_ID]


async def test_not_found_on_a_missing_schedule_is_tolerated() -> None:
    client = FakeClient()
    assert await _started(client) is False  # the delete before the create answered NOT_FOUND
    found = await cleaner_schedule_status(cast(Client, FakeClient()), SCHEDULE_ID)
    assert (found.exists, found.last_run) == (False, None)


async def test_status_shows_what_the_last_clean_deleted() -> None:
    client = FakeClient()
    await _started(client)
    summary = CleanSummary(
        types=[
            TypeCleaned(workflow_type="beads_poll", completed=2, failed=1),
            TypeCleaned(workflow_type="cleaner", errors=1),
        ]
    )
    client.started = [("cleaner-1", "r1")]
    client.runs[("cleaner-1", "r1")] = Run(WorkflowExecutionStatus.COMPLETED, summary)
    found = await cleaner_schedule_status(cast(Client, client), SCHEDULE_ID)
    assert (found.exists, found.interval_sec) == (True, 60)
    assert found.last_run is not None
    assert found.last_run.result == (
        "beads_poll: completed 2 failed 1 errors 0; cleaner: completed 0 failed 0 errors 1"
    )
