"""Listed runs for the cleaner tests: the fields of a `WorkflowExecution` the cleaner reads."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from temporalio.client import WorkflowExecutionStatus

START = datetime(2026, 10, 1, tzinfo=UTC)
COMPLETED = WorkflowExecutionStatus.COMPLETED
FAILED = WorkflowExecutionStatus.FAILED
RUNNING = WorkflowExecutionStatus.RUNNING


@dataclass
class Listed:
    """One listed run: ids, type, status and times."""

    run_id: str
    workflow_type: str = "beads_poll"
    status: WorkflowExecutionStatus | None = COMPLETED
    close_time: datetime | None = None
    start_time: datetime = START
    id: str = "beads-poll"


def at(minutes: int) -> datetime:
    """`minutes` after the start of the test day."""
    return START + timedelta(minutes=minutes)
