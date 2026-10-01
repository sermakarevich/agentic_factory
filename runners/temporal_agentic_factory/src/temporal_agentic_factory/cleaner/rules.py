"""Which listed runs one rule deletes, and what a clean returns.

Pure: no Temporal call. A run of another type, or one still running, is never
selected, whatever the list holds. Completed and continued-as-new runs count
as completed; every other closed status (failed, timed out, terminated,
canceled) as failed. Each kind keeps its newest runs, by close time (start
time when a run has none).
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from pydantic import BaseModel
from temporalio.client import WorkflowExecutionStatus

from temporal_agentic_factory.settings.model import CleanRule

COMPLETED_STATUSES = (WorkflowExecutionStatus.COMPLETED, WorkflowExecutionStatus.CONTINUED_AS_NEW)
OLDEST = datetime.min.replace(tzinfo=UTC)


class ListedRun(Protocol):
    """The fields of a listed execution the selection reads."""

    @property
    def workflow_type(self) -> str: ...

    @property
    def status(self) -> WorkflowExecutionStatus | None: ...

    @property
    def close_time(self) -> datetime | None: ...

    @property
    def start_time(self) -> datetime: ...


@dataclass(frozen=True)
class Selection[R: ListedRun]:
    """The runs one rule deletes, completed and failed apart."""

    completed: list[R]
    failed: list[R]


class TypeCleaned(BaseModel):
    """What a clean did to one workflow type: runs deleted by kind, and failed calls."""

    workflow_type: str
    completed: int = 0
    failed: int = 0
    errors: int = 0


class CleanSummary(BaseModel):
    """What a clean did, one entry per rule."""

    types: list[TypeCleaned]


def runs_to_delete[R: ListedRun](runs: list[R], rule: CleanRule) -> Selection[R]:
    """The closed runs of the rule's type beyond its newest `keep_completed` and `keep_failed`."""
    closed = [run for run in runs if _closed_of_type(run, rule.workflow_type)]
    completed = [run for run in closed if run.status in COMPLETED_STATUSES]
    failed = [run for run in closed if run.status not in COMPLETED_STATUSES]
    return Selection(
        completed=_newest_first(completed)[rule.keep_completed :],
        failed=_newest_first(failed)[rule.keep_failed :],
    )


def _closed_of_type(run: ListedRun, workflow_type: str) -> bool:
    """True for a run of `workflow_type` that has closed."""
    status = run.status
    return (
        run.workflow_type == workflow_type
        and status is not None
        and status != WorkflowExecutionStatus.RUNNING
    )


def _newest_first[R: ListedRun](runs: list[R]) -> list[R]:
    """By close time, or start time when a run has none, newest first."""
    return sorted(runs, key=lambda run: run.close_time or run.start_time or OLDEST, reverse=True)
