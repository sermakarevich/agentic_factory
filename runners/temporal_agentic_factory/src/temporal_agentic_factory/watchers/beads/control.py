"""The watcher's lifecycle over a client: start it once, stop it, read its state."""

import asyncio
from datetime import timedelta
from typing import Any

from pydantic import BaseModel
from temporalio.client import (
    Client,
    WorkflowExecutionStatus,
    WorkflowFailureError,
    WorkflowHandle,
    WorkflowQueryFailedError,
)
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.service import RPCError, RPCStatusCode

from temporal_agentic_factory.watchers.beads.last_check import LastCheck
from temporal_agentic_factory.watchers.beads.workflow import (
    BeadsWatcherWorkflow,
    WatcherConfig,
    WatcherRun,
)

STATIC_SUMMARY = "beads watcher"
ABSENT = "ABSENT"


class WatcherStatus(BaseModel):
    """Whether the watcher runs, and the last tick it answered with."""

    workflow_id: str
    running: bool
    status: str
    last_check: LastCheck | None = None
    query_error: str = ""


async def start_watcher(
    client: Client, workflow_id: str, task_queue: str, config: WatcherConfig
) -> bool:
    """The watcher started; False when one already runs under `workflow_id`."""
    try:
        await client.start_workflow(
            BeadsWatcherWorkflow.run,
            WatcherRun(config=config),
            id=workflow_id,
            task_queue=task_queue,
            static_summary=STATIC_SUMMARY,
        )
    except WorkflowAlreadyStartedError:
        return False
    return True


async def stop_watcher(client: Client, workflow_id: str, wait_sec: int) -> bool:
    """The watcher cancelled; True once it ended within `wait_sec` (or was not
    running), False when it still runs."""
    handle = client.get_workflow_handle(workflow_id)
    try:
        await handle.cancel()
    except RPCError as error:
        if error.status != RPCStatusCode.NOT_FOUND:
            raise
        return True
    return await _ended_within(handle, wait_sec)


async def _ended_within(handle: WorkflowHandle[Any, Any], wait_sec: int) -> bool:
    """Whether the cancelled run ended before `wait_sec` passed."""
    try:
        await asyncio.wait_for(handle.result(), wait_sec)
    except TimeoutError:
        return False
    except WorkflowFailureError:
        return True  # a cancelled workflow fails its result: that is the end we waited for
    return True


async def watcher_status(client: Client, workflow_id: str, query_timeout_sec: int) -> WatcherStatus:
    """The watcher's state; its last check when it runs and answers the query."""
    handle = client.get_workflow_handle(workflow_id)
    try:
        described = await handle.describe()
    except RPCError as error:
        if error.status != RPCStatusCode.NOT_FOUND:
            raise
        return WatcherStatus(workflow_id=workflow_id, running=False, status=ABSENT)
    if described.status != WorkflowExecutionStatus.RUNNING:
        status = described.status.name if described.status else ABSENT
        return WatcherStatus(workflow_id=workflow_id, running=False, status=status)
    return await _queried(handle, query_timeout_sec)


async def _queried(handle: WorkflowHandle[Any, Any], timeout_sec: int) -> WatcherStatus:
    """A running watcher with its `last_check` answer, or why it gave none."""
    running = WatcherStatus(workflow_id=handle.id, running=True, status="RUNNING")
    try:
        check = await handle.query(
            BeadsWatcherWorkflow.last_check, rpc_timeout=timedelta(seconds=timeout_sec)
        )
    except (RPCError, WorkflowQueryFailedError) as error:
        return running.model_copy(update={"query_error": str(error)})
    return running.model_copy(update={"last_check": check})
