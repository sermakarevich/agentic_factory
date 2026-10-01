"""The poll schedule's lifecycle over a client: create or replace it, delete it, read its state.

The schedule fires `beads_poll` every `interval_sec`; a tick still running when
the next is due makes the schedule skip that one, so ticks never stack.
"""

from datetime import datetime, timedelta

from pydantic import BaseModel
from temporalio.client import (
    Client,
    Schedule,
    ScheduleActionExecutionStartWorkflow,
    ScheduleActionStartWorkflow,
    ScheduleDescription,
    ScheduleHandle,
    ScheduleIntervalSpec,
    ScheduleOverlapPolicy,
    SchedulePolicy,
    ScheduleSpec,
    WorkflowFailureError,
)
from temporalio.service import RPCError, RPCStatusCode

from temporal_agentic_factory.watchers.beads.models import PollSummary
from temporal_agentic_factory.watchers.beads.workflow import BeadsPollWorkflow, PollConfig

STATIC_SUMMARY = "beads tick"
OLD_WATCHER_ID = "beads-watcher"  # the long-running watcher the schedule replaced
ABSENT = "ABSENT"
COMPLETED = "COMPLETED"
FAILED = "FAILED"


class LastRun(BaseModel):
    """The schedule's newest run: its id, status and what it did in one line."""

    workflow_id: str
    run_id: str
    status: str
    result: str = ""


class ScheduleStatus(BaseModel):
    """Whether the schedule exists and fires, when next, and its last run."""

    schedule_id: str
    exists: bool
    paused: bool = False
    interval_sec: int | None = None
    next_run: datetime | None = None
    last_run: LastRun | None = None


async def start_schedule(
    client: Client, schedule_id: str, task_queue: str, interval_sec: int, config: PollConfig
) -> bool:
    """The schedule created, replacing one under `schedule_id`; True when one was replaced."""
    replaced = await delete_schedule(client.get_schedule_handle(schedule_id))
    await client.create_schedule(
        schedule_id, poll_schedule(schedule_id, task_queue, interval_sec, config)
    )
    return replaced


def poll_schedule(
    schedule_id: str, task_queue: str, interval_sec: int, config: PollConfig
) -> Schedule:
    """`beads_poll` every `interval_sec`, skipped while one still runs; its runs
    are `<schedule_id>-<time>` (Temporal appends the time)."""
    return Schedule(
        action=ScheduleActionStartWorkflow(
            BeadsPollWorkflow.run,
            config,
            id=schedule_id,
            task_queue=task_queue,
            static_summary=STATIC_SUMMARY,
        ),
        spec=ScheduleSpec(intervals=[ScheduleIntervalSpec(every=timedelta(seconds=interval_sec))]),
        policy=SchedulePolicy(overlap=ScheduleOverlapPolicy.SKIP),
    )


async def end_old_watcher(client: Client) -> bool:
    """The old long-running watcher terminated; False when it did not run.

    A closed or missing run answers NOT_FOUND, so the status code decides."""
    try:
        await client.get_workflow_handle(OLD_WATCHER_ID).terminate(
            reason="replaced by the beads-poll schedule"
        )
    except RPCError as error:
        if error.status != RPCStatusCode.NOT_FOUND:
            raise
        return False
    return True


async def delete_schedule(handle: ScheduleHandle) -> bool:
    """Delete the schedule; False when it does not exist, so there was nothing to delete.

    The server's NOT_FOUND message varies ("workflow execution already
    completed"), so the status code decides, not the text.
    """
    try:
        await handle.delete()
    except RPCError as error:
        if error.status != RPCStatusCode.NOT_FOUND:
            raise
        return False
    return True


async def schedule_status(client: Client, schedule_id: str) -> ScheduleStatus:
    """The schedule's state and its newest run; `exists` False when there is none."""
    try:
        described = await client.get_schedule_handle(schedule_id).describe()
    except RPCError as error:
        if error.status != RPCStatusCode.NOT_FOUND:
            raise
        return ScheduleStatus(schedule_id=schedule_id, exists=False)
    return ScheduleStatus(
        schedule_id=schedule_id,
        exists=True,
        paused=described.schedule.state.paused,
        interval_sec=_interval_sec(described),
        next_run=min(described.info.next_action_times, default=None),
        last_run=await _last_run(client, described),
    )


def _interval_sec(described: ScheduleDescription) -> int | None:
    """The first interval of the spec in seconds; None when it has none."""
    intervals = described.schedule.spec.intervals
    return int(intervals[0].every.total_seconds()) if intervals else None


async def _last_run(client: Client, described: ScheduleDescription) -> LastRun | None:
    """The newest run the schedule started, with its status and result line."""
    started = [
        action.action
        for action in described.info.recent_actions
        if isinstance(action.action, ScheduleActionExecutionStartWorkflow)
    ]
    if not started:
        return None
    newest = started[-1]
    status = await _status_of(client, newest.workflow_id, newest.first_execution_run_id)
    result = await _result_line(client, newest, status)
    return LastRun(
        workflow_id=newest.workflow_id,
        run_id=newest.first_execution_run_id,
        status=status,
        result=result,
    )


async def _status_of(client: Client, workflow_id: str, run_id: str) -> str:
    """RUNNING, COMPLETED, FAILED, ...; ABSENT when the run is gone."""
    try:
        described = await client.get_workflow_handle(workflow_id, run_id=run_id).describe()
    except RPCError as error:
        if error.status != RPCStatusCode.NOT_FOUND:
            raise
        return ABSENT
    return described.status.name if described.status else ABSENT


async def _result_line(
    client: Client, run: ScheduleActionExecutionStartWorkflow, status: str
) -> str:
    """What a closed run did: its summary's counts, or why it failed; empty while it runs."""
    if status not in (COMPLETED, FAILED):
        return ""
    handle = client.get_workflow_handle_for(
        BeadsPollWorkflow.run, run.workflow_id, run_id=run.first_execution_run_id
    )
    try:
        return summary_line(await handle.result())
    except WorkflowFailureError as error:
        return f"tick failed: {error.cause or error}"


def summary_line(summary: PollSummary) -> str:
    """One tick's counts in one line."""
    return (
        f"spawned {len(summary.spawned)} closed {len(summary.closed)}"
        f" blocked {len(summary.blocked)} released {len(summary.reopened)}"
        f" skipped {len(summary.skipped)} errors {len(summary.errors)}"
    )
