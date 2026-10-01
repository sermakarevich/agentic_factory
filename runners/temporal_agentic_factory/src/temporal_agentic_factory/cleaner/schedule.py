"""The cleaner schedule over a client: create or replace it, read its state.

The schedule fires `cleaner` every `interval_sec`; a clean still running when
the next is due makes the schedule skip that one. The lifecycle itself is the
shared one in `schedules.py`.
"""

from temporalio.client import Client, Schedule

from temporal_agentic_factory.cleaner.rules import CleanSummary
from temporal_agentic_factory.cleaner.workflow import CleanConfig, CleanerWorkflow
from temporal_agentic_factory.schedules import (
    Every,
    ResultReader,
    ScheduleStatus,
    interval_schedule,
    schedule_status,
    start_schedule,
)

STATIC_SUMMARY = "clean history"


async def start_cleaner_schedule(
    client: Client, schedule_id: str, task_queue: str, interval_sec: int, config: CleanConfig
) -> bool:
    """The cleaner schedule created, replacing one under `schedule_id`; True when one was."""
    return await start_schedule(
        client, schedule_id, cleaner_schedule(schedule_id, task_queue, interval_sec, config)
    )


def cleaner_schedule(
    schedule_id: str, task_queue: str, interval_sec: int, config: CleanConfig
) -> Schedule:
    """`cleaner` every `interval_sec` with the rules as its input, skipped while one still runs."""
    return interval_schedule(
        CleanerWorkflow.run,
        config,
        Every(schedule_id, task_queue, interval_sec, STATIC_SUMMARY),
    )


async def cleaner_schedule_status(client: Client, schedule_id: str) -> ScheduleStatus:
    """The cleaner schedule's state and its newest clean's counts."""
    return await schedule_status(
        client, schedule_id, ResultReader(CleanSummary, summary_line, "clean failed")
    )


def summary_line(summary: CleanSummary) -> str:
    """One clean's counts in one line, one part per type."""
    return "; ".join(
        f"{cleaned.workflow_type}: completed {cleaned.completed}"
        f" failed {cleaned.failed} errors {cleaned.errors}"
        for cleaned in summary.types
    )
