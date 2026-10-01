"""A Schedule's lifecycle over a client, for every schedule af owns (the beads
poll, the cleaner): build one that fires a workflow every few seconds, create
or replace it, delete it, read its state and its last run in one line.

The server's NOT_FOUND message varies ("workflow execution already
completed"), so the status code decides, never the text.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

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
from temporalio.types import MethodAsyncSingleParam

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


@dataclass(frozen=True)
class ResultReader[T]:
    """How a schedule's run result reads: its type, its one line, the words before a failure."""

    result_type: type[T]
    line: Callable[[T], str]
    failed: str


@dataclass(frozen=True)
class Every:
    """Where and how often a schedule fires, and the summary its runs show."""

    schedule_id: str
    task_queue: str
    interval_sec: int
    static_summary: str


def interval_schedule[S, P, R](
    workflow: MethodAsyncSingleParam[S, P, R], arg: P, every: Every
) -> Schedule:
    """`workflow(arg)` every `interval_sec`, skipped while one still runs; its runs
    are `<schedule_id>-<time>` (Temporal appends the time)."""
    return Schedule(
        action=ScheduleActionStartWorkflow(
            workflow,
            arg,
            id=every.schedule_id,
            task_queue=every.task_queue,
            static_summary=every.static_summary,
        ),
        spec=ScheduleSpec(
            intervals=[ScheduleIntervalSpec(every=timedelta(seconds=every.interval_sec))]
        ),
        policy=SchedulePolicy(overlap=ScheduleOverlapPolicy.SKIP),
    )


async def start_schedule(client: Client, schedule_id: str, schedule: Schedule) -> bool:
    """The schedule created, replacing one under `schedule_id`; True when one was replaced."""
    replaced = await delete_schedule(client.get_schedule_handle(schedule_id))
    await client.create_schedule(schedule_id, schedule)
    return replaced


async def delete_schedule(handle: ScheduleHandle) -> bool:
    """Delete the schedule; False when it does not exist, so there was nothing to delete."""
    try:
        await handle.delete()
    except RPCError as error:
        if error.status != RPCStatusCode.NOT_FOUND:
            raise
        return False
    return True


async def schedule_status(
    client: Client, schedule_id: str, reader: ResultReader[Any]
) -> ScheduleStatus:
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
        last_run=await _last_run(client, described, reader),
    )


def _interval_sec(described: ScheduleDescription) -> int | None:
    """The first interval of the spec in seconds; None when it has none."""
    intervals = described.schedule.spec.intervals
    return int(intervals[0].every.total_seconds()) if intervals else None


async def _last_run(
    client: Client, described: ScheduleDescription, reader: ResultReader[Any]
) -> LastRun | None:
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
    return LastRun(
        workflow_id=newest.workflow_id,
        run_id=newest.first_execution_run_id,
        status=status,
        result=await _result_line(client, newest, status, reader),
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
    client: Client,
    run: ScheduleActionExecutionStartWorkflow,
    status: str,
    reader: ResultReader[Any],
) -> str:
    """What a closed run did in one line, or why it failed; empty while it runs."""
    if status not in (COMPLETED, FAILED):
        return ""
    handle = client.get_workflow_handle(
        run.workflow_id, run_id=run.first_execution_run_id, result_type=reader.result_type
    )
    try:
        return reader.line(await handle.result())
    except WorkflowFailureError as error:
        return f"{reader.failed}: {error.cause or error}"
