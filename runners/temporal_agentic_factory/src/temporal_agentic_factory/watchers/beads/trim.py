"""Old watcher runs deleted: only the newest `[beads_watcher] keep_runs` closed
runs of the watcher (and of the old one-tick `beads_poll`) stay in history.

Best effort: a failed listing or delete is logged and skipped, never raised.
Every other workflow type is left alone, by the query and again by a check.
"""

import logging
from datetime import UTC, datetime

from temporalio import activity
from temporalio.api.common.v1 import WorkflowExecution as ExecutionRef
from temporalio.api.workflowservice.v1 import DeleteWorkflowExecutionRequest
from temporalio.client import Client, WorkflowExecution, WorkflowExecutionStatus

from temporal_agentic_factory.client import connect
from temporal_agentic_factory.settings.load import settings

WATCHER_TYPES = ("beads_watcher", "beads_poll")
CLOSED_RUNS = (
    "(" + " OR ".join(f"WorkflowType = '{name}'" for name in WATCHER_TYPES) + ")"
    " AND ExecutionStatus != 'Running'"
)

logger = logging.getLogger(__name__)


@activity.defn
async def trim_watcher_runs() -> int:
    """Old watcher runs deleted on the configured server; how many were."""
    return await trimmed(
        await connect(), settings.temporal.namespace, settings.beads_watcher.keep_runs
    )


async def trimmed(client: Client, namespace: str, keep: int) -> int:
    """Every closed watcher run but the newest `keep` deleted; how many were."""
    try:
        runs = await _closed_watcher_runs(client)
    except Exception as error:
        logger.warning("listing old watcher runs failed: %s", error)
        return 0
    deleted = 0
    for run in _newest_first(runs)[keep:]:
        deleted += await _deleted(client, namespace, run)
    return deleted


async def _closed_watcher_runs(client: Client) -> list[WorkflowExecution]:
    """The closed runs of the watcher types; anything else the server returns is dropped."""
    return [
        run
        async for run in client.list_workflows(CLOSED_RUNS)
        if run.workflow_type in WATCHER_TYPES and run.status != WorkflowExecutionStatus.RUNNING
    ]


def _newest_first(runs: list[WorkflowExecution]) -> list[WorkflowExecution]:
    """By close time, or start time when a run has none, newest first."""
    oldest = datetime.min.replace(tzinfo=UTC)
    return sorted(runs, key=lambda run: run.close_time or run.start_time or oldest, reverse=True)


async def _deleted(client: Client, namespace: str, run: WorkflowExecution) -> bool:
    """One run (by its run id, never the current one by workflow id) deleted; False on failure."""
    try:
        await client.workflow_service.delete_workflow_execution(
            DeleteWorkflowExecutionRequest(
                namespace=namespace,
                workflow_execution=ExecutionRef(workflow_id=run.id, run_id=run.run_id),
            )
        )
    except Exception as error:
        logger.warning("deleting watcher run %s/%s failed: %s", run.id, run.run_id, error)
        return False
    return True
