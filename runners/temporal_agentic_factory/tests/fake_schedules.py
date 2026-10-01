"""A Temporal client that holds schedules and workflow runs in memory: what the
schedule modules call, recorded for the tests."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from temporalio.client import (
    Schedule,
    ScheduleActionExecutionStartWorkflow,
    ScheduleActionResult,
    WorkflowExecutionStatus,
)
from temporalio.service import RPCError, RPCStatusCode

NEXT_RUN = datetime(2026, 10, 1, 12, 0, 30, tzinfo=UTC)


def not_found() -> RPCError:
    return RPCError("workflow execution already completed", RPCStatusCode.NOT_FOUND, b"")


@dataclass
class Run:
    """One workflow run: its status and what its result is (a value or the error it raises)."""

    status: WorkflowExecutionStatus
    result: Any = None


@dataclass
class Described:
    """The fields of a schedule description the schedule modules read."""

    schedule: Schedule
    info: Any


@dataclass
class Info:
    next_action_times: list[datetime]
    recent_actions: list[ScheduleActionResult]


class ScheduleHandle:
    def __init__(self, client: "FakeClient", schedule_id: str) -> None:
        self.client = client
        self.id = schedule_id

    async def delete(self) -> None:
        if self.id not in self.client.schedules:
            raise not_found()
        del self.client.schedules[self.id]
        self.client.deleted.append(self.id)

    async def describe(self) -> Described:
        if self.id not in self.client.schedules:
            raise not_found()
        actions = [
            ScheduleActionResult(
                scheduled_at=NEXT_RUN,
                started_at=NEXT_RUN,
                action=ScheduleActionExecutionStartWorkflow(workflow_id, run_id),
            )
            for workflow_id, run_id in self.client.started
        ]
        return Described(self.client.schedules[self.id], Info([NEXT_RUN], actions))


class WorkflowHandle:
    def __init__(self, client: "FakeClient", workflow_id: str, run_id: str | None) -> None:
        self.client = client
        self.key = (workflow_id, run_id or "")

    def run(self) -> Run:
        if self.key not in self.client.runs:
            raise not_found()
        return self.client.runs[self.key]

    async def terminate(self, reason: str | None = None) -> None:
        if self.run().status != WorkflowExecutionStatus.RUNNING:
            raise not_found()
        self.client.terminated.append(self.key[0])

    async def describe(self) -> Run:
        return self.run()

    async def result(self) -> Any:
        result = self.run().result
        if isinstance(result, Exception):
            raise result
        return result


@dataclass
class FakeClient:
    """Schedules by id, runs by (workflow id, run id), the runs a schedule started."""

    schedules: dict[str, Schedule] = field(default_factory=dict)
    runs: dict[tuple[str, str], Run] = field(default_factory=dict)
    started: list[tuple[str, str]] = field(default_factory=list)
    created: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    terminated: list[str] = field(default_factory=list)

    def get_schedule_handle(self, schedule_id: str) -> ScheduleHandle:
        return ScheduleHandle(self, schedule_id)

    async def create_schedule(self, schedule_id: str, schedule: Schedule) -> None:
        self.schedules[schedule_id] = schedule
        self.created.append(schedule_id)

    def get_workflow_handle(
        self, workflow_id: str, run_id: str | None = None, result_type: Any = None
    ) -> WorkflowHandle:
        return WorkflowHandle(self, workflow_id, run_id)
