"""The poll schedule over a client: create or replace it, read its state, end the old watcher.

The schedule fires `beads_poll` every `interval_sec`; a tick still running when
the next is due makes the schedule skip that one, so ticks never stack. The
lifecycle itself is the shared one in `schedules.py`.
"""

from temporalio.client import Client, Schedule
from temporalio.service import RPCError, RPCStatusCode

from temporal_agentic_factory.schedules import (
    Every,
    ResultReader,
    ScheduleStatus,
    interval_schedule,
    schedule_status,
    start_schedule,
)
from temporal_agentic_factory.watchers.beads.models import PollSummary
from temporal_agentic_factory.watchers.beads.workflow import BeadsPollWorkflow, PollConfig

STATIC_SUMMARY = "beads tick"
OLD_WATCHER_ID = "beads-watcher"  # the long-running watcher the schedule replaced


async def start_poll_schedule(
    client: Client, schedule_id: str, task_queue: str, interval_sec: int, config: PollConfig
) -> bool:
    """The poll schedule created, replacing one under `schedule_id`; True when one was replaced."""
    return await start_schedule(
        client, schedule_id, poll_schedule(schedule_id, task_queue, interval_sec, config)
    )


def poll_schedule(
    schedule_id: str, task_queue: str, interval_sec: int, config: PollConfig
) -> Schedule:
    """`beads_poll` every `interval_sec`, skipped while one still runs."""
    return interval_schedule(
        BeadsPollWorkflow.run,
        config,
        Every(schedule_id, task_queue, interval_sec, STATIC_SUMMARY),
    )


async def poll_schedule_status(client: Client, schedule_id: str) -> ScheduleStatus:
    """The poll schedule's state and its newest tick's counts."""
    return await schedule_status(
        client, schedule_id, ResultReader(PollSummary, summary_line, "tick failed")
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


def summary_line(summary: PollSummary) -> str:
    """One tick's counts in one line."""
    return (
        f"spawned {len(summary.spawned)} closed {len(summary.closed)}"
        f" blocked {len(summary.blocked)} released {len(summary.reopened)}"
        f" skipped {len(summary.skipped)} errors {len(summary.errors)}"
    )
